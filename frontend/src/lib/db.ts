/**
 * IndexedDB setup for offline-first storage.
 * Stores objects with uid and modified fields for sync.
 */

import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import type { User, Role, Sanction, Tournament, Rating } from '$lib/types';
import { expandRolesForFilter } from './roles';

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
  ratings: {
    key: string;  // uid
    value: Rating;
    indexes: {
      'by-user': string;
      'by-country': string;
    };
  };
  changes: {
    key: number;  // auto-increment
    value: {
      id?: number;
      store: string;        // "users" | "sanctions" | "tournaments" | "ratings"
      type: 'create' | 'update' | 'delete';
      uid: string;
      timestamp: string;
      event?: unknown;      // business event payload (for tournament actions)
      data?: unknown;       // full object snapshot (for CRUD)
    };
  };
  metadata: {
    key: string;
    value: string;
  };
}

let dbPromise: Promise<IDBPDatabase<ArchonDB>> | null = null;

// Version 11: single tournament store, generalized changes store, full clear on upgrade
const DB_VERSION = 11;

export function getDB(): Promise<IDBPDatabase<ArchonDB>> {
  if (dbPromise) {
    return dbPromise;
  }

  console.log(`Opening IndexedDB archon-db v${DB_VERSION}...`);
  dbPromise = openDB<ArchonDB>('archon-db', DB_VERSION, {
    upgrade(db, oldVersion, _newVersion, transaction) {
      console.log(`IndexedDB upgrade from version ${oldVersion} to ${DB_VERSION}`);

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

      // Tournaments store (single store, all data levels)
      const tournamentStore = db.createObjectStore('tournaments', { keyPath: 'uid' });
      tournamentStore.createIndex('by-state', 'state');
      tournamentStore.createIndex('by-start', 'start');
      tournamentStore.createIndex('by-country', 'country');
      tournamentStore.createIndex('by-format', 'format');

      // Ratings store
      const ratingStore = db.createObjectStore('ratings', { keyPath: 'uid' });
      ratingStore.createIndex('by-user', 'user_uid');
      ratingStore.createIndex('by-country', 'country');

      // Changes log (generalized for all object types)
      db.createObjectStore('changes', { keyPath: 'id', autoIncrement: true });

      // Metadata store for sync state
      db.createObjectStore('metadata');

      console.log('IndexedDB upgrade complete');
    },
  }).then(db => {
    console.log('IndexedDB opened successfully');
    return db;
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

  // Use multiple transactions for very large batches to avoid blocking
  const BATCH_SIZE = 5000;
  for (let i = 0; i < users.length; i += BATCH_SIZE) {
    const batch = users.slice(i, i + BATCH_SIZE);
    const tx = db.transaction('users', 'readwrite');
    for (const user of batch) {
      tx.store.put(user);
    }
    await tx.done;
  }
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
  const nameWords = user.name.toLowerCase().split(/\s+/);
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
  const searchLower = nameSearch?.trim().toLowerCase();
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

// Change log operations
export async function logChange(
  store: string,
  type: 'create' | 'update' | 'delete',
  uid: string,
  options?: { event?: unknown; data?: unknown }
): Promise<void> {
  const db = await getDB();
  await db.add('changes', {
    store,
    type,
    uid,
    timestamp: new Date().toISOString(),
    event: options?.event,
    data: options?.data,
  });
}

export async function getChanges(): Promise<ArchonDB['changes']['value'][]> {
  const db = await getDB();
  return db.getAll('changes');
}

export async function clearChanges(): Promise<void> {
  const db = await getDB();
  await db.clear('changes');
}

export async function clearChangeForUid(uid: string): Promise<void> {
  const db = await getDB();
  const tx = db.transaction('changes', 'readwrite');
  let cursor = await tx.store.openCursor();
  while (cursor) {
    if (cursor.value.uid === uid) {
      await cursor.delete();
    }
    cursor = await cursor.continue();
  }
  await tx.done;
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
  for (const sanction of sanctions) {
    tx.store.put(sanction);
  }
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
  for (const t of tournaments) {
    tx.store.put(t);
  }
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

export async function getFilteredTournaments(
  filters: {
    state?: string;
    country?: string;
    format?: string;
    search?: string;
  },
  sortBy: 'date' | 'name' | 'state' = 'date',
  page = 0,
  pageSize = 50,
): Promise<FilteredTournamentsResult> {
  const db = await getDB();
  let items: Tournament[];

  // Pick best index for initial query
  if (filters.state && filters.state !== 'all') {
    items = await db.getAllFromIndex('tournaments', 'by-state', filters.state);
  } else if (filters.country && filters.country !== 'all') {
    items = await db.getAllFromIndex('tournaments', 'by-country', filters.country);
  } else if (filters.format && filters.format !== 'all') {
    items = await db.getAllFromIndex('tournaments', 'by-format', filters.format);
  } else {
    items = await db.getAll('tournaments');
  }

  // Apply remaining filters in JS
  if (filters.country && filters.country !== 'all') {
    items = items.filter(t => t.country === filters.country);
  }
  if (filters.format && filters.format !== 'all') {
    items = items.filter(t => t.format === filters.format);
  }
  if (filters.search?.trim()) {
    const q = filters.search.trim().toLowerCase();
    items = items.filter(t => t.name.toLowerCase().includes(q));
  }

  // Sort
  if (sortBy === 'date') {
    items.sort((a, b) => {
      const da = a.start || a.modified;
      const db_ = b.start || b.modified;
      return db_.localeCompare(da);
    });
  } else if (sortBy === 'name') {
    items.sort((a, b) => a.name.localeCompare(b.name));
  } else if (sortBy === 'state') {
    const order: Record<string, number> = { Planned: 0, Registration: 1, Waiting: 2, Playing: 3, Finished: 4 };
    items.sort((a, b) => (order[a.state] ?? 0) - (order[b.state] ?? 0));
  }

  const total = items.length;
  const start = page * pageSize;
  return { items: items.slice(start, start + pageSize), total };
}

// Rating operations
export async function getRating(uid: string): Promise<Rating | undefined> {
  const db = await getDB();
  return db.get('ratings', uid);
}

export async function getRatingByUserUid(userUid: string): Promise<Rating | undefined> {
  const db = await getDB();
  const ratings = await db.getAllFromIndex('ratings', 'by-user', userUid);
  return ratings[0];
}

export async function getAllRatings(): Promise<Rating[]> {
  const db = await getDB();
  return db.getAll('ratings');
}

export async function saveRating(rating: Rating): Promise<void> {
  const db = await getDB();
  await db.put('ratings', rating);
}

export async function saveRatingsBatch(ratings: Rating[]): Promise<void> {
  if (ratings.length === 0) return;
  const db = await getDB();
  const tx = db.transaction('ratings', 'readwrite');
  for (const r of ratings) {
    tx.store.put(r);
  }
  await tx.done;
}

export async function deleteRating(uid: string): Promise<void> {
  const db = await getDB();
  await db.delete('ratings', uid);
}

export async function clearAllRatings(): Promise<void> {
  const db = await getDB();
  await db.clear('ratings');
}
