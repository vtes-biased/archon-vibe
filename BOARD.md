# Board

A list designed to shrink. **The goal is zero.** Completion is deletion — there is
no closed state, no archive; git history is the record and `git blame` knows a
line's age.

**Order is priority.** Ranking rules, applied top to bottom when two unrelated
lines compete:

1. user-reported defects
2. correctness
3. blocking work and useful refactorings
4. polish
5. new capability

**Hard limit: 15 lines.** Adding a sixteenth forces a drop or a promotion to the
wiki. **No waiting state**: externally-gated work is deferred on the wiki page
that owns it — see [wiki/vekn-decommission.md](wiki/vekn-decommission.md) — with a
named trigger, and returns through `/intake` when the trigger fires.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [wiki](wiki/index.md) page and delete the line. Context lives in
the wiki; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.


- Make the Profile nav item show whether you are signed in, with a distinct sign-in icon and label for a signed-out visitor, read from the stored session rather than `isAuthenticated`, which drops whenever `/auth/me` is unreachable. **Done when** the bottom nav and the rail differ between signed-in and signed-out using no green, a signed-in member offline still shows as signed in, `/profile` offline no longer asks that member to sign in, and `wiki/design.md` records the nav states. From gh-80, an organizer on Android Chrome who could not tell from the icon.
- Let a developer edit an existing app's scopes and redirect URIs, and drop deactivated apps from their list. **Done when** the Developer section edits both under the registration rules (`backend/src/routes/oauth.py:806`, `:812`), owner and first-party session only, with the purpose of a held `profile:email` fixed since members consented to it; removing a scope strips it from every consent and kills the token lineages carrying it, because a refresh re-issues the token's own scopes (`:522`) and a kept consent would re-grant it silently (`:187`); a deactivated app leaves its owner's list while its row stays, because `list_consents` skips a consent with no client (`:732`); and `wiki/access.md` records both. From gh-81, a DEV member maintaining an app.
- Let an official switch the promo inventory between grouping by promo and grouping by holder, so an NC can read each Prince's stock at a glance. **Done when** a segmented pill toggle above the holdings offers "By promo" / "By holder", mirrored in the URL; by holder lists each holder alphabetically with their promos, showing remaining and received counts and the retired badge; both views work offline from the synced holdings; the labels exist in every locale; and doc-impact is none, since it reuses the segmented-toggle idiom and records no new decision. From an NC.
