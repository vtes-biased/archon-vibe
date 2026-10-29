# League final

Doc-impact: `wiki/product.md` (Leagues — replaces "rank-1 Champion crowning"),
`wiki/glossary.md` ("league final", five locales), `wiki/tournaments.md` (the
finals scoring now also scores a league final).

## Why on the league, not a tournament

A typical league final is a single 5-player finals table seeded from the league
standings, with no preliminaries. The tournament console cannot host it:

- `StartFinals` refuses under two played rounds (`FinalsMinRounds`) and seats
  the top five of the tournament's own preliminary standings.
- A one-round, one-table event finished without a final sets no winner
  (`FinishTournament`; owner-approved rules-literal stance in
  `wiki/tournaments.md`), scores the table as a preliminary (no seed
  tiebreak), and would be rated and pushed to vekn.net.

Owner chose the league-owned final over a finals-only tournament kind or a
hand-set champion.

## Shape

- Seat: top five of the league standings, seed order = league rank. Ties at
  fifth need a resolution — mirror the tournament toss rule or let the
  organiser order them; decide at ship time.
- Score with the engine's finals table scoring (`score_table` with
  `seed_order`), so GW/VP ties break by seed as in a tournament final.
- Champion: the final's winner when one was played, else standings rank 1.
- The league standings themselves are unchanged by the final.

## Context from the report

"Appalachian Assault" (US, GP mode) was finished on 25 October with the
standings leader crowned; its organiser expected the league final's winner.
The tournament form only lists unfinished leagues
(`TournamentFields.svelte`), which is why the final could not be attached
after Finish. Once shipped, the GitHub reply tells them to clear the finish
date, play the final on the league page, and finish again.
