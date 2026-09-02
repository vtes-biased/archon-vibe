Doc-impact: `wiki/design.md` — §"List view state" carries the promise that must end
up true, and the `/users/[uid]` surface section is where a back affordance is
recorded if that is the fix. Not `wiki/hazards.md`: `syncQueryParams` is the single
chokepoint and already carries the trap comment.

## Reproduce before changing anything

The naive diagnosis — "the tab is not mirrored to the URL" — is **wrong**. Measured
signed out against the dev server on 2026-09-02:

- `/users`, click Members → address bar becomes `/users?tab=members`.
- Client-side link navigation to `/users/<uid>`, then browser Back → URL is
  `/users?tab=members` and the Members pill is `aria-pressed="true"`.
- Same from the profile via the bottom-bar Community icon (`openLastView`) → also
  restores Members.

So the failing path is not the plain signed-out one. Reproduce as an official first.

## Ruled out

On Back into a `replaceState`-mirrored entry, SvelteKit restores its own recorded
pre-shallow URL into `page.url` and does **not** rewrite the address bar — the
history write in `navigate()` sits behind `if (!popped)`. That is precisely why
`url-filters.ts` reads `window.location`. The existing comment there is correct and
is not the bug.

## Surviving hypotheses

- The members directory renders only for signed-in viewers, so the broken path may
  be official-only — `UserList` mounts and runs its own `syncQueryParams` effect
  there, which the signed-out repro never exercises.
- `openLastView`'s memory is per-tab `sessionStorage` with a 30-minute inactivity
  window. A profile opened in a **new tab**, or returned to after a pause, resolves
  the nav icon to the bare `/users` — which is the Community tab.

## Adjacent

`/tournaments/[uid]` has a back link (`openLastView`); `/users/[uid]` has none, so
in the installed app the nav icon is the only way back.
