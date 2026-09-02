Doc-impact: `wiki/tournaments.md` — a Storyline row in the config table, the
"Restricted format is not modelled" paragraph amended to say the exception now
made for storylines, `ranking_eligibility` gaining the format, and the Hall of Fame
predicate gaining it. `wiki/vekn.md` — the event-type
mapping line, the push map, and the TWDA skip. `wiki/architecture.md` — the deck
validation paragraph, which must say Storyline has no decks rather than lax ones.
`wiki/domain/tournament-rules.md` — the storyline domain facts below, which the
page does not yet hold. Not `wiki/glossary.md`: format names are untranslated
option literals. Not `wiki/sync.md` or `wiki/public-api.md`: `DeckObject` is
unchanged.

## What a storyline is

Official VEKN Storyline Events are worldwide narrative events whose results feed an
ongoing World of Darkness plot. They run under constructed tournament rules **plus**
per-storyline special rules — a 75%-single-clan crypt is the recurring one — carry
**custom promo cards minted for that storyline**, and often add adversaries, reward
mechanics and a two-hour cap. The tournament rules glossary lists them under
**Premier Events**; the Judge's Guide §3.1.3 names storyline events as its example
of *events where decklists are not used*. Sources:
<https://www.vekn.net/storyline-events/official-storyline-events>,
`reference/tournament-rules.md` (glossary, Premier Events),
`reference/judges-guide-v2.md` §3.1.3.

That last fact is why this line removes decklists rather than loosening validation.

## The decision this changes

`wiki/tournaments.md` records that card-set restrictions (§6.1.1) and the Restricted
format (§7.9) are not modelled, such events being entered as Limited. The VEKN
import applies that to storylines today. This line makes storylines the exception;
Restricted and set-restricted events stay as they are. The bar is the same page's
`No Grand Prix rank, deliberately` precedent — a category must earn more than a
label. Storyline earns the decklist removal, the ratings and badge exclusion, and a
faithful upstream round-trip.

## Upstream already has it

`backend/src/vekn_tournament_sync.py` maps **event type 9 = Storyline** onto
`(Limited, Basic)`, and `vekn_push.py`'s reverse map has no entry for it. Owner
accepted both directions: import `9 → Storyline`, push `(Storyline, Basic) → 9`.

Measured on the dev database (2026-09-02, 8277 tournaments): four tournaments name
"storyline", all filed Limited, dated 2014, 2015, 2020 and 2022 — every one outside
the 18-month rating window, against 614 Limited events total. The sync rewrites
`format` on an existing row when it differs, so reclassification happens on the next
calendar pull with no backfill and no rating recompute. We do not store
`eventtype_id`, so a name match is a bound rather than a census; it bounds the
affected set at single digits of pre-window events. No `wiki/post-deploy.md` item.

## Where the work actually lands

`UpsertDeck` (`engine/src/tournament/mod.rs:2439`) is the single submission entry
point — one refusal covers every path. The form drops `decklist_required` and
`decklists_mode`; `PlayersTab.svelte` gates its deck affordances on
`decklist_required || isOrganizer`, so the organizer's own upload path needs the
same gate. Format options are hardcoded in `TournamentFields.svelte`,
`tournaments/+page.svelte`, `leagues/new` and `leagues/[uid]`.

`decklist_required` must be false under Storyline **in the engine**, not merely
absent from the form: `UpdateConfig` takes it from the public API too, and
`mod.rs:579` and `mod.rs:733` set `missing_decklist` on every player when it is
true with no deck on file — on a format that accepts no deck, that strands
check-in with no way to clear it. Ignore the field or refuse it; ship's call.

`ranking_eligibility` is the one exclusion that is **not** free: it also drives the
ranked/unranked badge and the RtP column, so an 8-player Storyline event with a
final would render "ranked" while earning nothing. Ratings are free —
`backend/src/ratings.py` selects by an explicit format list.

The Hall of Fame and the TWDA push look free — both need a live winning
`DeckObject`, which a Storyline event created as one never has — but the
format-switch edge below breaks that: a finished Standard event with a winning deck
switched to Storyline has `format` distinct from `'Limited'` and a live deck, so
`db.py:1278` counts it and the TWDA push does not skip it. An imported type-9 event
carrying a deck is the same exposure. The **Done when** promises no Hall of Fame
count, so this must be closed, not assumed: add `Storyline` beside `Limited` in the
Hall of Fame predicate and the TWDA skip — two conditions, against a lock on the
format switch, which would be a new rule. Revisit when organizer-authored custom
cards bring decklists back.

`rating_category`'s `_ => true` arm would call Storyline constructed. Unreachable
from `ratings.py`, but exported over both PyO3 and WASM. Ship decides whether that
latent trap is worth a branch.

## Edge resolved, not locked

`UpdateConfig` can change `format` in any state, so a tournament holding decks can
become Storyline. Existing decks stay visible and stop being editable — no new lock,
recorded in the wiki. This is the edge that costs the Hall of Fame and TWDA
exclusions their free ride, above.

## Out of scope

Organizer-authored custom cards, and any decklist that could name them. The owner
scoped decklist removal as the interim precisely because unknown-card persistence
would need a `DeckObject` field and is likely temporary.
