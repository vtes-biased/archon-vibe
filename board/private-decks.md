Doc-impact: `wiki/tournaments.md` — the event catalog gains `SetDeckPrivate`, "Who
may do what" gains it, the post-finish publication pass paragraph gains private as
an input with the winner exception, and the profile paragraph. `wiki/product.md` —
the visibility paragraph gains its companion sentence: the decklists mode is a
display default, private is an access boundary. `wiki/public-api.md` — the
publication contract paragraph, and the deferred TWD opt-out item narrowed to what
this leaves. `wiki/vekn.md` — one sentence: a private deck never reaches the TWDA
because the winner is excepted. `wiki/architecture.md` — the DeckObject field list.

Not `wiki/sync.md`: the deck row of the projection table reads "full data when
`public = true`, else none", and that rule is unchanged — private changes what sets
`public`, not what `public` means. Not `wiki/post-deploy.md`: a new flag defaulting
false migrates nothing and re-projects nothing.

Owner decisions, September 2026: private is added beside anonymous, not in place of
it — anonymous is a credit boundary and private a disclosure one, and an anonymous
deck still feeds the archive; the winner's deck publishes regardless; the toggle
lives on a deck already submitted, never on the upload form.

## Why it is not folded into the attribution line

They look adjacent and are not. Attribution's weight is the projection boundary and
the production migration — `compute_deck_member` and `compute_deck_api`
(`access_levels.py:220-230`) learn to drop `user_uid`, stored rows move, published
decks re-project. Private touches none of that: those two functions already gate on
`public` alone, so forcing a deck out of publication needs no projection change at
all. The overlap is one field on each payload builder and a sibling event.

Two events rather than one widened one, and two fields rather than a combined
disclosure enum: credit and disclosure are causally unrelated, and similar-looking
unrelated code stays repeated ([dogmas](../wiki/dogmas.md)). They compose — a deck
can be anonymous and public, named and private, or both.

Land after the attribution line all the same: it rewrites the deck panel this
toggle sits on and the two payload builders this field rides.

## The mechanics

`compute_deck_public` (`engine/src/tournament/helpers.rs:271`) takes the tournament
and a `player_uid` and never looks at the deck row, so it cannot see a per-deck
flag today. Its caller `recompute_deck_publication` already holds the deck `d` in
the closure, so the predicate becomes deck-aware by signature and one condition —
private forces false except where `tournament[WINNER] == player_uid`, a test the
function already performs in both its other branches. The winner exception is
therefore free: no stamped flag, nothing for the projections to learn.

The flag must ride **both** decks-payload builders — `_build_decks_json`
(`backend/src/routes/tournaments.py:137`) and `buildDecksPayload`
(`frontend/src/lib/engine.ts:213`), each passing `user_uid`, `round`, `uid`,
`public` today ([hazards](../wiki/hazards.md#two-implementations-of-one-gate)). The
attribution line adds a field to the same two functions; expect to arrive second.

`SetDeckPrivate { player_uid, round, private }`, in the shape
`SetDeckAttribution` establishes: owner or organizer, any state, keyed on the
deck's round, no content change.

Two paths already exist and need nothing new. **During play nothing is shared** —
`compute_deck_public` returns false off a `Finished` state — so private only bites
post-finish. **Retraction is the pass** — any action on a Finished event runs
`recompute_deck_publication`, so marking an already-published deck private emits
`set_public false` and tombstones it at the levels that lost it
([sync](../wiki/sync.md#access-levels)).

## The fired trigger

`wiki/public-api.md` parks *"User-level TWD opt-out — a member asking not to have
their name or deck in the TWDA. Trigger: a member asks."* This ask fires it and
does not consume it: that item is member-level and standing, covers the name as
well as the deck, and this line explicitly excepts the winner — which is the only
deck the TWDA ever holds. Narrow the item to that residue rather than deleting it.
