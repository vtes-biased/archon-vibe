# Frontend dead-code sweep — full list

From the 2026-07-04 codebase audit. "Dead" = zero references verified by grep across
frontend/src + tests.

## Redundant guards

- ~20 `requireOnline()` calls immediately preceding `apiRequest` — apiRequest gained the
  identical offline guard in 76b0c17 (2026-06-09), one day after requireOnline was
  consolidated (20e5bcc); the pairs were never cleaned. KEEP requireOnline for the raw-fetch
  `importArchonFile` (api.ts:504).

## Dead API/db/type items

- `fetchUsers` — api.ts:189 (vestigial forward to getAllUsers from the API-read era)
- `liftSanction` — api.ts:430 (superseded by `updateSanction(uid, {lifted:true})`)
- `deleteAvatar` — api.ts:749 + stranded `/** Delete user avatar. */` docblock at :633-635
- `getUsersByCountry` — db.ts:302 (superseded by getFilteredUsers' country branch)
- `getDecksByUser` — db.ts:771 (the decks `by-user` index it fed → drop at next DB_VERSION
  bump, ticket 398)
- `AuthMethod` interface — types.ts:156 (auth store defines its own local one; this models a
  `credential_hash` the frontend never receives)
- `TournamentConfig` interface — types.ts:418 (drifted shadow; `Tournament` covers the fields)
- Orphaned docblocks — engine.ts:74-76 (stranded "Tournament event types" comment) and
  :256-263 (full docblock for the removed computeSeating)
- Dynamic re-import of `getOfflineTournamentUids` — sync.ts:575 (already statically imported
  at :51)

## Dead exports sweep

- `dismissAllToasts` — stores/toast.svelte.ts:64
- `cycleTheme` — stores/theme.svelte.ts:33
- `clearError` — stores/auth.svelte.ts:569
- `getCard` — cards.ts:55
- `getCityById` — geonames.ts:97
- `getCitiesByCountry` — geonames.ts:146 (+ fix the stale lib/README.md example referencing it)
- `DISCIPLINE_NAME_TO_TRIGRAM` — vtes-icons.ts:50

## Dead components / component-local dead code

- `LocaleSwitcher.svelte` — zero imports since Paraglide phase-0 (1ca65a7); owner OK'd deletion
- Tournament `+page.svelte` dead cluster: `isPlayerDQ` (:344), `sanctionsForPlayer` (:347),
  `seatDisplay` wrapper (:355), dead `getRatingPts` copy (:214 — also covered by ticket 381),
  unused imports (`vpOptions`, `computeGwLocal`, `computeTpLocal`, `scoreSeatingSync` — the
  scoring ones also die via ticket 380)
- PlayersTab.svelte:116 — identical-branch conditional in `currentRound` (collapse to one return)
- FinalsTab.svelte:37 — write-only `alterSeating` (+ its onchange write at :130)

## Deliberately excluded (kept for feature tickets)

- Offline-tournament-creation chain (`createTournamentOffline` api.ts:564,
  `createTournamentWithEngine` engine.ts:547) — feature ticket 400
- Passkey conditional-UI trio + abort controller (passkeys.svelte.ts:225-344) — feature
  ticket 401
