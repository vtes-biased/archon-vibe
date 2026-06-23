# #307 — Tier anonymous vs account vs VEKN-member access

## Problem

Three tiers are intended but only two exist on the wire:

| viewer | wanted | today |
|---|---|---|
| not logged in (anonymous) | community + content links ONLY | **public** projection |
| logged in, no `vekn_id` | the current "public" experience (officials directory, local community, contact) | **public** projection (identical to anonymous) |
| VEKN member (`vekn_id`) | member projection (members list, …) | member |

`broadcast.entitled_level`: `no viewer → public`; `viewer.vekn_id → member`; **else → public**.
So a bare account is byte-identical to anonymous, and "you need an account to see X"
is not expressible today.

Worse, the `public` projection already exposes officials to anonymous viewers
(`access_levels.compute_user_public`):
- NC / Prince → public fields **+ contact_email + contact_phone** + community_links
- IC → public fields + community_links
- any community-link holder → minimal fields (country, roles, links), no name

→ anonymous viewers currently receive NC/Prince contact emails/phones on the public
SSE stream and in IndexedDB. A frontend-only gate does **not** fix this (data still on
the wire / in IDB). The projection itself must shrink for anonymous.

## Goal

- **Anonymous**: only the fully-public community + content links (`community_links`,
  rendered by `CommunityContentSection`). No members list, no officials directory
  (NC/Prince/IC), no contact info, no names.
- **At-least-an-account** (incl. non-VEKN): the info that is "public" today — officials
  directory, local community, contacts.
- **VEKN member**: unchanged member projection.

## Open design decisions (product-manager + principal-engineer)

1. **Tier shape.** Either:
   - (A) introduce a 4th projection level "authenticated" between `public` and `member`
     (new precomputed column + SSE mapping), or
   - (B) collapse any-account → `member` in `entitled_level` and shrink the `public`
     projection to links-only.
   (A) is more storage/SSE surface; (B) reuses `member` but then a non-VEKN account
   gets the full member projection.
2. **Does a logged-in non-VEKN account see the full members list**, or only the
   officials/community directory? The user only explicitly restricts the members list
   for *anonymous*. If non-VEKN accounts may see the members list, (B) is sufficient;
   if not, (A) (or a separate members-list gate) is needed.
3. **Anonymous community-links projection.** Need `community_links` (+ minimal fields to
   render them) WITHOUT officials' names/contact. Essentially the existing
   "link-holder → minimal fields" branch applied to everyone, contact stripped.

## Children

- #308 backend access model (`access_levels.py`, `broadcast.entitled_level`, SSE level
  mapping, SYNC.md)
- #309 Community tab — anonymous sees only community/content link sections
- #310 Members tab/list — hidden from anonymous, explicit sign-in message
- #311 tournaments/leagues list display decision (fully-public-stripped vs
  hidden-with-explicit-login-message)
