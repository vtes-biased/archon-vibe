import { openDB, type DBSchema, type IDBPDatabase, type IDBPTransaction, type StoreNames } from 'idb';
import type { User, Role, Sanction, Tournament, DeckObject, League, Promo, VtesCard, OfflinePlayer } from '$lib/types';
import { expandRolesForFilter } from './roles';
import { normalizeSearch, searchTokens } from './utils';

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
    key: string;
    value: User;
    indexes: {
      'by-name': string;
    };
  };
  sanctions: {
    key: string;
    value: Sanction;
    indexes: {
      'by-user': string;
      'by-tournament': string;
    };
  };
  tournaments: {
    key: string;
    value: Tournament;
    indexes: {
      'by-state': string;
      'by-start': string;
      'by-country': string;
      'by-format': string;
      'by-code': string;
      'by-vekn': string;
    };
  };
  decks: {
    key: string;
    value: DeckObject;
    indexes: {
      'by-tournament': string;
      'by-user': string;
    };
  };
  leagues: {
    key: string;
    value: League;
    indexes: {
      'by-country': string;
      'by-start': string;
    };
  };
  promos: {
    key: string;
    value: Promo;
  };
  cards: {
    key: number;
    value: VtesCard;
  };
  metadata: {
    key: string;
    value: string;
  };
}

let dbPromise: Promise<IDBPDatabase<ArchonDB>> | null = null;

const DB_VERSION = 17;

type UpgradeTx = IDBPTransaction<ArchonDB, ArrayLike<StoreNames<ArchonDB>>, 'versionchange'>;

/** Unsynced offline-tournament data lifted out of the old stores before the destructive version
 * upgrade drops them — synced data re-fetches from SSE, but an offline tournament is locked to this device and would lose real work. */
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

/** Runs inside the versionchange transaction and awaits ONLY IDB operations so the transaction
 * stays alive; uses the raw upgrade tx, NOT the getDB() helpers (which would recurse). */
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

  // Issue every row read in one synchronous burst, then await once: a sequential await-per-row loop
  // can let the versionchange transaction go inactive between awaits (idb's documented hazard).
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
      const rescued = await rescueOfflineData(db, transaction);

      // Deleting and recreating every store triggers a full resync from SSE on next connect.
      for (const name of [...db.objectStoreNames]) {
        db.deleteObjectStore(name);
      }

      const userStore = db.createObjectStore('users', { keyPath: 'uid' });
      userStore.createIndex('by-name', 'name');

      const sanctionStore = db.createObjectStore('sanctions', { keyPath: 'uid' });
      sanctionStore.createIndex('by-user', 'user_uid');
      sanctionStore.createIndex('by-tournament', 'tournament_uid');

      const tournamentStore = db.createObjectStore('tournaments', { keyPath: 'uid' });
      tournamentStore.createIndex('by-state', 'state');
      tournamentStore.createIndex('by-start', 'start');
      tournamentStore.createIndex('by-country', 'country');
      tournamentStore.createIndex('by-format', 'format');
      tournamentStore.createIndex('by-code', 'event_code');
      tournamentStore.createIndex('by-vekn', 'external_ids.vekn');

      const deckStore = db.createObjectStore('decks', { keyPath: 'uid' });
      deckStore.createIndex('by-tournament', 'tournament_uid');
      deckStore.createIndex('by-user', 'user_uid');

      const leagueStore = db.createObjectStore('leagues', { keyPath: 'uid' });
      leagueStore.createIndex('by-country', 'country');
      leagueStore.createIndex('by-start', 'start');

      db.createObjectStore('promos', { keyPath: 'uid' });
      db.createObjectStore('cards', { keyPath: 'id' });
      db.createObjectStore('metadata');

      restoreOfflineData(transaction, rescued);
      if (rescued.tournaments.length > 0) {
        console.info(`[IDB] Preserved ${rescued.tournaments.length} offline tournament(s) across upgrade.`);
      }

    },
  });

  return dbPromise;
}

export async function getUser(uid: string): Promise<User | undefined> {
  const db = await getDB();
  return db.get('users', uid);
}

