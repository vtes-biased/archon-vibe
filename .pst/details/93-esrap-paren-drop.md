# esrap 2.2.10 drops parentheses in `A && (B || C)` — silent app-wide miscompilation

**Status: FIXED** (esrap bumped 2.2.10 → 2.2.11; `overrides` guard added). Blocking.

## Symptom
Opening any tournament detail page left it stuck on "Syncing" / "Sign in to view full
tournament details", because the SSE sync handler threw on every sync cycle:

```
TypeError: Cannot read properties of undefined (reading 'tournament_uid')
  at handleSync (src/routes/tournaments/[uid]/+page.svelte)
  at SyncManager.emit (src/lib/sync.ts)
```

## Root cause
`esrap` is Svelte's AST→code printer. Version **2.2.10** drops the parentheses around a
`||` group when it is an operand of `&&`, turning `A && (B || C)` into `A && B || C`
(which JS parses as `(A && B) || C` — different semantics).

The crash site, `handleSync`:
```js
if (event.type === "deck" && (!event.data?.tournament_uid || event.data.tournament_uid === uid)) { … }
```
compiled (2.2.10) to:
```js
if (strict_equals(event.type,"deck") && !event.data?.tournament_uid || strict_equals(event.data.tournament_uid, get(uid))) { … }
```
For events with no `data` (`syncing`, `sync_complete`, …) the `A && B` half is false, so JS
evaluates the `|| C` half → `event.data.tournament_uid` on `undefined` → throws. The throw
propagated out of `SyncManager.emit`, aborting the sync → page never received full data.

This was **not** specific to `handleSync` — esrap 2.2.10 mis-printed *every* `A && (B || C)`
in `.svelte` files. Two more confirmed (silent, no throw):
- `canStartNext` (`+page.svelte`): `(checkedIn+playing) >= 4 && (maxRounds === 0 || rounds < maxRounds)`
  → `(>=4 && max===0) || rounds<max`. With `maxRounds > 0` this lets the organizer start a
  round with **fewer than 4 checked-in players**.
- QR `{#if}` (`+page.svelte`): `showQrCode && (state===Registration || state===Waiting) && checkin_code`
  → wrong visibility logic.

`.ts` files are unaffected (compiled by esbuild, not Svelte/esrap).

## How it was diagnosed
The project's `node_modules/svelte` produced dropped parens while a clean `npm i svelte@5.56.x`
in a temp dir did not — same svelte version. Difference was the transitive `esrap`:
the project's `package-lock.json` pinned `esrap@2.2.10`; a fresh resolve picked `2.2.11`.

Minimal reproduction (run inside `frontend/`):
```js
import { compile } from 'svelte/compiler';
const src = `<script>let {a,b,c}=$props();const r=$derived(a&&(b||c));</script>{r}`;
console.log(compile(src,{generate:'client',runes:true}).js.code);
// 2.2.10:  $.derived(() => a && b || c)         ← BUG (parens dropped)
// 2.2.11:  $.derived(() => a && (b || c))       ← correct
```

## Fix
- `npm update esrap` → `esrap@2.2.11` (also incidentally bumped `svelte` 5.56.1 → 5.56.3).
- Added `"overrides": { "esrap": ">=2.2.11" }` to `frontend/package.json` so it can never
  resolve back to 2.2.10 on a fresh install / lock regeneration.
- Verified: served Vite output now keeps the parens for all three sites; `svelte-check` clean.

Svelte version was a red herring — 5.56.0/5.56.1/5.56.3 are all correct with good esrap.

## Follow-up (optional)
- Consider reporting upstream to the `esrap` repo if not already fixed in their changelog.
- When bumping Svelte/esrap in future, re-run the minimal repro above as a guard.
