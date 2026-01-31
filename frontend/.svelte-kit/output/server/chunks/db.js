import { openDB } from "idb";
const ROLE_COLORS = {
  IC: {
    bg: "bg-purple-900/60",
    text: "text-purple-200"
  },
  NC: {
    bg: "bg-blue-900/60",
    text: "text-blue-200"
  },
  Prince: {
    bg: "bg-crimson-800/60",
    text: "text-crimson-200"
  },
  Ethics: {
    bg: "bg-emerald-900/60",
    text: "text-emerald-200"
  },
  PTC: {
    bg: "bg-cyan-900/60",
    text: "text-cyan-200"
  },
  PT: {
    bg: "bg-teal-900/60",
    text: "text-teal-200"
  },
  Rulemonger: {
    bg: "bg-amber-900/60",
    text: "text-amber-200"
  },
  Judge: {
    bg: "bg-indigo-900/60",
    text: "text-indigo-200"
  },
  Judgekin: {
    bg: "bg-slate-800/60",
    text: "text-slate-200"
  },
  DEV: {
    bg: "bg-lime-900/60",
    text: "text-lime-200"
  }
};
function getRoleClasses(role) {
  const config = ROLE_COLORS[role];
  return `${config.bg} ${config.text}`;
}
function expandRolesForFilter(roles) {
  const expanded = new Set(roles);
  if (expanded.has("Judge")) {
    expanded.add("Judgekin");
    expanded.add("Rulemonger");
  }
  return Array.from(expanded);
}
let dbPromise = null;
const DB_VERSION = 11;
function getDB() {
  if (dbPromise) {
    return dbPromise;
  }
  console.log(`Opening IndexedDB archon-db v${DB_VERSION}...`);
  dbPromise = openDB("archon-db", DB_VERSION, {
    upgrade(db, oldVersion, _newVersion, transaction) {
      console.log(`IndexedDB upgrade from version ${oldVersion} to ${DB_VERSION}`);
      for (const name of [...db.objectStoreNames]) {
        db.deleteObjectStore(name);
      }
      const userStore = db.createObjectStore("users", { keyPath: "uid" });
      userStore.createIndex("by-name", "name");
      userStore.createIndex("by-country-name", ["country", "name"]);
      const sanctionStore = db.createObjectStore("sanctions", { keyPath: "uid" });
      sanctionStore.createIndex("by-user", "user_uid");
      const tournamentStore = db.createObjectStore("tournaments", { keyPath: "uid" });
      tournamentStore.createIndex("by-state", "state");
      tournamentStore.createIndex("by-start", "start");
      tournamentStore.createIndex("by-country", "country");
      tournamentStore.createIndex("by-format", "format");
      const ratingStore = db.createObjectStore("ratings", { keyPath: "uid" });
      ratingStore.createIndex("by-user", "user_uid");
      ratingStore.createIndex("by-country", "country");
      db.createObjectStore("changes", { keyPath: "id", autoIncrement: true });
      db.createObjectStore("metadata");
      console.log("IndexedDB upgrade complete");
    }
  }).then((db) => {
    console.log("IndexedDB opened successfully");
    return db;
  });
  return dbPromise;
}
async function hasAnyUsers() {
  const db = await getDB();
  const count = await db.count("users");
  return count > 0;
}
async function saveUser(user) {
  const db = await getDB();
  await db.put("users", user);
}
async function saveUsersBatch(users) {
  if (users.length === 0) return;
  const db = await getDB();
  const BATCH_SIZE = 5e3;
  for (let i = 0; i < users.length; i += BATCH_SIZE) {
    const batch = users.slice(i, i + BATCH_SIZE);
    const tx = db.transaction("users", "readwrite");
    for (const user of batch) {
      tx.store.put(user);
    }
    await tx.done;
  }
}
function matchesNameSearch(user, search) {
  const nameWords = user.name.toLowerCase().split(/\s+/);
  const searchTerms = search.split(/\s+/).filter((t) => t.length > 0);
  return searchTerms.every(
    (term) => nameWords.some((word) => word.startsWith(term)) || user.vekn_id && user.vekn_id.startsWith(term)
  );
}
async function getFilteredUsers(country, roles, nameSearch) {
  const plainRoles = roles && roles.length > 0 ? [...roles] : void 0;
  const expandedRoles = plainRoles ? expandRolesForFilter(plainRoles) : void 0;
  const searchLower = nameSearch?.trim().toLowerCase();
  const db = await getDB();
  const applyNameFilter = (users) => {
    if (!searchLower) return users;
    return users.filter((u) => matchesNameSearch(u, searchLower));
  };
  const applyRolesFilter = (users) => {
    if (!expandedRoles || expandedRoles.length === 0) return users;
    return users.filter((u) => u.roles && expandedRoles.some((role) => u.roles.includes(role)));
  };
  if (!country) {
    const allUsers = await db.getAllFromIndex("users", "by-name");
    return applyNameFilter(applyRolesFilter(allUsers));
  }
  const range = IDBKeyRange.bound([country, ""], [country, "￿"]);
  const usersInCountry = await db.getAllFromIndex("users", "by-country-name", range);
  return applyNameFilter(applyRolesFilter(usersInCountry));
}
async function clearAllUsers() {
  const db = await getDB();
  await db.clear("users");
}
async function clearChanges() {
  const db = await getDB();
  await db.clear("changes");
}
async function clearChangeForUid(uid) {
  const db = await getDB();
  const tx = db.transaction("changes", "readwrite");
  let cursor = await tx.store.openCursor();
  while (cursor) {
    if (cursor.value.uid === uid) {
      await cursor.delete();
    }
    cursor = await cursor.continue();
  }
  await tx.done;
}
async function getLastSyncTimestamp() {
  const db = await getDB();
  const value = await db.get("metadata", "last_sync_timestamp");
  return value || null;
}
async function setLastSyncTimestamp(timestamp) {
  const db = await getDB();
  await db.put("metadata", timestamp, "last_sync_timestamp");
}
async function clearLastSyncTimestamp() {
  const db = await getDB();
  await db.delete("metadata", "last_sync_timestamp");
}
async function getSanctionsForUser(userUid) {
  const db = await getDB();
  return db.getAllFromIndex("sanctions", "by-user", userUid);
}
async function saveSanction(sanction) {
  const db = await getDB();
  await db.put("sanctions", sanction);
}
async function saveSanctionsBatch(sanctions) {
  if (sanctions.length === 0) return;
  const db = await getDB();
  const tx = db.transaction("sanctions", "readwrite");
  for (const sanction of sanctions) {
    tx.store.put(sanction);
  }
  await tx.done;
}
async function deleteSanction(uid) {
  const db = await getDB();
  await db.delete("sanctions", uid);
}
async function clearAllSanctions() {
  const db = await getDB();
  await db.clear("sanctions");
}
async function getActiveSanctionsForUser(userUid) {
  const sanctions = await getSanctionsForUser(userUid);
  const eighteenMonthsAgo = /* @__PURE__ */ new Date();
  eighteenMonthsAgo.setMonth(eighteenMonthsAgo.getMonth() - 18);
  return sanctions.filter((s) => {
    if (s.deleted_at) return false;
    const issuedAt = new Date(s.issued_at);
    const isPermanentBan = s.level === "suspension" && !s.expires_at;
    return isPermanentBan || issuedAt >= eighteenMonthsAgo;
  });
}
async function isUserCurrentlySanctioned(userUid) {
  const sanctions = await getActiveSanctionsForUser(userUid);
  const now = /* @__PURE__ */ new Date();
  return sanctions.some((s) => {
    if (s.level !== "suspension" && s.level !== "probation") return false;
    if (s.lifted_at) return false;
    if (s.expires_at && new Date(s.expires_at) < now) return false;
    return true;
  });
}
async function userHasPastSanctions(userUid) {
  const sanctions = await getSanctionsForUser(userUid);
  return sanctions.some((s) => !s.deleted_at);
}
async function saveTournament(tournament) {
  const db = await getDB();
  await db.put("tournaments", tournament);
}
async function saveTournamentsBatch(tournaments) {
  if (tournaments.length === 0) return;
  const db = await getDB();
  const tx = db.transaction("tournaments", "readwrite");
  for (const t of tournaments) {
    tx.store.put(t);
  }
  await tx.done;
}
async function deleteTournament(uid) {
  const db = await getDB();
  await db.delete("tournaments", uid);
}
async function clearAllTournaments() {
  const db = await getDB();
  await db.clear("tournaments");
}
async function saveRating(rating) {
  const db = await getDB();
  await db.put("ratings", rating);
}
async function saveRatingsBatch(ratings) {
  if (ratings.length === 0) return;
  const db = await getDB();
  const tx = db.transaction("ratings", "readwrite");
  for (const r of ratings) {
    tx.store.put(r);
  }
  await tx.done;
}
async function clearAllRatings() {
  const db = await getDB();
  await db.clear("ratings");
}
export {
  saveUsersBatch as a,
  saveUser as b,
  clearChangeForUid as c,
  deleteTournament as d,
  deleteSanction as e,
  saveSanctionsBatch as f,
  getLastSyncTimestamp as g,
  saveSanction as h,
  saveTournamentsBatch as i,
  saveTournament as j,
  saveRatingsBatch as k,
  saveRating as l,
  clearAllUsers as m,
  clearAllSanctions as n,
  clearAllTournaments as o,
  clearAllRatings as p,
  clearChanges as q,
  clearLastSyncTimestamp as r,
  setLastSyncTimestamp as s,
  getRoleClasses as t,
  expandRolesForFilter as u,
  getFilteredUsers as v,
  userHasPastSanctions as w,
  isUserCurrentlySanctioned as x,
  hasAnyUsers as y
};
//# sourceMappingURL=db.js.map
