# The game

Vampire: The Eternal Struggle — what a tournament tool has to model. This is not a
rules reference; it is the slice of the game the app touches. Source unless noted:
`reference/vtes-rules.md` (VTES 5th Edition rules). Full rules text and the
multilingual term set live in `reference/`.

## Shape of a game

Players are **Methuselahs** seated clockwise. Each has a **predator** (the player
to their right) and a **prey** (the player to their left). Influence is **pool**;
a Methuselah who runs out of pool is **ousted**. The game continues until one
Methuselah remains (§5).

Ousting your prey earns **1 victory point** and 6 pool; being the last Methuselah
standing earns an additional victory point. The winner is whoever holds the most
victory points, even if they were themselves ousted; a tie means no winner (§5).
When your prey is ousted, their prey becomes yours, and you become that player's
predator — so the ring closes and predator-prey relationships shift during play
(§5).

A player may also **withdraw** (advanced rules): having exhausted their library
and beginning a turn with less than a full hand, they announce the intent during
their unlock phase and succeed if they lose no blood or pool before their next
unlock phase. A successful withdrawal earns 1 victory point under the game rules,
and **the predator gets nothing** — no victory point, no pool. In tournament play
that award is reduced to half a victory point
([tournament rules §3.7.2](tournament-rules.md#scoring)).

Everything else — turn phases, combat, politics, disciplines, torpor, diablerie —
is invisible to the app. It matters only in that the app must never claim to
adjudicate it ([dogmas](../dogmas.md#product)).

## Deck structure

A deck has two independent stacks: the **crypt** (vampires, amber backs) and the
**library** (everything else, green backs).

Deck construction, per the rulebook's DECK CONSTRUCTION box (§1):

- crypt: **at least 12 cards, no maximum**;
- library: **between 60 and 90 cards**;
- any number of copies of a given card, within those limits — there is no
  four-of rule;
- each vampire belongs to a numbered **group**, and a crypt must be built from a
  **single group or two consecutive groups**.

The tournament rules restate the Standard Constructed sizes and add format-specific
limits — Limited minimums scale with the number of boosters, and Limited crypts
carry **no group restriction at all**
([tournament rules §6.2, §7.2.1](tournament-rules.md#formats)).

A card's identity for deck purposes is the printed card. The same vampire may
exist in several groups and in a base and **advanced** version, which is why the
app carries three name forms per card rather than one
([architecture](../architecture.md#cards-and-decks)).

## Vocabulary the app uses

The app's user-facing vocabulary is the game's own, and the official translations
are Black Chantry's, not ours — see [glossary](../glossary.md), whose per-locale
table is authoritative for UI copy, and `reference/game_terms.json` for the
official term set in EN/FR/ES/PT-BR/IT/JP/LATIN.

The terms that carry into tournament administration: **Methuselah** (a player),
**minion**, **predator** / **prey**, **oust**, **withdraw**, **victory point**,
**crypt**, **library**, **group**, **advanced**, **table**, **seat**.
