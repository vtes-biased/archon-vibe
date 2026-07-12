/**
 * IndexedDB setup for offline-first storage.
 * Stores objects with uid and modified fields for sync.
 */

import { openDB, type DBSchema, type IDBPDatabase, type IDBPTransaction, type StoreNames } from 'idb';
import type { User, Role, Sanction, Tournament, DeckObject, League, VtesCard, OfflinePlayer } from '$lib/types';
import { expandRolesForFilter } from './roles';
import { normalizeSearch } from './utils';

// Device ID: persistent random UUID identifying this browser/device
export function getDeviceId(): string {
  let id = localStorage.getItem('archon_device_id');
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem('archon_device_id', id);
  }
  return id;
}

interface ArchonDB extends DBSchema {
  users: {
    key: string;  // uid
    value: User;
    indexes: {
      'by-name': string;
      'by-country-name': [string, string];  // Compound index for country+name
    };
  };
  sanctions: {
    key: string;  // uid
    value: Sanction;
    indexes: {
      'by-user': string;  // user_uid index for efficient lookups
      'by-tournament': string;  // tournament_uid index
    };
  };
  tournaments: {
    key: string;  // uid
    value: Tournament;
    indexes: {
      'by-state': string;
      'by-start': string;
      'by-country': string;
      'by-format': string;
    };
  };
  decks: {
    key: string;  // uid
    value: DeckObject;
    indexes: {
      'by-tournament': string;
      'by-user': string;
    };
  };
  leagues: {
    key: string;  // uid
    value: League;
    indexes: {
      'by-country': string;
      'by-start': string;
    };
  };
  cards: {
    key: number; // card id
    value: VtesCard;
  };
  metadata: {
    key: string;
    value: string;
  };
}

let dbPromise: Promise<IDBPDatabase<ArchonDB>> | null = null;

// Version 15: new sync — replace ratings with decks store, remove changes store
const DB_VERSION = 15;

type UpgradeTx = IDBPTransaction<ArchonDB, ArrayLike<StoreNames<ArchonDB>>, 'versionchange'>;

/**
 * Unsynced offline-tournament data lifted out of the old stores so it survives
 * the destructive version upgrade below. Synced data is re-fetched from SSE, but
 * an offline tournament is locked to this device and may hold changes not yet
 * pushed to the server — dropping it loses real work. The `offline_*`
 * metadata keys are the manifest of what is unsynced; the referenced rows live
 * in the tournaments / users / sanctions / decks stores.
 */
interface RescuedOfflineData {
  metadata: [string, string][];
  tournaments: Tournament[];
  users: User[];
  sanctions: Sanction[];
  decks: DeckObject[];
}

const EMPTY_RESCUE: RescuedOfflineData = { metadata: [], tournaments: [], users: [], sanctions: [], decks: [] };

