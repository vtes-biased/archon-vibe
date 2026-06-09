# Frontend error-surfacing audit

Audit of how errors reach the user across login, permissions, network, engine, sync,
and tournament/league flows. Children #102–#106 are the first-pass P2 fixes; #107 is the
proper P3 structured-error-code effort.

## Root-cause threads

1. **Engine errors are thrown as plain JS strings.** Every WASM export is
   `Result<String, String>` (`engine/src/lib.rs`), errors built via `.map_err(|e| e.to_string())?`.
   wasm-bindgen throws an `Err(String)` as a JS **primitive string**, so `e instanceof Error`
   is `false`. The dominant catch shape `e instanceof Error ? e.message : m.fallback()` therefore
   **discards** the precise engine reason and shows the generic localized fallback. This is the
   exact "hide the real issue behind a blanket message" failure — it already happens today.

2. **Network/transport failures bypass the toast.** `apiRequest` (`api.ts:57-68`) only toasts on
   `!response.ok`. A thrown `fetch` (offline mid-request, DNS, CORS, server down) propagates as a
   `TypeError` and is **not** toasted. Combined with the intentional empty catches
   (`// Error toast shown by apiRequest`) in SanctionsManager, VeknManagement, OrganizerManager,
   TournamentSanctionModal, PlayersTab, User avatar, profile resync → **fully silent** on a drop.
   And these `api.ts` mutations call `requireOnline()` first, which throws the localized offline
   message *before* `apiRequest` — also swallowed by the same empty catches. Issuing a sanction or
   sponsoring a VEKN id while offline gives zero feedback.

3. **WASM load failure is invisible.** `+layout.svelte:51` `initEngine().catch(console.error)`.
   On failure the app silently degrades (fail-closed permissions, optimistic→server-only,
   empty standings/validation) with no user signal. → #103.

## Where engine precision lands today (page-level `catch (e)`)

| Source | JS type | Today shows | Precise? |
|---|---|---|---|
| Server rejected action | `ApiError` | `e.message` = server `detail` | yes |
| Network/transport | `TypeError` | `e.message` = "Failed to fetch" | cryptic |
| Direct WASM reject | **string** | `m.fallback()` | **dropped** |
| `requireOnline()` | `Error(m.…)` | localized offline msg | yes |

Note: for **tournament actions** the WASM throw is swallowed by `tournament-actions.ts:167`'s
`catch {}` and re-run on the server, so online the reason returns as `ApiError.detail` (row 1).
The string-throw drop (row 3) only escapes to the UI in **direct-engine paths**: offline
tournament creation (`tournaments/new` → `createTournamentWithEngine`) and the direct
`computeLeagueStandings` call (#105). Offline, that same `catch {}` masks an engine *rejection*
as "requires online" (#102).

## What's already good (don't regress)

- Fail-closed permission gating (`engine.ts` `isOrganizer`/`canEditLeague`/`canChangeRole` return
  false until WASM loads, never default-allow).
- Double-submit guards on every async action (loading flags).
- Optimistic rollback with the server's reason surfaced.
- OAuth callback errors are localized (`login/+page.svelte:117-124`).

## Gaps → tickets

- #102 — shape-aware message mapper + network/offline-aware toasts (the core; surfaces string
  engine errors, friendly network message, kills the silent empty-catch flows, fixes the
  offline-rejection masking, login network-vs-auth).
- #103 — surface WASM engine load failure.
- #104 — SSE/sync banner: localize + manual Reconnect + stale-data hint; stop silent give-up.
- #105 — league standings compute fails silently → inline error + retry.
- #106 — localize remaining hardcoded strings.
- #107 — P3 proper: stable engine error codes + params → localized frontend mapping.

## Not pursued (by design / out of scope here)

- "Who to ask" remediation copy on permission denials — needs product-manager wording per role
  (NC implicit organizer rights; judge calls → explicit organizers). File separately if wanted.
- Toast dedup/stack cap — minor; `CheckInAll` over many barred players can stack identical toasts.
