# Access

Who may do what. This is *authorization* — a separate axis from the *visibility*
levels in [sync](sync.md#access-levels), which compute what each viewer receives
from the same roles.

Every authorization rule lives once, as data, in `engine/src/permissions.rs`:
`CAPABILITIES` (what each authority takes) and `ROLE_APPOINTMENTS` (who may grant
each role). **A matrix change edits a row there and nowhere else.** The backend
(`permissions.py`, a thin marshalling adapter with no logic, each route keeping its
own 403 detail), the frontend (`lib/engine.ts`, UX-only and failing closed to
`false` until WASM loads) and the Discord bot are all callers. **No role literal
outside the engine may decide access**, and the backend remains the authoritative
enforcement point — checks run at both layers.

## Capabilities

Scope: **global** = anywhere; **own country** = the actor's `country` equals the
target's or the resource's, and the actor must have one; **organizer** = the actor
is listed on the tournament or league. IC holds every capability globally and is
omitted from the rows below.

| Capability | Who, besides IC |
|---|---|
| `sponsor_member`, `create_tournament` | NC, Prince — global (a visiting official can sponsor abroad) |
| `edit_member_profile`, `manage_vekn`, `mark_deceased` | NC — own country |
| `merge_accounts`, `delete_member`, `force_unlock_tournament`, `manage_promos`, `run_admin_sync`, `promote_link_global`, `set_archival_results` | nobody |
| `moderate_link`, `promote_link_national` | NC — own country |
| `organize_tournament` | NC — own country; explicit organizer |
| `manage_leagues` | NC — global |
| `edit_league` | NC — own country; league organizer |
| `issue_restricted_sanction`, `lift_restricted_sanction`, `modify_sanction`, `delete_any_sanction` | Ethics — global |
| `issue_tournament_sanction` | Ethics — global; tournament organizer |
| `lift_tournament_sanction` | Rulemonger — global; NC — the tournament's country |
| `lift_league_disqualification` | league organizer |
| `delete_organizer_sanction` | tournament organizer, while the tournament is unfinished |
| `record_promo_intake`, `view_full_promo_ledger` | NC — global (the inventory chain is not country-scoped) |
| `manage_oauth_clients` | DEV — global |

`moderate_link` and `promote_link_national` scope on the **link's** country, which
a `CommunityLink` carries as a field of its own defaulting to its owner's — so an
NC curates every link serving their country wherever its owner lives
([architecture](architecture.md#community-links)).

`set_archival_results` is IC-only rather than organizer, because the rows it
applies to have no real organizer: a TWDA reconstruction has none at all, and an
import's is whatever upstream claimed. Invalidation authority is IC's anyway (8.6).

Two rows carry a security rationale. `merge_accounts` is IC-only because a merge
**unions both accounts' roles** — anyone who could merge could land a role by
absorbing a shell account that carries it. `sponsor_member` is a single capability
covering both minting the member and issuing the VEKN ID — splitting them invited
the two halves to drift.

**Appointments** — NC grants **Prince** in their own country; PTC grants **PT**;
Rulemonger grants **Judge** and **Judgekin**; everything else is IC's. **A target
must hold a `vekn_id` to hold any role.**

Rules carrying a precondition the table cannot express keep a resolver beside it:
sanction level, tournament state, a target's own roles (`can_change_country`), and
the `open_to_country_princes` league flag.

**Two out-of-band consumers watch role writes**: the Discord Linked Roles push
fires on **any** role delta with no periodic reconcile, while the resync
fingerprint moves only for IC and NC. A role writer outside the users route skips
both silently.

## Authentication

Every method issues JWT access/refresh token pairs — short-lived access,
longer-lived refresh. OAuth tokens are a separate `oauth_access` type with scope
restrictions.

| Method | Notes | Key files |
|---|---|---|
| Email + password | register or login | `routes/auth.py` |
| Magic link | signup, password reset, invite; the link stays valid until the password is actually set, not merely verified | `email_service.py` |
| WebAuthn / passkeys | FIDO2; four endpoints — `register/{options,verify}` to add to an existing authenticated account, and `create/{options,verify}` unauthenticated to create a new user | `passkeys.svelte.ts` |
| Discord OAuth | `GET /auth/discord/authorize` with `mode=login|link` → callback; login matches by Discord ID or creates a user, link attaches the Discord ID to the authenticated user | `routes/auth.py` |
| GitHub OAuth | **link-only**, not a login method; stores `github_login`/`github_id` on User (full-only), used to @-mention a reporter on their feedback issue | `routes/auth/github.py` |

## OAuth2 provider

A full RFC 6749 / RFC 7636 (PKCE) implementation for third-party API access.

Endpoints `/oauth/{authorize,token,userinfo}`; client CRUD and secret regeneration
under `/oauth/clients` (DEV role); `GET /oauth/consents` lists authorized apps and
is **first-party session only**, rejecting OAuth tokens with 403;
`DELETE /oauth/consents/{client_id}` revokes consent and immediately revokes live
tokens for that client.

Scopes: `profile:read` (limited to `/oauth/*`) and `user:impersonate` (full API).

Security: PKCE S256 required, Argon2-hashed client secrets, refresh-token rotation
with a revocation chain, single-use authorization codes, consent persistence, and a
`revoked` flag on access tokens honored by the auth middleware.

There is no public read API on top of this — see
[dogmas](dogmas.md#product).

## VEKN identity

A `vekn_id` is what makes someone a member rather than a visitor: it is the gate
for the `member` access level, for holding any role, and for tournament
participation ([domain](domain/tournament-rules.md#eligibility-and-materials)).

A uid carrying a `vekn_id` is **never re-keyed and never soft-deleted** — the
immovable-uid invariant. Claim, sponsor, link, abandon, force-abandon, merge and
detach are all [architecture](architecture.md#account-surgery).

The `vekn_id` unique index has no `deleted_at` exclusion, so a soft-deleted user
still reserves its number while `deleted_at`-filtered lookups disagree — a seed
insert can therefore crash on a reserved number.

## Deployment gate

Production nginx proxies **only an allowlist of path prefixes** to FastAPI:
`/api`, `/auth`, `/oauth`, `/vekn`, `/sanctions`, `/admin`, `/snapshot`, `/stream`.
A new route under an existing prefix is fine; **a new top-level segment 404s in
production while passing dev CORS and tests**.
