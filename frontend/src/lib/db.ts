/**
 * IndexedDB setup for offline-first storage.
 * Stores objects with uid and modified fields for sync.
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
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
    upgrade(db, oldVersion, _newVersion, transaction) {

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
  // Use the name index to get pre-sorted results
  return db.getAllFromIndex('users', 'by-name');
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

export async function getUsersByCountry(country: string): Promise<User[]> {
  const db = await getDB();
  // Use compound index to get sorted by name
  const range = IDBKeyRange.bound([country, ''], [country, '\uffff']);
  return db.getAllFromIndex('users', 'by-country-name', range);
}

/**
 * Check if a user's name matches a search query.
 * Supports multiple search terms: "vin rip" matches "Vincent Ripoll".
 * Each search term must match the start of at least one name word.
 */
function matchesNameSearch(user: User, search: string): boolean {
  const nameWords = normalizeSearch(user.name).split(/\s+/);
  const searchTerms = search.split(/\s+/).filter(t => t.length > 0);

  // Each search term must match the prefix of a name word or the VEKN ID
  return searchTerms.every(term =>
    nameWords.some(word => word.startsWith(term)) ||
    (user.vekn_id && user.vekn_id.startsWith(term))
  );
}

export async function getUserByVeknId(veknId: string): Promise<User | undefined> {
  const db = await getDB();
  const allUsers = await db.getAll('users');
  return allUsers.find(u => u.vekn_id === veknId);
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

  // Case 1: No country filter - get all sorted by name, then filter in JS
  if (!country) {
    const allUsers = await db.getAllFromIndex('users', 'by-name');
    return applyNameFilter(applyRolesFilter(allUsers));
  }

  // Case 2: Country filter - use compound index, then filter in JS
  const range = IDBKeyRange.bound([country, ''], [country, '\uffff']);
  const usersInCountry = await db.getAllFromIndex('users', 'by-country-name', range);
  return applyNameFilter(applyRolesFilter(usersInCountry));
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
  // Return true if there are any non-deleted sanctions
  return sanctions.some(s => !s.deleted_at);
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
}

const ONGOING_STATES: Set<string> = new Set(['Registration', 'Waiting', 'Playing']);

function sortByDateDesc(items: Tournament[]): void {
  items.sort((a, b) => {
    const da = a.start || a.modified;
    const db_ = b.start || b.modified;
    return db_.localeCompare(da);
  });
}

export async function getFilteredTournaments(
  filters: {
    ongoing?: boolean;
    includeOnline?: boolean;
    country?: string;
    format?: string;
    search?: string;
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

  // Always sort by date desc
  sortByDateDesc(items);

  const total = items.length;
  const start = page * pageSize;
  return { items: items.slice(start, start + pageSize), total };
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

  sortByDateDesc(items);

  const total = items.length;
  const start = page * pageSize;
  return { items: items.slice(start, start + pageSize), total };
}

// Deck operations (standalone DeckObject, extracted from tournaments)
export async function getDeck(uid: string): Promise<DeckObject | undefined> {
  const db = await getDB();
  return db.get('decks', uid);
}

export async function getDecksByTournament(tournamentUid: string): Promise<DeckObject[]> {
  const db = await getDB();
  return db.getAllFromIndex('decks', 'by-tournament', tournamentUid);
}

/** Get decks for a tournament, grouped by user_uid (same shape as old tournament.decks). */
export async function getDecksByTournamentGrouped(tournamentUid: string): Promise<Record<string, DeckObject[]>> {
  const decks = await getDecksByTournament(tournamentUid);
  const grouped: Record<string, DeckObject[]> = {};
  for (const d of decks) {
    (grouped[d.user_uid] ??= []).push(d);
  }
  return grouped;
}

export async function getDecksByUser(userUid: string): Promise<DeckObject[]> {
  const db = await getDB();
  return db.getAllFromIndex('decks', 'by-user', userUid);
}

export async function saveDeck(deck: DeckObject): Promise<void> {
  const db = await getDB();
  const tx = db.transaction('decks', 'readwrite');
  // Deduplicate: remove any deck with same (tournament_uid, user_uid, round) but different uid
  // This cleans up optimistic decks when authoritative SSE arrives
  const existing = await tx.store.index('by-tournament').getAll(deck.tournament_uid);
  for (const d of existing) {
    if (d.uid !== deck.uid && d.user_uid === deck.user_uid && d.round === deck.round) {
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