export async function getAllUsers(): Promise<User[]> {
  const db = await getDB();
  // Tombstones now hard-delete the row (sync.ts); this !deleted_at filter is defensive, hiding any
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
  patchUserIndex(user);
}

export async function saveUsersBatch(users: User[]): Promise<void> {
  if (users.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('users', 'readwrite');
  for (const user of users) tx.store.put(user);
  await tx.done;
  for (const user of users) patchUserIndex(user);
}

export async function deleteUser(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('users', uid);
  dropFromUserIndex(uid);
}

/** getAll() over the ~10k-member corpus costs ~100ms+ (each User embeds 4 CategoryRating
 * histories), so this index is read once and patched on write; saveUser/saveUsersBatch/deleteUser/clearAllUsers must all patch it or it goes stale. */
interface UserIndexEntry {
  user: User;
  /** Word-prefix haystack: name, nickname, email and Discord handle tokens. */
  tokens: string[];
  /** Normalized full name — ranking key, precomputed to stay out of sort comparators. */
  nameNorm: string;
  /** Matched as whole-value prefixes, never tokenized: they are opaque ids. */
  vekn: string;
  discordId: string;
}

let userIndexPromise: Promise<Map<string, UserIndexEntry>> | null = null;

function buildEntry(user: User): UserIndexEntry {
  return {
    user,
    // Contact fields exist only in the full projection (an official's entitled members, see backend
    // access_levels.py), so email/Discord search is implicitly scoped to those.
    tokens: [
      ...searchTokens(user.name),
      ...(user.nickname ? searchTokens(user.nickname) : []),
      ...(user.contact_email ? searchTokens(user.contact_email) : []),
      ...(user.contact_discord ? searchTokens(user.contact_discord) : []),
    ],
    nameNorm: normalizeSearch(user.name),
    vekn: user.vekn_id ?? '',
    discordId: user.discord_id ?? '',
  };
}

async function getUserIndex(): Promise<Map<string, UserIndexEntry>> {
  if (!userIndexPromise) {
    userIndexPromise = (async () => {
      const db = await getDB();
      const all = await db.getAll('users');
      return new Map(all.map(u => [u.uid, buildEntry(u)]));
    })();
  }
  return userIndexPromise;
}

/** Components about to show a member search box call this on mount, so the index build
 * isn't billed to the user's first keystroke. */
export async function warmUserIndex(): Promise<void> {
  await getUserIndex();
}

// Chains onto the build promise rather than a materialized map, so a write landing mid-build still
// applies; the IDB write has already committed by the time this runs, so re-indexing is always correct.
function patchUserIndex(user: User): void {
  if (userIndexPromise) void userIndexPromise.then(idx => idx.set(user.uid, buildEntry(user)));
}

function dropFromUserIndex(uid: string): void {
  if (userIndexPromise) void userIndexPromise.then(idx => idx.delete(uid));
}

/** Ranks name-leading matches above incidental word hits, then alphabetically — callers truncate to
 * the top 8/10, so without this a surname query would order by first name arbitrarily. */
function sortSearchResults(entries: UserIndexEntry[], terms: string[]): User[] {
  const lead = terms[0];
  if (lead) {
    // Rank key read off the entry, never recomputed per comparison — normalizing
    // inside a comparator redoes the work O(n log n) times.
    entries.sort((a, b) =>
      (a.nameNorm.startsWith(lead) ? 0 : 1) - (b.nameNorm.startsWith(lead) ? 0 : 1) ||
      a.user.name.localeCompare(b.user.name));
  } else {
    entries.sort((a, b) => a.user.name.localeCompare(b.user.name));
  }
  return entries.map(e => e.user);
}

/** Search is uniformly word-prefix; every term must open a name/nickname/email/Discord token or
 * prefix an id. Mid-word matches are deliberately excluded — they read as a bug (e.g. "inc" hitting an email address). */
export async function getFilteredUsers(
  country?: string,
  roles?: Role[],
  nameSearch?: string
): Promise<User[]> {
  const plainRoles = roles && roles.length > 0 ? [...roles] : undefined;
  const expandedRoles = plainRoles ? expandRolesForFilter(plainRoles) : undefined;
  const terms = nameSearch?.trim() ? searchTokens(nameSearch) : [];
  const index = await getUserIndex();

  const matched: UserIndexEntry[] = [];
  for (const entry of index.values()) {
    const u = entry.user;
    // Tombstones now hard-delete the row (sync.ts); this is defensive, hiding any
    // pre-change soft-deleted row a client still holds until its next full resync.
    if (u.deleted_at) continue;
    if (country && u.country !== country) continue;
    if (expandedRoles && expandedRoles.length > 0 &&
        !(u.roles && expandedRoles.some(role => u.roles!.includes(role)))) continue;
    if (terms.length > 0 &&
        !terms.every(term =>
          entry.tokens.some(tok => tok.startsWith(term)) ||
          entry.vekn.startsWith(term) ||
          entry.discordId.startsWith(term))) continue;
    matched.push(entry);
  }
  return sortSearchResults(matched, terms);
}

export async function clearAllUsers(): Promise<void> {
  const db = await getDB();
  await db.clear('users');
  userIndexPromise = null;
}

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

// DB-clock instant of snapshot generation, echoed on /stream as a freshness signal so the server's
// staleness guard measures real client-away time. Separate from last_sync_timestamp (the data cursor).
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

// Opaque access-version fingerprint: seeded from /snapshot's X-Access-Version header, echoed on
// /stream as ?av=. The client never parses it — a mismatch at connect triggers one resync.
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

// Set while a snapshot streams into the stores, cleared only when eof lands. Streaming ingest writes
// as it reads, so a marker surviving into the next boot means a partial snapshot; connect() refetches.
export async function getSnapshotIngesting(): Promise<boolean> {
  const db = await getDB();
  return (await db.get('metadata', 'snapshot_ingest_in_progress')) === '1';
}

export async function setSnapshotIngesting(): Promise<void> {
  const db = await getDB();
  await db.put('metadata', '1', 'snapshot_ingest_in_progress');
}

export async function clearSnapshotIngesting(): Promise<void> {
  const db = await getDB();
  await db.delete('metadata', 'snapshot_ingest_in_progress');
}

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

export async function getSanctionsForTournament(tournamentUid: string): Promise<Sanction[]> {
  const db = await getDB();
  return db.getAllFromIndex('sanctions', 'by-tournament', tournamentUid);
}

export async function getPlayerSanctionsInTournament(
  userUid: string,
  tournamentUid: string
): Promise<Sanction[]> {
  const sanctions = await getSanctionsForTournament(tournamentUid);
  return sanctions.filter(s => s.user_uid === userUid && !s.deleted_at);
}

/** Sanctions visible in a tournament's context: its own sanctions, plus the given players'
 * sanctions from OTHER tournaments within the last 18 months (VEKN cross-event visibility) — cautions stay private to their own event. */
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

export async function getActiveSanctionsForUser(userUid: string): Promise<Sanction[]> {
  const sanctions = await getSanctionsForUser(userUid);
  const eighteenMonthsAgo = new Date();
  eighteenMonthsAgo.setMonth(eighteenMonthsAgo.getMonth() - 18);

  return sanctions.filter(s => {
    if (s.deleted_at) return false;

    const issuedAt = new Date(s.issued_at);
    const isPermanentBan = s.level === 'suspension' && !s.expires_at;
    return isPermanentBan || issuedAt >= eighteenMonthsAgo;
  });
}

/** Does this sanction currently bar registration? Shared by the single-user and bulk checks below
 * so they can't drift — NOT the same rule as getSuspendedUserUids, which is suspension-only for the rankings board. */
function barsRegistration(s: Sanction, now: Date, cutoff: Date): boolean {
  if (s.deleted_at) return false;
  if (s.level !== 'suspension' && s.level !== 'probation') return false;
  if (s.lifted_at) return false;
  // A suspension with no expiry is permanent, so it outlives the 18-month window.
  const isPermanentBan = s.level === 'suspension' && !s.expires_at;
  if (!isPermanentBan && new Date(s.issued_at) < cutoff) return false;
  if (s.expires_at && new Date(s.expires_at) < now) return false;
  return true;
}

function sanctionWindow(): { now: Date; cutoff: Date } {
  const cutoff = new Date();
  cutoff.setMonth(cutoff.getMonth() - 18);
  return { now: new Date(), cutoff };
}

export async function isUserCurrentlySanctioned(userUid: string): Promise<boolean> {
  const sanctions = await getSanctionsForUser(userUid);
  const { now, cutoff } = sanctionWindow();
  return sanctions.some(s => barsRegistration(s, now, cutoff));
}

/** One pass over the sanctions store: the member pickers need this for a whole page of results at
 * once, and asking per-row cost one IDB transaction each on the path to first paint. */
export async function getRegistrationBarredUids(): Promise<Set<string>> {
  const db = await getDB();
  const all = await db.getAll('sanctions');
  const { now, cutoff } = sanctionWindow();
  const barred = new Set<string>();
  for (const s of all) if (barsRegistration(s, now, cutoff)) barred.add(s.user_uid);
  return barred;
}

/** Single scan of the sanctions store, for bulk filtering (e.g. rankings). */
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

export async function userHasPastSanctions(userUid: string): Promise<boolean> {
  const sanctions = await getSanctionsForUser(userUid);
  // Cautions stay private to their tournament — they don't count as a member-
  // directory sanction, so the "sanctioned" filter must ignore them.
  return sanctions.some(s => !s.deleted_at && s.level !== 'caution');
}

export async function getTournament(uid: string): Promise<Tournament | undefined> {
  const db = await getDB();
  return db.get('tournaments', uid);
}

export async function getTournamentByCode(code: string): Promise<Tournament | undefined> {
  const db = await getDB();
  // An IDB index matches the stored bytes, so the case-insensitive resolve the
  // server does in SQL becomes three exact probes here — the three shapes a code
  // ever takes. The `by-vekn` probe covers an event whose vekn id arrived after
  // its code was minted, and can never shadow a code: it runs only on a miss.
  for (const variant of [code, code.toUpperCase(), code.toLowerCase()]) {
    const hit = await db.getFromIndex('tournaments', 'by-code', variant);
    if (hit && !hit.deleted_at) return hit;
  }
  const byVekn = await db.getFromIndex('tournaments', 'by-vekn', code);
  return byVekn && !byVekn.deleted_at ? byVekn : undefined;
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

export interface FilteredTournamentsResult {
  items: Tournament[];
  total: number;
  /** Size of the leading upcoming/current cluster (see sortUpcomingFirst). */
  upcomingCount: number;
}

const ONGOING_STATES: Set<string> = new Set(['Registration', 'Waiting', 'Playing']);

export type TournamentStateFilter = 'all' | 'upcoming' | 'ongoing' | 'finished';

/** Naive local wall-clock "today", same format as Tournament.start. */
function todayCutoff(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T00:00`;
}

const tournamentDate = (t: Tournament) => t.start || t.modified;

/**
 * "Upcoming" = not Finished and dated today or later — plus actually-running
 * events (Playing/Waiting) from an earlier date, which belong with the live ones.
 */
function isUpcoming(t: Tournament, cutoff: string): boolean {
  return (
    t.state !== 'Finished' &&
    (tournamentDate(t) >= cutoff || t.state === 'Playing' || t.state === 'Waiting')
  );
}

/** Shared by both list queries so the filter and the divider agree on "upcoming". */
function matchesState(t: Tournament, state: TournamentStateFilter, cutoff: string): boolean {
  switch (state) {
    case 'upcoming':
      return isUpcoming(t, cutoff);
    case 'ongoing':
      return ONGOING_STATES.has(t.state);
    case 'finished':
      return t.state === 'Finished';
    default:
      return true;
  }
}

/** Sorts upcoming/current ascending then past descending, returning the upcoming cluster size for an
 * Upcoming/Past divider. Filtering to Finished needs no separate sort flip — with no upcoming events left, the whole list is the past cluster already in recency order. */
export function sortUpcomingFirst(items: Tournament[]): number {
  const cutoff = todayCutoff();
  const date = tournamentDate;
  const isUpcomingHere = (t: Tournament) => isUpcoming(t, cutoff);
  let upcomingCount = 0;
  items.sort((a, b) => {
    const ua = isUpcomingHere(a);
    if (ua !== isUpcomingHere(b)) return ua ? -1 : 1;
    return ua ? date(a).localeCompare(date(b)) : date(b).localeCompare(date(a));
  });
  for (const t of items) {
    if (!isUpcomingHere(t)) break;
    upcomingCount++;
  }
  return upcomingCount;
}

export async function getFilteredTournaments(
  filters: {
    state?: TournamentStateFilter;
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

  if (filters.country && filters.country !== 'all') {
    items = await db.getAllFromIndex('tournaments', 'by-country', filters.country);
  } else if (filters.format && filters.format !== 'all') {
    items = await db.getAllFromIndex('tournaments', 'by-format', filters.format);
  } else {
    items = await db.getAll('tournaments');
  }

  if (filters.state && filters.state !== 'all') {
    const cutoff = todayCutoff();
    items = items.filter(t => matchesState(t, filters.state!, cutoff));
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

/** Matches if the user organizes or participates in it (any state), or — for non-finished events —
 * it's in their country, online (if included), or an NC/CC championship on their continent. */
export async function getAgendaTournaments(
  userUid: string,
  userCountry: string,
  continentCountries: string[],
  filters: { state?: TournamentStateFilter; includeOnline?: boolean; format?: string; search?: string },
  page = 0,
  pageSize = 50,
): Promise<FilteredTournamentsResult> {
  const db = await getDB();
  const allItems = await db.getAll('tournaments');
  const continentSet = new Set(continentCountries);

  let items = allItems.filter(t => {
    if (t.organizers_uids?.includes(userUid)) return true;
    if (t.players?.some(p => p.user_uid === userUid)) return true;
    if (t.state === 'Finished') return false;
    if (t.country === userCountry) return true;
    if (filters.includeOnline && t.online) return true;
    if (t.country && continentSet.has(t.country)) {
      if (t.rank === 'National Championship' || t.rank === 'Continental Championship') return true;
    }
    return false;
  });

  if (filters.state && filters.state !== 'all') {
    const cutoff = todayCutoff();
    items = items.filter(t => matchesState(t, filters.state!, cutoff));
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

export async function getDeck(uid: string): Promise<DeckObject | undefined> {
  const db = await getDB();
  return db.get('decks', uid);
}

export async function getDecksByTournament(tournamentUid: string): Promise<DeckObject[]> {
  const db = await getDB();
  const decks = await db.getAllFromIndex('decks', 'by-tournament', tournamentUid);
  // Offline-deleted decks stay as local tombstones until go-online pushes them (getDeck stays
  // unfiltered — the push payload needs them); hide them from every UI/engine read here.
  return decks.filter(d => !d.deleted_at);
}

export async function getDecksByUser(userUid: string): Promise<DeckObject[]> {
  const db = await getDB();
  const decks = await db.getAllFromIndex('decks', 'by-user', userUid);
  return decks.filter(d => !d.deleted_at);
}

/** Same shape as the old embedded tournament.decks, for callers that still expect it. */
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
  // Removes any other deck with the same (tournament_uid, user_uid, round) but a different uid — this
  // cleans up optimistic decks once authoritative SSE arrives. Spares offline tombstones (deleted_at): they must survive until go-online pushes them.
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

export async function getPromo(uid: string): Promise<Promo | undefined> {
  const db = await getDB();
  return db.get('promos', uid);
}

export async function getAllPromos(): Promise<Promo[]> {
  const db = await getDB();
  return db.getAll('promos');
}

export async function savePromo(promo: Promo): Promise<void> {
  const db = await getDB();
  await db.put('promos', promo);
}

export async function savePromosBatch(promos: Promo[]): Promise<void> {
  if (promos.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('promos', 'readwrite');
  for (const p of promos) tx.store.put(p);
  await tx.done;
}

export async function deletePromo(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('promos', uid);
}

export async function clearAllPromos(): Promise<void> {
  const db = await getDB();
  await db.clear('promos');
}

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

  const cutoff = new Date(Date.now() - 3 * 365.25 * 24 * 3600 * 1000).toISOString();

  const venueMap = new Map<string, { info: VenueInfo; modified: string }>();
  for (const t of tournaments) {
    if (t.deleted_at || !t.venue?.trim() || t.modified < cutoff) continue;
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