function safeParseArray(value: string): unknown[] {
  try {
    const v = JSON.parse(value);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

/**
 * Read unsynced offline-tournament data out of the existing stores before they
 * are dropped. Runs inside the versionchange transaction and awaits ONLY IDB
 * operations (never a non-IDB promise) so the transaction stays alive. Uses the
 * raw upgrade transaction, NOT the getDB() helpers (which would recurse).
 * Returns empty on a fresh DB or a pre-metadata schema.
 */
async function rescueOfflineData(db: IDBPDatabase<ArchonDB>, tx: UpgradeTx): Promise<RescuedOfflineData> {
  if (!db.objectStoreNames.contains('metadata')) return EMPTY_RESCUE;

  const metaStore = tx.objectStore('metadata');
  const [keys, values] = await Promise.all([metaStore.getAllKeys(), metaStore.getAll()]);

  const metadata: [string, string][] = [];
  const tournamentUids = new Set<string>();
  const userUids = new Set<string>();
  const sanctionUids = new Set<string>();
  const deckUids = new Set<string>();

  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const value = values[i];
    if (typeof key !== 'string' || !key.startsWith('offline_') || typeof value !== 'string') continue;
    metadata.push([key, value]);
    if (key.startsWith('offline_tournament:')) {
      tournamentUids.add(key.slice('offline_tournament:'.length));
    } else if (key.startsWith('offline_players:')) {
      for (const p of safeParseArray(value)) {
        const uid = (p as { temp_uid?: string })?.temp_uid;
        if (uid) userUids.add(uid);
      }
    } else if (key.startsWith('offline_sanctions:')) {
      for (const uid of safeParseArray(value)) if (typeof uid === 'string') sanctionUids.add(uid);
    } else if (key.startsWith('offline_decks:')) {
      for (const uid of safeParseArray(value)) if (typeof uid === 'string') deckUids.add(uid);
    }
  }

  // No offline tournaments → nothing to keep (drop any stray offline_* metadata).
  if (tournamentUids.size === 0) return EMPTY_RESCUE;

  // Issue every row read in one synchronous burst, then await once. A sequential
  // await-per-row loop can let the versionchange transaction go inactive between
  // awaits (idb's documented "transaction lifetime" hazard); a single batched
  // await keeps it alive.
  const tournamentReads = db.objectStoreNames.contains('tournaments')
    ? [...tournamentUids].map((uid) => tx.objectStore('tournaments').get(uid)) : [];
  const userReads = db.objectStoreNames.contains('users')
    ? [...userUids].map((uid) => tx.objectStore('users').get(uid)) : [];
  const sanctionReads = db.objectStoreNames.contains('sanctions')
    ? [...sanctionUids].map((uid) => tx.objectStore('sanctions').get(uid)) : [];
  const deckReads = db.objectStoreNames.contains('decks')
    ? [...deckUids].map((uid) => tx.objectStore('decks').get(uid)) : [];
  const [tournaments, users, sanctions, decks] = await Promise.all([
    Promise.all(tournamentReads),
    Promise.all(userReads),
    Promise.all(sanctionReads),
    Promise.all(deckReads),
  ]);

  return {
    metadata,
    tournaments: tournaments.filter((t): t is Tournament => !!t),
    users: users.filter((u): u is User => !!u),
    sanctions: sanctions.filter((s): s is Sanction => !!s),
    decks: decks.filter((d): d is DeckObject => !!d),
  };
}

/** Write rescued offline data back into the freshly recreated stores. */
function restoreOfflineData(tx: UpgradeTx, rescued: RescuedOfflineData): void {
  const meta = tx.objectStore('metadata');
  for (const [key, value] of rescued.metadata) meta.put(value, key);
  const tournaments = tx.objectStore('tournaments');
  for (const t of rescued.tournaments) tournaments.put(t);
  const users = tx.objectStore('users');
  for (const u of rescued.users) users.put(u);
  const sanctions = tx.objectStore('sanctions');
  for (const s of rescued.sanctions) sanctions.put(s);
  const decks = tx.objectStore('decks');
  for (const d of rescued.decks) decks.put(d);
}

export function getDB(): Promise<IDBPDatabase<ArchonDB>> {
  if (dbPromise) {
    return dbPromise;
  }

  dbPromise = openDB<ArchonDB>('archon-db', DB_VERSION, {
    blocked() {
      // Another connection (old tab, service worker) is blocking the upgrade.
      console.warn('[IDB] Upgrade blocked by another connection. Close other tabs.');
    },
    terminated() {
      // Connection was abnormally closed — reset so next getDB() retries.
      dbPromise = null;
    },
    async upgrade(db, _oldVersion, _newVersion, transaction) {

      // Rescue unsynced offline-tournament data before the destructive rebuild
      // Read everything first, then drop/recreate stores, then write
      // it back — all in this versionchange transaction, awaiting only IDB ops.
      const rescued = await rescueOfflineData(db, transaction);

      // On ANY version upgrade: delete all existing stores and recreate fresh.
      // This triggers a full resync from SSE on next connect.
      for (const name of [...db.objectStoreNames]) {
        db.deleteObjectStore(name);
      }

      // Users store
      const userStore = db.createObjectStore('users', { keyPath: 'uid' });
      userStore.createIndex('by-name', 'name');
      userStore.createIndex('by-country-name', ['country', 'name']);

      // Sanctions store
      const sanctionStore = db.createObjectStore('sanctions', { keyPath: 'uid' });
      sanctionStore.createIndex('by-user', 'user_uid');
      sanctionStore.createIndex('by-tournament', 'tournament_uid');

      // Tournaments store (single store, all data levels)
      const tournamentStore = db.createObjectStore('tournaments', { keyPath: 'uid' });
      tournamentStore.createIndex('by-state', 'state');
      tournamentStore.createIndex('by-start', 'start');
      tournamentStore.createIndex('by-country', 'country');
      tournamentStore.createIndex('by-format', 'format');

      // Decks store (standalone deck objects, extracted from tournaments)
      const deckStore = db.createObjectStore('decks', { keyPath: 'uid' });
      deckStore.createIndex('by-tournament', 'tournament_uid');
      deckStore.createIndex('by-user', 'user_uid');

      // Leagues store
      const leagueStore = db.createObjectStore('leagues', { keyPath: 'uid' });
      leagueStore.createIndex('by-country', 'country');
      leagueStore.createIndex('by-start', 'start');

      // Cards store (VTES card database, keyed by card ID)
      db.createObjectStore('cards', { keyPath: 'id' });

      // Metadata store for sync state
      db.createObjectStore('metadata');

      // Restore the rescued offline data into the fresh stores.
      restoreOfflineData(transaction, rescued);
      if (rescued.tournaments.length > 0) {
        console.info(`[IDB] Preserved ${rescued.tournaments.length} offline tournament(s) across upgrade.`);
      }

    },
  });

  return dbPromise;
}

// User operations
export async function getUser(uid: string): Promise<User | undefined> {
  const db = await getDB();
  return db.get('users', uid);
}

export async function getAllUsers(): Promise<User[]> {
  const db = await getDB();
  // Use the name index to get pre-sorted results. Tombstones now hard-delete the
  // row (sync.ts), so this !deleted_at filter is defensive: it hides any
  // pre-change soft-deleted row a client still holds until its next full resync.
  const users = await db.getAllFromIndex('users', 'by-name');
  return users.filter(u => !u.deleted_at);
}

export async function hasAnyUsers(): Promise<boolean> {
  const db = await getDB();
  const count = await db.count('users');
  return count > 0;
}

export async function saveUser(user: User): Promise<void> {
  const db = await getDB();
  await db.put('users', user);
}

export async function saveUsersBatch(users: User[]): Promise<void> {
  if (users.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('users', 'readwrite');
  for (const user of users) tx.store.put(user);
  await tx.done;
}

export async function deleteUser(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('users', uid);
}

/**
 * Check if a user matches a search query.
 * Supports multiple search terms: "vin rip" matches "Vincent Ripoll".
 * Each term must match a name/nickname word prefix, the VEKN/Discord ID prefix,
 * or appear anywhere in the email / Discord handle. Contact fields are only
 * present for an official's entitled members (full projection — see backend
 * access_levels.py), so email/Discord search is implicitly scoped to those.
 */
function matchesNameSearch(user: User, search: string): boolean {
  const nameWords = normalizeSearch(user.name).split(/\s+/);
  const nickWords = user.nickname ? normalizeSearch(user.nickname).split(/\s+/) : [];
  const email = user.contact_email ? normalizeSearch(user.contact_email) : "";
  const discord = user.contact_discord ? normalizeSearch(user.contact_discord) : "";
  const searchTerms = search.split(/\s+/).filter(t => t.length > 0);

  return searchTerms.every(term =>
    nameWords.some(word => word.startsWith(term)) ||
    nickWords.some(word => word.startsWith(term)) ||
    (user.vekn_id != null && user.vekn_id.startsWith(term)) ||
    (user.discord_id != null && user.discord_id.startsWith(term)) ||
    email.includes(term) ||
    discord.includes(term)
  );
}

export async function getFilteredUsers(
  country?: string,
  roles?: Role[],
  nameSearch?: string
): Promise<User[]> {
  // Convert Svelte proxy to plain array and expand roles (e.g., Judge includes Judgekin)
  const plainRoles = roles && roles.length > 0 ? [...roles] : undefined;
  const expandedRoles = plainRoles ? expandRolesForFilter(plainRoles) : undefined;
  const searchLower = nameSearch?.trim() ? normalizeSearch(nameSearch.trim()) : undefined;
  const db = await getDB();

  // Helper to apply name search filter
  const applyNameFilter = (users: User[]): User[] => {
    if (!searchLower) return users;
    return users.filter(u => matchesNameSearch(u, searchLower));
  };

  // Helper to apply roles filter
  const applyRolesFilter = (users: User[]): User[] => {
    if (!expandedRoles || expandedRoles.length === 0) return users;
    return users.filter(u => u.roles && expandedRoles.some(role => u.roles!.includes(role)));
  };

  // Soft-deleted users (e.g. merge_users dups) never appear in listings.
  const notDeleted = (users: User[]): User[] => users.filter(u => !u.deleted_at);

  // Case 1: No country filter - get all sorted by name, then filter in JS
  if (!country) {
    const allUsers = await db.getAllFromIndex('users', 'by-name');
    return applyNameFilter(applyRolesFilter(notDeleted(allUsers)));
  }

  // Case 2: Country filter - use compound index, then filter in JS
  const range = IDBKeyRange.bound([country, ''], [country, '\uffff']);
  const usersInCountry = await db.getAllFromIndex('users', 'by-country-name', range);
  return applyNameFilter(applyRolesFilter(notDeleted(usersInCountry)));
}

export async function clearAllUsers(): Promise<void> {
  const db = await getDB();
  await db.clear('users');
}

// Metadata operations
export async function getLastSyncTimestamp(): Promise<string | null> {
  const db = await getDB();
  const value = await db.get('metadata', 'last_sync_timestamp');
  return value || null;
}

export async function setLastSyncTimestamp(timestamp: string): Promise<void> {
  const db = await getDB();
  await db.put('metadata', timestamp, 'last_sync_timestamp');
}

export async function clearLastSyncTimestamp(): Promise<void> {
  const db = await getDB();
  await db.delete('metadata', 'last_sync_timestamp');
}

// Snapshot generation instant (DB clock), echoed on /stream as a freshness signal so the
// server's staleness guard measures real client-away time rather than the data's
// last-modified time. Separate from last_sync_timestamp, which is the data cursor (since).
export async function getLastSyncGeneratedAt(): Promise<string | null> {
  const db = await getDB();
  const value = await db.get('metadata', 'last_sync_generated_at');
  return value || null;
}

export async function setLastSyncGeneratedAt(generatedAt: string): Promise<void> {
  const db = await getDB();
  await db.put('metadata', generatedAt, 'last_sync_generated_at');
}

export async function clearLastSyncGeneratedAt(): Promise<void> {
  const db = await getDB();
  await db.delete('metadata', 'last_sync_generated_at');
}

// Opaque access-version fingerprint: seeded from the /snapshot X-Access-Version header,
// echoed on /stream as ?av=, and refreshed by targeted-push frames. The client never
// parses it — a mismatch at connect tells the server the cached corpus predates an
// entitlement change and triggers one resync.
export async function getLastSyncAccessVersion(): Promise<string | null> {
  const db = await getDB();
  const value = await db.get('metadata', 'last_sync_access_version');
  return value || null;
}

export async function setLastSyncAccessVersion(av: string): Promise<void> {
  const db = await getDB();
  await db.put('metadata', av, 'last_sync_access_version');
}

export async function clearLastSyncAccessVersion(): Promise<void> {
  const db = await getDB();
  await db.delete('metadata', 'last_sync_access_version');
}

// Sanction operations
export async function getSanction(uid: string): Promise<Sanction | undefined> {
  const db = await getDB();
  return db.get('sanctions', uid);
}

export async function getSanctionsForUser(userUid: string): Promise<Sanction[]> {
  const db = await getDB();
  return db.getAllFromIndex('sanctions', 'by-user', userUid);
}

export async function saveSanction(sanction: Sanction): Promise<void> {
  const db = await getDB();
  await db.put('sanctions', sanction);
}

export async function saveSanctionsBatch(sanctions: Sanction[]): Promise<void> {
  if (sanctions.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('sanctions', 'readwrite');
  for (const s of sanctions) tx.store.put(s);
  await tx.done;
}

export async function deleteSanction(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('sanctions', uid);
}

export async function clearAllSanctions(): Promise<void> {
  const db = await getDB();
  await db.clear('sanctions');
}

/**
 * Get all sanctions for a tournament.
 */
export async function getSanctionsForTournament(tournamentUid: string): Promise<Sanction[]> {
  const db = await getDB();
  return db.getAllFromIndex('sanctions', 'by-tournament', tournamentUid);
}

/**
 * Get sanctions for a specific player in a specific tournament.
 */
export async function getPlayerSanctionsInTournament(
  userUid: string,
  tournamentUid: string
): Promise<Sanction[]> {
  const sanctions = await getSanctionsForTournament(tournamentUid);
  return sanctions.filter(s => s.user_uid === userUid && !s.deleted_at);
}

/**
 * Sanctions visible in a tournament's context: all of the tournament's own
 * sanctions, plus the given players' sanctions from OTHER tournaments within
 * the last 18 months (VEKN cross-event visibility). Only cautions stay
 * private to the event where they were issued. Single scan of the store.
 */
export async function getTournamentContextSanctions(
  tournamentUid: string,
  playerUids: string[]
): Promise<Sanction[]> {
  const db = await getDB();
  const all = await db.getAll('sanctions');
  const players = new Set(playerUids);
  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - 18);

  return all.filter(s => {
    if (s.deleted_at) return false;
    if (s.tournament_uid === tournamentUid) return true;
    if (!players.has(s.user_uid)) return false;
    if (s.level === 'caution') return false;
    return new Date(s.issued_at) >= cutoff;
  });
}

/**
 * Get active (non-deleted) sanctions for a user within the last 18 months.
 */
export async function getActiveSanctionsForUser(userUid: string): Promise<Sanction[]> {
  const sanctions = await getSanctionsForUser(userUid);
  const eighteenMonthsAgo = new Date();
  eighteenMonthsAgo.setMonth(eighteenMonthsAgo.getMonth() - 18);

  return sanctions.filter(s => {
    // Exclude soft-deleted sanctions
    if (s.deleted_at) return false;

    // Include if within last 18 months OR if it's a permanent ban (no expires_at on suspension)
    const issuedAt = new Date(s.issued_at);
    const isPermanentBan = s.level === 'suspension' && !s.expires_at;
    return isPermanentBan || issuedAt >= eighteenMonthsAgo;
  });
}

/**
 * Check if user currently has an active ban/suspension/probation.
 * Returns true if there's an active sanction that hasn't been lifted and hasn't expired.
 */
export async function isUserCurrentlySanctioned(userUid: string): Promise<boolean> {
  const sanctions = await getActiveSanctionsForUser(userUid);
  const now = new Date();

  return sanctions.some(s => {
    // Only count suspension and probation as "currently sanctioned"
    if (s.level !== 'suspension' && s.level !== 'probation') return false;

    // Skip if lifted
    if (s.lifted_at) return false;

    // Check if expired
    if (s.expires_at && new Date(s.expires_at) < now) return false;

    return true;
  });
}

/**
 * Get the set of user UIDs that are currently suspended.
 * Single scan of sanctions store — efficient for bulk filtering (e.g., rankings).
 */
export async function getSuspendedUserUids(): Promise<Set<string>> {
  const db = await getDB();
  const allSanctions = await db.getAll('sanctions');
  const now = new Date();
  const suspended = new Set<string>();

  for (const s of allSanctions) {
    if (s.deleted_at) continue;
    if (s.level !== 'suspension') continue;
    if (s.lifted_at) continue;
    if (s.expires_at && new Date(s.expires_at) < now) continue;
    suspended.add(s.user_uid);
  }

  return suspended;
}

/**
 * Check if user has any past sanctions (including lifted/expired).
 */
export async function userHasPastSanctions(userUid: string): Promise<boolean> {
  const sanctions = await getSanctionsForUser(userUid);
  // Cautions stay private to their tournament — they don't count as a member-
  // directory sanction, so the "sanctioned" filter must ignore them.
  return sanctions.some(s => !s.deleted_at && s.level !== 'caution');
}

// Tournament operations (single store, all data levels)
export async function getTournament(uid: string): Promise<Tournament | undefined> {
  const db = await getDB();
  return db.get('tournaments', uid);
}

export async function getAllTournaments(): Promise<Tournament[]> {
  const db = await getDB();
  return db.getAll('tournaments');
}

export async function saveTournament(tournament: Tournament): Promise<void> {
  const db = await getDB();
  await db.put('tournaments', tournament);
}

export async function saveTournamentsBatch(tournaments: Tournament[]): Promise<void> {
  if (tournaments.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('tournaments', 'readwrite');
  for (const t of tournaments) tx.store.put(t);
  await tx.done;
}

export async function deleteTournament(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('tournaments', uid);
}

export async function clearAllTournaments(): Promise<void> {
  const db = await getDB();
  await db.clear('tournaments');
}

// Filtered tournament queries using indexes
export interface FilteredTournamentsResult {
  items: Tournament[];
  total: number;
  /** Size of the leading upcoming/current cluster (see sortUpcomingFirst). */
  upcomingCount: number;
}

const ONGOING_STATES: Set<string> = new Set(['Registration', 'Waiting', 'Playing']);

/**
 * Sort in place: upcoming/current events ascending (soonest first), then past
 * events descending (most recent first). Returns the upcoming cluster size so
 * callers can render an Upcoming/Past divider. "Upcoming" = not Finished and
 * dated today or later — plus actually-running events (Playing/Waiting) from an
 * earlier date, which belong above the divider while live.
 */
export function sortUpcomingFirst(items: Tournament[]): number {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  // Naive local wall-clock cutoff, same format as Tournament.start.
  const cutoff = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T00:00`;
  const date = (t: Tournament) => t.start || t.modified;
  const isUpcoming = (t: Tournament) =>
    t.state !== 'Finished' &&
    (date(t) >= cutoff || t.state === 'Playing' || t.state === 'Waiting');
  let upcomingCount = 0;
  items.sort((a, b) => {
    const ua = isUpcoming(a);
    if (ua !== isUpcoming(b)) return ua ? -1 : 1;
    return ua ? date(a).localeCompare(date(b)) : date(b).localeCompare(date(a));
  });
  for (const t of items) {
    if (!isUpcoming(t)) break;
    upcomingCount++;
  }
  return upcomingCount;
}

export async function getFilteredTournaments(
  filters: {
    ongoing?: boolean;
    includeOnline?: boolean;
    country?: string;
    format?: string;
    search?: string;
    excludePast?: boolean;
  },
  page = 0,
  pageSize = 50,
): Promise<FilteredTournamentsResult> {
  const db = await getDB();
  let items: Tournament[];

  // Pick best index for initial query
  if (filters.country && filters.country !== 'all') {
    items = await db.getAllFromIndex('tournaments', 'by-country', filters.country);
  } else if (filters.format && filters.format !== 'all') {
    items = await db.getAllFromIndex('tournaments', 'by-format', filters.format);
  } else {
    items = await db.getAll('tournaments');
  }

  // Apply filters in JS
  if (filters.ongoing) {
    items = items.filter(t => ONGOING_STATES.has(t.state));
  }
  // Logged-out viewers see current + upcoming only (no finished/past events).
  if (filters.excludePast) {
    items = items.filter(t => t.state !== 'Finished');
  }
  if (filters.country && filters.country !== 'all') {
    items = items.filter(t => t.country === filters.country);
  }
  if (filters.includeOnline === false) {
    items = items.filter(t => !t.online);
  }
  if (filters.format && filters.format !== 'all') {
    items = items.filter(t => t.format === filters.format);
  }
  if (filters.search?.trim()) {
    const q = normalizeSearch(filters.search.trim());
    items = items.filter(t => normalizeSearch(t.name).includes(q));
  }

  const upcomingCount = sortUpcomingFirst(items);

  const total = items.length;
  const start = page * pageSize;
  return { items: items.slice(start, start + pageSize), total, upcomingCount };
}

/**
 * Get tournaments matching the user's personal agenda.
 * A tournament matches if ANY of these are true:
 * 1. Same country (non-finished)
 * 2. Online (if includeOnline, non-finished)
 * 3. NC/CC on same continent (non-finished)
 * 4. User organizes it (any state)
 * 5. User participates (any state)
 */
export async function getAgendaTournaments(
  userUid: string,
  userCountry: string,
  continentCountries: string[],
  filters: { ongoing?: boolean; includeOnline?: boolean; format?: string; search?: string },
  page = 0,
  pageSize = 50,
): Promise<FilteredTournamentsResult> {
  const db = await getDB();
  const allItems = await db.getAll('tournaments');
  const continentSet = new Set(continentCountries);

  let items = allItems.filter(t => {
    // User organizes (any state)
    if (t.organizers_uids?.includes(userUid)) return true;
    // User participates (any state)
    if (t.players?.some(p => p.user_uid === userUid)) return true;
    // Non-finished only for geographic matches
    if (t.state === 'Finished') return false;
    // Same country
    if (t.country === userCountry) return true;
    // Online
    if (filters.includeOnline && t.online) return true;
    // NC/CC on same continent
    if (t.country && continentSet.has(t.country)) {
      if (t.rank === 'National Championship' || t.rank === 'Continental Championship') return true;
    }
    return false;
  });

  // Apply additional filters
  if (filters.ongoing) {
    items = items.filter(t => ONGOING_STATES.has(t.state));
  }
  if (filters.format && filters.format !== 'all') {
    items = items.filter(t => t.format === filters.format);
  }
  if (filters.search?.trim()) {
    const q = normalizeSearch(filters.search.trim());
    items = items.filter(t => normalizeSearch(t.name).includes(q));
  }

  const upcomingCount = sortUpcomingFirst(items);

  const total = items.length;
  const start = page * pageSize;
  return { items: items.slice(start, start + pageSize), total, upcomingCount };
}

// Deck operations (standalone DeckObject, extracted from tournaments)
export async function getDeck(uid: string): Promise<DeckObject | undefined> {
  const db = await getDB();
  return db.get('decks', uid);
}

export async function getDecksByTournament(tournamentUid: string): Promise<DeckObject[]> {
  const db = await getDB();
  const decks = await db.getAllFromIndex('decks', 'by-tournament', tournamentUid);
  // Offline-deleted decks are kept as local tombstones until go-online pushes
  // them (getDeck stays unfiltered — the push payload needs them); hide them
  // from every UI/engine read.
  return decks.filter(d => !d.deleted_at);
}

/** Get decks for a tournament, grouped by user_uid (same shape as old tournament.decks). */
export async function getDecksByTournamentGrouped(tournamentUid: string): Promise<Record<string, DeckObject[]>> {
  const decks = await getDecksByTournament(tournamentUid);
  const grouped: Record<string, DeckObject[]> = {};
  for (const d of decks) {
    (grouped[d.user_uid] ??= []).push(d);
  }
  // Sort each player's decks by round so array index matches slot index
  for (const arr of Object.values(grouped)) {
    arr.sort((a, b) => (a.round ?? 0) - (b.round ?? 0));
  }
  return grouped;
}

export async function saveDeck(deck: DeckObject): Promise<void> {
  const db = await getDB();
  const tx = db.transaction('decks', 'readwrite');
  // Deduplicate: remove any deck with same (tournament_uid, user_uid, round) but different uid
  // This cleans up optimistic decks when authoritative SSE arrives. Spare offline
  // tombstones (deleted_at): they must survive until go-online pushes them —
  // authoritative deletions arrive as del-frames by uid, never through here.
  const existing = await tx.store.index('by-tournament').getAll(deck.tournament_uid);
  for (const d of existing) {
    if (d.uid !== deck.uid && d.user_uid === deck.user_uid && d.round === deck.round && !d.deleted_at) {
      tx.store.delete(d.uid);
    }
  }
  tx.store.put(deck);
  await tx.done;
}

export async function saveDecksBatch(decks: DeckObject[]): Promise<void> {
  if (decks.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('decks', 'readwrite');
  for (const d of decks) tx.store.put(d);
  await tx.done;
}

export async function deleteDeck(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('decks', uid);
}

export async function clearAllDecks(): Promise<void> {
  const db = await getDB();
  await db.clear('decks');
}

// League operations
export async function getLeague(uid: string): Promise<League | undefined> {
  const db = await getDB();
  return db.get('leagues', uid);
}

export async function getAllLeagues(): Promise<League[]> {
  const db = await getDB();
  return db.getAll('leagues');
}

export async function saveLeague(league: League): Promise<void> {
  const db = await getDB();
  await db.put('leagues', league);
}

export async function saveLeaguesBatch(leagues: League[]): Promise<void> {
  if (leagues.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('leagues', 'readwrite');
  for (const l of leagues) tx.store.put(l);
  await tx.done;
}

export async function deleteLeague(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('leagues', uid);
}

export async function clearAllLeagues(): Promise<void> {
  const db = await getDB();
  await db.clear('leagues');
}

// Metadata helpers for offline tournament state

export async function getMetadata(key: string): Promise<string | undefined> {
  const db = await getDB();
  return db.get('metadata', key);
}

export async function setMetadata(key: string, value: string): Promise<void> {
  const db = await getDB();
  await db.put('metadata', value, key);
}

export async function deleteMetadata(key: string): Promise<void> {
  const db = await getDB();
  await db.delete('metadata', key);
}

/** Get all metadata keys matching a prefix. */
export async function getMetadataByPrefix(prefix: string): Promise<Map<string, string>> {
  const db = await getDB();
  const tx = db.transaction('metadata', 'readonly');
  const result = new Map<string, string>();
  let cursor = await tx.store.openCursor();
  while (cursor) {
    if (typeof cursor.key === 'string' && cursor.key.startsWith(prefix)) {
      result.set(cursor.key, cursor.value);
    }
    cursor = await cursor.continue();
  }
  await tx.done;
  return result;
}

// Offline players registry (stored as JSON in metadata store)

export async function getOfflinePlayers(tournamentUid: string): Promise<OfflinePlayer[]> {
  const raw = await getMetadata(`offline_players:${tournamentUid}`);
  if (!raw) return [];
  return JSON.parse(raw);
}

export async function setOfflinePlayers(tournamentUid: string, players: OfflinePlayer[]): Promise<void> {
  await setMetadata(`offline_players:${tournamentUid}`, JSON.stringify(players));
}

export async function addOfflinePlayer(tournamentUid: string, player: OfflinePlayer): Promise<void> {
  const players = await getOfflinePlayers(tournamentUid);
  players.push(player);
  await setOfflinePlayers(tournamentUid, players);
}

// Offline sanctions registry (list of sanction UIDs created offline for a tournament)

export async function getOfflineSanctionUids(tournamentUid: string): Promise<string[]> {
  const raw = await getMetadata(`offline_sanctions:${tournamentUid}`);
  if (!raw) return [];
  return JSON.parse(raw);
}

export async function addOfflineSanctionUid(tournamentUid: string, sanctionUid: string): Promise<void> {
  const uids = await getOfflineSanctionUids(tournamentUid);
  uids.push(sanctionUid);
  await setMetadata(`offline_sanctions:${tournamentUid}`, JSON.stringify(uids));
}

export async function getOfflineDeckUids(tournamentUid: string): Promise<string[]> {
  const raw = await getMetadata(`offline_decks:${tournamentUid}`);
  if (!raw) return [];
  return JSON.parse(raw);
}

export async function addOfflineDeckUid(tournamentUid: string, deckUid: string): Promise<void> {
  const uids = await getOfflineDeckUids(tournamentUid);
  uids.push(deckUid);
  await setMetadata(`offline_decks:${tournamentUid}`, JSON.stringify(uids));
}

// Venue autocomplete from tournament history

export interface VenueInfo {
  venue: string;
  venue_url: string;
  address: string;
  map_url: string;
}

export async function getVenuesByCountry(country: string): Promise<VenueInfo[]> {
  if (!country) return [];
  const db = await getDB();
  const tournaments = await db.getAllFromIndex('tournaments', 'by-country', country);

  // Only consider tournaments from the last 3 years
  const cutoff = new Date(Date.now() - 3 * 365.25 * 24 * 3600 * 1000).toISOString();

  // Keep most recent tournament's data per venue name
  const venueMap = new Map<string, { info: VenueInfo; modified: string }>();
  for (const t of tournaments) {
    if (t.deleted_at || !t.venue?.trim() || t.modified < cutoff) continue;
    // Strip diacritics, punctuation, and whitespace for matching
    const key = normalizeSearch(t.venue).replace(/[^\w]/g, '');
    const existing = venueMap.get(key);
    if (!existing || t.modified > existing.modified) {
      venueMap.set(key, {
        info: {
          venue: t.venue.trim(),
          venue_url: t.venue_url ?? '',
          address: t.address ?? '',
          map_url: t.map_url ?? '',
        },
        modified: t.modified,
      });
    }
  }

  return [...venueMap.values()]
    .map(v => v.info)
    .sort((a, b) => a.venue.localeCompare(b.venue));
}
