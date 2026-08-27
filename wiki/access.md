# Access

Who may do what. This is *authorization* — a separate axis from the *visibility*
levels in [sync](sync.md#access-levels), which compute what each viewer receives
from the same roles.

Every authorization rule lives once, as data, in `engine/src/permissions.rs`:
`CAPABILITIES` (what each authority takes) and `ROLE_APPOINTMENTS` (who may grant
each role). **A matrix change edits a row there and nowhere else.** The backend
(`permissions.py`, a thin marshalling adapter with no logic, each route keeping its
own 403 detail), the frontend (`lib/engine.ts`, UX-only) and the Discord bot are
all callers. **No role literal
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
| `manage_nda` | PTC — global (request, upload, view and download playtest NDA records) |

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
Rulemonger grants **Judge** and **Sheriff**; everything else is IC's. **A target
must hold a `vekn_id` to hold any role**, and **granting PT requires an NDA on
record** ([architecture](architecture.md#nda-records)) — a grant, not a hold: a
target already holding PT is being revoked, so grandfathered holders (role
predates the NDA workflow) keep the role and stay revocable. The NDA fact lives
off `User`, so callers pass it into `can_change_role` explicitly (`has_nda` on
the target context, absent = false).

Rules carrying a precondition the table cannot express keep a resolver beside it:
sanction level, tournament state, a target's own roles (`can_change_country`),
the target's NDA record (PT), and the `open_to_country_princes` league flag.

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
| Discord OAuth | `GET /auth/discord/authorize` (`?link=true` attaches the Discord ID to the authenticated user) → callback; login matches by Discord ID or creates a user | `routes/auth/discord.py` |
| GitHub OAuth | **link-only**, not a login method; stores `github_login`/`github_id` on User (full-only), used to @-mention a reporter on their feedback issue | `routes/auth/github.py` |

**Password, passkey and Discord login honour `/login?redirect=<path>`** (magic
link never returns to `/login` and drops it) — same-origin paths only
(open-redirect guard), checked in the login page's `successTarget()` and
again at the Discord authorize ingress, which carries the path through the
OAuth state and back onto the callback's `/login` URL. The consent page sends
its own path and query there, so a third-party OAuth login — the Discord bot's
`login_hint=discord` links included — resumes the authorization after login.

**Magic-link lifetimes are per purpose**: 15 minutes for signup and password
reset, 7 days for an invite — its recipient did not ask for the email and has no
reason to be watching their inbox. Clicking any of them mints a separate
10-minute window to submit the password.

An expired or already-used link routes to `/login?recover=1`, the reset form under
wording that fits someone who has never had a password. That is the invited
member's way back in: a member created with an email address carries a contact
address and no email auth method, and the `reset` purpose creates the login on
exactly that basis. A one-click resend is not buildable — an expired transient
token is gone from storage, so the server cannot recover the address to resend
to, and for the same reason the page cannot tell which purpose the dead link
served. That is why its copy names the signup tab for the one case a reset
cannot serve: a signup link that expired before any account existed.

### The email of record

`contact_email` is the account's address of record, not an address the member
chose to publish — its name reads the other way round. It is what door-dedup
409s on, what the account merge carries to the survivor, what the `reset`
purpose recovers a login from for someone who never had a password, where the
invite is sent, and what the VEKN registry push submits, falling back to
`<vekn_id>@placeholder.vekn.net` when there is none. It becomes a published
address for exactly two roles: an NC's or Prince's row carries it into the member
projection in plaintext and into the public one base64-cloaked, a harvester
speed-bump rather than access control. Every other member's reaches only the
holder and full-access readers, and no `api` projection carries it at all.

**Case is folded at the lookup, not at the row, and the two lookups differ on
which.** `contact_email` is compared `LOWER()` on both sides in SQL, so a row
keeps whatever case its writer supplied and no caller has to think about it. An
email **auth method's** `identifier` is compared exactly, so it is lowercased on
every write and every reader must lowercase too — a hand-typed venue address
passed through raw finds no one.

A `+tag` subaddress is deliberately not canonicalized: this is the address we
actually send to and hand to the VEKN registry, so folding `a+vtes@x.com` to
`a@x.com` would aim that mail at a mailbox the member may not own, and would
turn two distinct people into one 409 at the door.

## OAuth2 provider

A full RFC 6749 / RFC 7636 (PKCE) implementation for third-party API access.

`/oauth/token` takes the RFC's `application/x-www-form-urlencoded` body or a JSON
body with the same keys, whichever the client sends. The JSON form came first and
the Discord bot still uses it; the form encoding is what every third-party OAuth
library reaches for, so refusing it made the endpoint non-compliant for exactly
the audience the daemon grant exists to serve.

`/oauth/authorize` answers with `{"redirect_url": …}` on every path that ends in a
navigation — consent already on file, approval, denial — and never with a 302. The
consent page holds a Bearer token, so it reaches the endpoint through `fetch`, and a
fetch cannot read `Location` off a redirect: `redirect: "manual"` yields an opaque
response whose header list is empty. While the auto-approve path returned a 302 the
page navigated to the empty string, which reloads the consent page, which calls
`/authorize` again — a returning user looped forever instead of reaching the app.

Endpoints `/oauth/{authorize,token,revoke,userinfo}`; client CRUD and secret
regeneration under `/oauth/clients` (DEV role); `GET /oauth/consents` lists
authorized apps and is **first-party session only**, rejecting OAuth tokens with
403; `DELETE /oauth/consents/{client_id}` revokes consent and immediately revokes
live tokens for that client, across every event it holds.

`POST /oauth/revoke` (RFC 7009) is how a client hands a pair back without sending
the user to their profile page. It takes the token itself rather than a jti, and
revokes the **whole rotation lineage** it belongs to — either half kills the other,
and a rotated chain dies with it. Expiry is not verified on the way in, so an
expired access token still names the live refresh sibling handed back with it.
Past client authentication every answer is 200 — unknown, malformed, expired or
another client's token alike — so the endpoint is no oracle for which tokens
exist; only a bad client secret (401) and a missing `token` (400) fail. Consent
survives: revoking tokens is not revoking the grant, which is
`DELETE /oauth/consents/{client_id}`.

Scopes: `profile:read` (limited to `/oauth/*`) and `user:impersonate` (one
tournament, below) delegate a *user's* authority; `api:read` delegates nobody's
and is refused at `/authorize` for that reason — it is the daemon grant's scope
and only that.

### Impersonation is per event

**`user:impersonate` is granted for exactly one tournament.** The authorize
request carries `tournament=<uid>` beside the scope, the consent page names the
event to the user, and the grant is stored and keyed on the triple
**(client, user, tournament)** — a returning user gets a one-click approve for
each new event and never a silent cross-event auto-approve. A token with the
scope and no tournament is refused outright; there is no unscoped regime.

The tournament rides the JWT as its **own `tournament` claim, never as a member
of `scope`** — the scope string round-trips through the `OAuthScope` enum on
refresh, and a uid is not an enum member.

**A grant dies with its event.** `/authorize` refuses a `Finished` tournament and
refresh refuses one too, so the relationship ends structurally rather than by
anyone remembering to revoke. Within the last access token's hour the actor could
otherwise revive the event, so `ReopenTournament` is barred for OAuth actors;
every other action the engine already state-gates.

`DELETE /oauth/consents/{client_id}` revokes the app, meaning **every** event it
was granted; `GET /oauth/consents` answers one row per event, and the profile
page folds them into one card per app.

**`/oauth/authorize` is first-party session only**, both verbs, like the consent
endpoints and for the same reason: `/oauth/*` is otherwise reachable with a
scoped token, so a client could POST its own approval for a second event and key
itself a consent no one ever saw a page for.

#### The allowlist

Enforcement is an **allowlist**, in `middleware/auth.py`: a route added anywhere
else in the app is refused until it is named here.

| Reachable | |
|---|---|
| `/oauth/*` | the grant's own lifecycle |
| `/api/tournaments/<the token's uid>/…` | minus the barred sub-routes below |
| `POST /sanctions/` | body `tournament_uid` must equal the token's — a path gate cannot see a body, so the match is in the handler |
| `GET /sanctions/reference` | engine-owned, public anyway |
| `/stream?tournament=<the token's uid>` | the scoped stream, [sync](sync.md#the-sse-endpoint) |

Everything else 403s — `/snapshot` and the unscoped `/stream` above all, which
would hand a third party the granting organizer's whole corpus, private decks
included. `POST /vekn/claim` matters as much: it answers with a **first-party**
token pair for the merged uid, so reaching it turns a delegated grant into a
full session.

**Barred inside the token's own tournament**, whatever the user may do: delete,
`organizers` add/remove, `push-vekn`, and the offline-lock family (`go-offline`,
`go-online`, `force-takeover`, `force-unlock`, `sync-offline`). These are the
infrastructure of owning an event, not of running one.

`GET /api/tournaments/{uid}/decks` is the delegated read a play platform needs
once a round starts — [sync](sync.md#delegated-third-party-reads).

Security: PKCE S256 required, Argon2-hashed client secrets, refresh-token rotation
with a revocation chain, single-use authorization codes, consent persistence, and a
`revoked` flag on access tokens honored by the auth middleware.

### The daemon grant

`grant_type=client_credentials` on the same `/oauth/token`, for a third party with
no user to act for. The client authenticates with its own secret and gets a
one-hour `oauth_client` JWT carrying `client_id` and `api:read` — and **no
`oauth_tokens` row**, deliberately: that record's `user_uid` is non-optional and
the app's middleware unconditionally resolves a User from a token, so the type
never touches either. The main app rejects an `oauth_client` token by
construction — it knows two token types and this is neither — and the
[public API](public-api.md#auth) accepts it, checking the client's `active` flag,
which is therefore the whole of revocation. There is no refresh token: mint
another.

A client registered for `api:read` alone needs no `redirect_uri`, since it never
sends a browser anywhere. The public API also accepts a user's `oauth_access`
token, at any scope and with the same answer — a user token is attribution, not a
different permission.

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

The public API's vhost is a second, tighter allowlist of the same kind, and a new
streaming route must be named in it or it is throttled as a single-row lookup —
[public-api](public-api.md#deployment).
