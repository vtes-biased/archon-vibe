Doc-impact: `wiki/architecture.md` — the DeckObject field list. `wiki/tournaments.md`
— the event catalog gains `SetDeckAttribution`, "Who may do what" gains it, the
profile paragraph and the decks section state the boundary and the Finalists rule.
`wiki/vekn.md` — the designer-credit paragraph resolves from the typed field.
`wiki/public-api.md` — the deck fields and the contract paragraph: no owner on an
anonymous deck, member credits only. `wiki/sync.md` — the deck row of the projection
table and the "What members actually receive" boundary table. `wiki/product.md` —
the profile sentence and the decks capability. `wiki/post-deploy.md` — the row
migration and the re-projection.

Owner decisions, September 2026: anonymous is a boundary, not a display convention;
attribution is its own typed field with its own owner-only event; the winner is
always named, an anonymous finalist is not.

## The typed credit

Today `(author, attribution)` are two loose strings written by three UI modes
(`DeckUpload.svelte:190-213`, `DeckDisplay.svelte:118-142`): `attribution` holds a
VEKN id, a name (`selectAttrUser` falls back to `user.name`), free typed text, the
`"twda"` sentinel or null; `author` is the display name. `DeckUpload` reimplements
the radio group and autocomplete that `AttributionPicker.svelte` already provides
and the two have drifted. `model.rs:130-139` shows the engine never sees
`attribution`.

One typed field replaces both: anonymous, the owner, a member by VEKN id, a named
non-member, or the archive. Display names resolve at render time from the user
store for members; a named non-member and an archive entry keep their text. The
`api` projection carries member credits only — a free-text name never reaches
`/v1`, which is the contract `public_api/main.py:194` states and
`DECK_API_EXCLUDE` (`access_levels.py:217`) fails to honour today;
`test_access_levels.py:581-585` asserts the current leak and is rewritten. The TWDA
credit resolution at `routes/tournaments.py:368-377` and the import at
`twda_import.py:431` (`attribution="twda"`) move to the type.

Migration of stored rows, parked on the post-deploy page: null → anonymous,
`"twda"` → archive, the owner's own VEKN id → owner, another member's id → member,
anything else → named non-member.

## The event

`SetDeckAttribution { player_uid, round, attribution }`: owner or organizer, any
state, no content change, keyed on the deck's round like the upload. It is the
only way attribution moves; `UpsertDeck` keeps carrying it for a first upload.

## The boundary

The member and api projections (`access_levels.py:222-233`) drop `user_uid` when the
credit is anonymous, the winner's deck excepted — the winner stays named, which is
the TWDA's stance already. The predicate needs the winner, which the deck row does
not carry, so the engine stamps a flag beside `public` (feed it the credit kind:
`_build_decks_json` at `routes/tournaments.py:134` and `buildDecksPayload` at
`frontend/src/lib/engine.ts:213` pass `uid`, `user_uid`, `round` only) and the
post-finish pass from the deck-record line recomputes it. Land that line first.

`entitled_level` (`broadcast.py:130`) keeps answering full to the owner from the
full row, so the owner and organizers still hold everything.

Client side, an anonymous deck arrives with no owner: the IndexedDB dedup key
(`db.ts:972-985`) and the grouping in `PlayerDecksSection.svelte` key on `user_uid`
and must key such decks on the deck's own uid; `PlayerRecord.svelte:29-36` finds
decks by owner and so lists none of another member's anonymous decks without a
new rule. In Finalists mode, `showIdentity` (`PlayerDecksSection.svelte:362`) names
every finalist today; it names the winner and no anonymous finalist.

Re-projection in production: every published anonymous deck already sits in member
stores with its owner. A re-save of all deck rows recomputes the projections and
broadcasts the new frames, which replace the old rows by uid. The same pass can
retire the retraction item already parked on the post-deploy page.
