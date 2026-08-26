# Tournament creation wizard

Doc-impact: `wiki/product.md` (organizer flow), `wiki/design.md` (wizard
pattern); `wiki/tournaments.md` only if a payment-tracking flag is introduced.

## Shape

A guided flow in front of `frontend/src/routes/tournaments/new/+page.svelte`:
"what kind of event is this?" → branch questions → a prefilled configuration
plus inline guidance for the steps the app cannot automate. The plain form
stays reachable for organizers who know what they want.

## Decision tree (owner's outline, 2026-08-26)

**Online**
- official VTES Discord? → bot is already there, guide event setup
- other Discord? → give the link, guide bot installation (skip if installed)
- multideck? decklists required?
- sync event: one round after the other, all players present, advise resetting
  check-in between rounds
- async event: multiple rounds in parallel (JOL-style)
- long event: open rounds, spans weeks, join-whenever; option self-organized
  rounds

**Real-life**
- normal small size: prior registration optional, check-in and pay at the gate,
  seat and play; guide adding a late arrival to round one; timer optional
- multideck? decklists required?
- paid or free? → whether to surface payment tracking; if a third-party payment
  app is used, point at the paid-registrations CSV import
- advise organizers to collect decklists by VDB QR-code scan; encourage advance
  registration + decklist upload
- offline venue known in advance? → guide activating offline mode
- big event: upload CSV of paid registrations, QR-code self-check-in at the
  venue, configure rooms
- long-running open-round event: parallel rounds, self-organized games

## Exists vs. new

Everything the tree branches on already exists: multideck, decklists mode,
`open_rounds`, `self_organized_rounds`, `table_rooms`, QR check-in, offline
mode, Discord bot, per-player payment status (`SetPaymentStatus`/`MarkAllPaid`),
live announcements, and the paid-registrations CSV import
(`CsvRegisterModal.svelte` → `POST /{uid}/bulk-register`: VEKN id first, email
last resort, unmatched rows returned for hand resolution, max 500 rows,
Registration state only). New is the wizard flow itself and the guidance copy.

Small folded improvement: widen the import's `HEADER_ALIASES` so the VEKN
column also matches `vekn #`, `vekn#`, `vekn number`.

## Owner decisions to surface during the work

- Payment tracking has no config-level on/off flag today — per-player status is
  always there. Does "paid or free?" become a persisted flag (hiding the paid
  column on free events) or wizard-only guidance?
- A better name than "league" for the long-running open-round real-life
  archetype, to avoid confusion with actual leagues (`/leagues`).
