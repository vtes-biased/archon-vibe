# Wiki

What Archon is and what was decided. A manifesto of *what is*, not a journal of how
it came to be. Every page is reachable from here.

Work owed lives in [`BOARD.md`](../BOARD.md), not here. A line that cannot be
completed is documentation and belongs on a page below.

## Start here

- [product](product.md) — scope, who it is for, what it does and deliberately does
  not do.
- [dogmas](dogmas.md) — the human-chosen paradigms. Ingress and egress check
  against this page.
- [glossary](glossary.md) — the vocabulary no generic tool knows, including the
  per-locale term table.

## Domain

Standing knowledge of the environment the product operates in, compiled from the
official documents in `reference/`. Every claim names its source. These pages have
no code to lint against: check their sources instead.

- [domain/vtes](domain/vtes.md) — the game, scoped to what a tournament tool must
  model.
- [domain/tournament-rules](domain/tournament-rules.md) — the VEKN tournament
  rules the app implements.
- [domain/judging](domain/judging.md) — the Judge's Guide penalty system.
- [domain/vekn](domain/vekn.md) — the organization, its ratings system, its ethics
  process, and the external systems we interoperate with.

## The product

- [tournaments](tournaments.md) — how the rules are implemented, the engine event
  catalog, and where the app knowingly diverges from the rules.
- [architecture](architecture.md) — stack, data model, database access, the engine,
  and every subsystem's mechanics.
- [sync](sync.md) — access levels, SSE, the cursor, resync, snapshots, IndexedDB,
  and the offline lifecycle.
- [access](access.md) — capabilities, appointments, authentication, the OAuth2
  provider.
- [public-api](public-api.md) — the read-only `/v1` API for third parties: its
  endpoints, its JSON Lines streams, and the lint that keeps it apart from the app.
- [vekn](vekn.md) — push, pull, TWDA, and the legacy archon sync.
- [vekn-decommission](vekn-decommission.md) — work deferred until the VEKN syncs
  retire, with the evidence that cannot be reconstructed afterwards.
- [post-deploy](post-deploy.md) — the actions a production deploy unlocks, each
  gated on the commit that makes it safe. Empty is the normal state.
- [discord](discord.md) — Linked Roles and the tournament bot.
- [design](design.md) — the pinned visual system.
- [i18n](i18n.md) — the five locales, conventions and per-locale traps.

## Working on it

- [dev](dev.md) — setup, commands, configuration, deployment, library docs.
- [testing](testing.md) — layers, how to run them, and the traps that have bitten.
- [hazards](hazards.md) — non-local traps. Read before touching the subsystems it
  names.
