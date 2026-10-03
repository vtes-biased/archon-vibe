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


- Let a member manage their login methods from the profile: add a further passkey or link a further Discord once one exists, remove a Discord login or a passkey, refusing the last remaining login method, and keep the profile's Discord link and username on the Discord they last signed in with — done when the profile lists each passkey distinguishably with an Add button and a Link Discord button always available, both removals work, removing the last method is refused, signing in with a second Discord updates both link and username, removing the Discord the profile shows hands both to a remaining Discord login or clears them, and `wiki/access.md` (login methods) and `wiki/hazards.md` (last-method removal) are updated. Reported in gh-43 (passkey active but missing from the macOS PWA keychain, `LinkedAccounts.svelte:231` hides Add) and gh-45 (a Prince locked out of their Discord, `LinkedAccounts.svelte:174` hides Link). Context in `board/login-removal.md`.
- Drop the country from content-type community links: the editor asks it only for channel links, a content link stores none (moderation falls back to the owner's country) and takes the pinning NC's country when pinned national, cleared on unpin, refusing a national pin already held by another country — done when any NC can pin any content link into their card, the editor shows no country for content types, existing unpinned content links are nulled, and `wiki/architecture.md` (community links) and `wiki/access.md` (link-country scoping) are updated. Reported in gh-44 (a Prince read the required country as an audience restriction, `frontend/messages/en.json:1668`, `community_links.py:80`).
- Add a copy-as-text button to every read-only decklist, reusing `formatDeckText` (`social-text.ts:15`) so the clipboard gets the TWDA-style text deckbuilders import — done when `DeckDisplay` offers the copy on published finals decks, a member's record and a player's own deck, pasting into VDB's text import reproduces the deck, and it works offline. Reported in gh-46 (a judge on Android could only copy the rendered list, which VDB rejects; "Copy results" carries the winner's deck alone).
