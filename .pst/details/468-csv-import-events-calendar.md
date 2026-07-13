# CSV bulk-registration + The Events Calendar sync exploration

## Shipped: CSV import (2026-07)

`POST /api/tournaments/{uid}/bulk-register` + `CsvRegisterModal` (ActionBar → More,
Registration state only). Rows match by VEKN ID first, then email (the #413 dedup
keys); matches register through the engine (`AddPlayer`, then `SetPaymentStatus`
Paid — default on, per-row `paid` column override) under one row lock, one save,
one broadcast. Unmatched rows (`not_found` / `no_vekn_id` / `duplicate_row`) and
engine rejections (suspension/league-DQ barriers) are returned and listed in the
modal for resolution through the normal officials-only sponsor/create desk flow —
never silently created. Client-side minimal RFC4180 parser; header row required;
column aliases: `vekn_id|vekn`, `email`, `name|player|attendee`, `paid|payment`.
Cap 500 rows.

## Explored: The Events Calendar / Event Tickets pull (EC 2026 uses it)

**What the plugin stack exposes.** The Events Calendar (free) ships a public REST
API at `/wp-json/tribe/events/v1/…` — events, venues, organizers. Attendee data
lives in the **Event Tickets** plugin family; its REST surface
(`/wp-json/tribe/tickets/v1/attendees`) carries per-attendee name/email + ticket
meta, and requires authentication for non-public fields (WordPress Application
Passwords over HTTPS Basic auth is the plugin-recommended path; per-site key).

**Assessment.**
- Feasible as a *fetcher producing the same row shape the CSV path consumes*:
  attendee name + purchaser email map 1:1 onto `BulkRegisterRow{name, email,
  paid=true}`. VEKN IDs would only be present if the ticket form collects them
  (custom attendee field — worth requesting from championship organizers, since
  email-only matching is weaker).
- Refreshable: re-pulling and re-posting is naturally idempotent — bulk-register
  skips `already_registered`, so a nightly/on-demand re-sync only adds newcomers.
- Frictions: per-event WP credentials (application password) must be provisioned
  and stored (ansible-vault, runtime path, like the officials-contacts pattern —
  never committed); attendee-field shape varies with the ticket provider
  (Event Tickets vs Event Tickets Plus vs WooCommerce tickets), so the fetcher
  needs a per-site mapping config; and rate/format drift on a third-party
  WordPress is a support burden close to an event.

**Recommendation.** CSV now (shipped) covers the flow — every ticketing platform
exports CSV, including Event Tickets' own attendee export, so the WP API pull is
an optimization, not a gap. Revisit as a small backend fetcher (server-side pull
→ reuse `bulk_register` internals) if EC 2026 organizers ask for live re-sync
during the registration window; verify the exact attendee endpoint + auth against
the real EC site before building (the REST details above are plugin-doc knowledge,
not tested against their install).
