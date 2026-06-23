# Proxy player support (judges-guide §5.1.1)

## Concept
A **proxy player** is a registered participant who is stood in for by a non-competing
tournament official playing a **random deck from the officials' stock of competitive decks**
(not the official's own). Rare, large multi-judge events.

Behaviour:
- The seat **plays normally**: opponents score VPs against it and it participates in
  oust-order validation (`check_table_vps`). VPs ARE entered for the seat during scoring —
  the scoring flow is unchanged.
- The proxied player is **excluded from standings rank, rating (RTP), and finals/qualification**.
- Their score is **shown, not zeroed** (the VPs are real for oust-order / table-sum checks),
  but they hold no rank and earn no rating.

This is structurally the **disqualified-player pattern** (seat counts for opponents, person
excluded from rank/rating, rendered rank `—` and muted) — differing only in:
- benign, not punitive → **neutral** badge (not the crimson DQ treatment);
- score is **not zeroed** (DQ zeroes; proxy keeps the real VPs).

## Data model
- New boolean **`non_competing`** on `Player` (per-tournament roster record).
  - Internal name is `non_competing` (NOT `proxy`) to avoid colliding with the existing
    `Tournament.proxies` field, which means *proxy cards allowed* — a different concept.
  - **UI label is "Proxy"** (the guide's word; card-proxy confusion is a non-issue in the UI).
  - Mirror the field across all three layers: Rust `Player` struct → PyO3/backend
    `models.py` Player → frontend `types.ts` Player. Carry it onto `StandingEntry` too so the
    badge/rank logic needs no roster lookup.

## Engine (Rust — owns the exclusion, fail-closed)
- **Standings** (`standings.rs` `update_standings`): a `non_competing` player gets no rank
  (like `disqualified`), sorted to the tail with DQ'd entries, but **keep their gw/vp/tp**
  (do not zero). Their VPs still feed opponents' scores / table validation as today.
- **Rating**: the RTP computation must early-return 0 for `non_competing` (same guard as DQ).
- **Finals**: excluded from finals seeding/qualification candidates and from the top-5 /
  tie logic (they are not in the ranked field).
- **Toggle action** (new): set/clear `non_competing` on a player. Mirror an existing simple
  per-player mutation (`SetPaymentStatus`). Organizer-gated.
- **State guard** (engine-enforced, `SetNonCompeting` handler): **blocked once finals are
  seeded (`finals != null`) or the tournament is Finished** — so a proxied↔competing flip
  can't rewrite a concluded result. Toggling mid-prelim is allowed (and is the use case: a
  no-show stood in for by an official partway through) — standings are recomputed each event,
  so it stays consistent. UI mirrors via `canSetProxy` (disables the toggle), but the engine
  is the source of truth (`CannotSetNonCompeting`).

## Deck / decklist
- A proxy plays a random stock deck handled by officials out-of-band — **no decklist is
  submitted in-app**. `decklist_required` has **no engine enforcement** (frontend-only gate),
  so no special handling is needed; the deck cell just renders a "🎲 Random" hint instead of
  "no deck". Decklist-required does not block seating a proxy.

## UI (frontend) — PlayersTab action-row refactor + read-only indicator
The proxy toggle rides a small refactor of the per-player organizer action surface, agreed
because the inline row was already saturated (payment, deck, check-in, drop, sanction).

- **Inline row keeps only the high-frequency core**: payment · deck · check-in/out · **More**.
- **"More" drawer** holds the rare/destructive tail, frequency-ordered:
  - **Drop player** and **Issue sanction** lead (as buttons);
  - **Proxy** is a small, demoted toggle at the bottom (dashed divider, an (i) info affordance
    + a one-line tip carrying the §5.1.1 explanation).
- **Desktop** (table layout): the action cell shrinks to `Check out · More`; "More" reuses
  the existing full-width expand row (`colspan`) that the deck icon opens, via a
  `mode: 'deck' | 'manage'` flag (deck icon → deck content, More → manage panel).
- **Read-only "Proxy" badge** wherever the player appears seated:
  - PlayersTab rows + standings: neutral badge (`badge-slate`/`bg-surface-active text-ink-muted`,
    NOT crimson), rank `—`, muted row, score shown (not zeroed).
  - RoundsTab seat rows (`seatDisplay` area) and the print path (`printSeatHtml`) so printed
    seatings annotate it too. **No toggle in RoundsTab — display only.**
- `AddPlayerForm` is **unchanged** (deliberately — protects the common add-player path; proxy
  is set after the fact on the roster row).

## Standings presentation
Show the proxy (do not hide — avoids "where did my judge go?"); rank `—`, score muted but not
zeroed, sorted to the tail alongside DQ'd entries, zero rating. Reuses the DQ row treatment
with the neutral badge color.

## i18n
New strings (×5 locales via `i18n-translator`): proxy badge label, the "More" trigger, the
proxy toggle label, and the §5.1.1 tip ("Stood in for by a non-competing official playing a
random deck from the officials' stock of competitive decks. VPs count for opponents, not
standings/rating.").

## Files touched
- Rust: `Player` struct, action enum + handler, `standings.rs`, rating, finals/top-5 logic.
- Backend: `models.py` Player, action routing (`routes/tournaments.py`), `access_levels.py`
  (ensure `non_competing` is projected to member/full as appropriate).
- Frontend: `types.ts` (Player + StandingEntry), `tournament-utils.ts` (`computeStandings`
  tail-sort + carry flag, rating guard, finals/top-5 exclusion), `PlayersTab.svelte` (row
  refactor + More drawer + badge), `RoundsTab.svelte` (read-only badge + print), `engine.ts` /
  `tournament-actions.ts` (new action), messages (i18n).

## Open verification (before/while building)
- Confirm the exact §5.1.1 wording for the random-deck mechanic if the guide phrasing differs.
- principal-engineer review = build gate (data model + engine + WASM pipeline).
