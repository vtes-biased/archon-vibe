# Deck round stamp

Doc-impact: `wiki/tournaments.md` (the never-remove-mid-array rationale, and the
`UpsertDeck`/`DeleteDeck` entry in the Decks event list), `wiki/sync.md` (the
delegated-read paragraph — the per-player translation goes away), `wiki/hazards.md`
(the four-implementations entry shrinks: the count keeps deciding the open-rounds
cap but stops deciding deck slots), `wiki/product.md` ("multideck per-round
locking"), `wiki/post-deploy.md` (the stored-deck rewrite is a stored-value
migration, and `just migration-pairing` fails without a proof section).

## The defect

`DeckObject.round` is not the tournament's round index. It is a per-player slot,
assigned at upload from `count_player_rounds_played` — which **skips `Cancelled`
tables**. A mid-array `CancelRound` is a soft-cancel, so the count drops and every
later slot shifts by one.

Rounds 0, 1, 2 played; cancel round 1. The player's count goes 3 → 2, and:

- the delegated deck read answers their round-1 deck for round 2;
- `is_deck_locked` re-opens a deck they already played, which corrupts §3.1.5a's
  **Best-Performing Deck** method — it ranks preliminary decks by the score each
  actually earned, so a deck editable after the fact is not the deck that scored.

An *immediate* cancel is harmless: the slot slides to the player's next game,
which is what §3.1.5 free swapping already allows. Only cancel-after-later-rounds
misattributes.

## Decisions (owner, 2026-08-27)

- **Stamp at seating, not at upload.** A deck carries no round until the player is
  seated; the engine stamps the tournament's round index at `StartRound` and
  `SelfOrganizeRound`, and clears it when a tail `CancelRound` removes that round.
- **"Locked" becomes "stamped"** — a stamped deck is played and immutable, a
  pending one is editable. The count arithmetic in `is_deck_locked` goes away.
- **No round uuid.** Index stability is already an engine invariant maintained by
  construction: mid-array cancels are soft, hard removal is tail-only, and the
  cascade pops only trailing rounds, so nothing below ever shifts. A uuid would be
  a second identity system to thread through sanction validation, SA resolution,
  seating history, frontend labels, offline sync and every projection. Revisit only
  if something ever reorders rounds; nothing does.
- **No re-indexing on cancel, for either kind.** Sanctions are solved twice over —
  soft-cancel preserves the index, and `resolve_sa_effective_rounds` re-resolves to
  a seated round per JG §1.1.3 even when the stored one dies. Under stamp-at-seating
  decks inherit the same stability, and the only writer needed is the un-stamp on
  the tail hard-remove path.

## Why the "must be per-player" argument does not survive

The index has to be per-player only while it is assigned at upload: a deck is
uploaded before the round it will be played in exists, and `SelfOrganizeRound`
creates each pod already `In Progress`, so there is no window in which a
globally-indexed deck could be named. Null-until-seated removes the constraint
entirely — the pending deck needs no index, and by the time one exists the round
does too.

## Shape

- `DeckObject.round` keeps its type (`int | None`) and changes meaning: the
  tournament's round index once played, null while pending or when it is a
  single-deck event's registered deck. The finals is `len(rounds)`, as
  `Sanction.round_number` already uses it.
- Engine stamps on seating and clears on tail cancel, through the existing
  `deck_ops` side-effect channel (`ReopenTournament` already emits deck ops).
- `is_deck_locked` and its `count_player_rounds_played` call go; the per-player
  count survives only for the open-rounds cap.
- Frontend renders slots from stamps plus the one pending slot, rather than sizing
  from `roundsPlayed`.
- `_deck_slot` in the tournaments route is deleted; the delegated read keys the
  ongoing round index directly.
- **Migration**: rewrite stored `deck.round` from the player's i-th counted round
  at migration time. Multideck events only — a single-deck event's registered deck
  stays null.
