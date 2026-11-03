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


- Read the Archon spreadsheet's Override sheet on import, so a table the organizer listed there with an explanation comes in as judge-overridden instead of refusing the whole file. **Done when** a sheet whose Override tab lists a round (or `F` for the final), a table and a non-empty Explanation imports that table as Finished with an override stamped to the importing organizer and the Explanation as its comment, skipping only the VP-distribution check while table size, VP range and half-steps are still checked; a listed row with a blank Explanation, or one naming a table that does not exist, is refused with a message saying so; a table that fails the VP check and is not listed is refused with a plain-language reason that points to the Override sheet rather than an internal error name; and the "Archon Excel import" section of `wiki/architecture.md` describes the Override sheet's use. From an organizer whose import was refused on a Life Boon table that ended in time.
- Hold the organizers' never-finished warning until an event's declared Finish date has passed, so a long online event still running stops being called never finished. **Done when** an event whose Finish date is still ahead stays off the warning on `/tournaments`, one with no Finish is warned as today and one with a past Finish two days after that date, the list index carries `finish` (`frontend/src/lib/db.ts:757`, `:1012`), and `wiki/product.md` states the rule. From gh-82, a Prince and Judge on Android running JOL events of about three months of rounds plus finals, warned on all three.
- Tell a player what the event will publish, beside their deck's private checkbox, so `decklists_mode` stops being visible to organizers alone; private stays opt-in. **Done when** a player with a submitted deck reads which decks the event publishes on finish (Winner / Finalists / All) beside "Keep this decklist private" in `DeckDisplay.svelte:295`, in every locale, and the player guide and `wiki/tournaments.md` say so, recording why the default stays opt-in: private outranks the mode (`engine/src/tournament/helpers.rs:292`), so a private default would void Finalists and All. From gh-79, a Sheriff and Rulemonger on desktop, no specific event named.
- Make the Profile nav item show whether you are signed in, with a distinct sign-in icon and label for a signed-out visitor, read from the stored session rather than `isAuthenticated`, which drops whenever `/auth/me` is unreachable. **Done when** the bottom nav and the rail differ between signed-in and signed-out using no green, a signed-in member offline still shows as signed in, `/profile` offline no longer asks that member to sign in, and `wiki/design.md` records the nav states. From gh-80, an organizer on Android Chrome who could not tell from the icon.
- Let a developer edit an existing app's scopes and redirect URIs, and drop deactivated apps from their list. **Done when** the Developer section edits both under the registration rules (`backend/src/routes/oauth.py:806`, `:812`), owner and first-party session only, with the purpose of a held `profile:email` fixed since members consented to it; removing a scope strips it from every consent and kills the token lineages carrying it, because a refresh re-issues the token's own scopes (`:522`) and a kept consent would re-grant it silently (`:187`); a deactivated app leaves its owner's list while its row stays, because `list_consents` skips a consent with no client (`:732`); and `wiki/access.md` records both. From gh-81, a DEV member maintaining an app.
- Let an official switch the promo inventory between grouping by promo and grouping by holder, so an NC can read each Prince's stock at a glance. **Done when** a segmented pill toggle above the holdings offers "By promo" / "By holder", mirrored in the URL; by holder lists each holder alphabetically with their promos, showing remaining and received counts and the retired badge; both views work offline from the synced holdings; the labels exist in every locale; and doc-impact is none, since it reuses the segmented-toggle idiom and records no new decision. From an NC.
