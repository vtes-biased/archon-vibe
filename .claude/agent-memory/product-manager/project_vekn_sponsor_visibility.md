---
name: vekn-sponsor-visibility
description: Sponsor (coopted_by) relationship — what it means, who may see it, and why surfacing it in the members UI is frontend-only
metadata:
  type: project
---

The member "sponsor" relationship is stored as `coopted_by` (sponsor's user uid) + `coopted_at` on the User object, inferred from VEKN-ID prefix / city-Prince / country-NC mapping (`backend/src/vekn_sync.py`, granted via `backend/src/routes/vekn.py` `/vekn/sponsor`). Purpose: **accountability/traceability** for new-member registrations (matters for fraud cleanup, suspensions, country-roster integrity — see [[project_vekn_account_surgery_bugs]]).

**Visibility verdict (sensitive — restricted):**
- IC: yes, globally.
- NC: yes, but scoped to their own country's roster.
- Sponsor (Prince/NC/IC): legitimate "who did I sponsor" interest in their own list.
- Member / general members / public: NO — exposes an official→member graph, invites lobbying.

**Why:** sponsor data is privacy-sensitive and operationally relevant only to officials; ordinary directory viewers get no benefit and some harm.

**How to apply:** when asked to surface sponsor info — recommend a **role-gated field on the member detail view** (`users/[uid]/+page.svelte`, reuse the IC/Ethics gate ~line 63) plus a **"members I sponsored" list on the sponsor's own profile** (`ProfileView.svelte`). NOT a column in `UserList.svelte` (already 601 lines, mobile-first, data absent at member level). Skip the directory filter.

**Gating mechanism (frontend-only, NO backend change):** `coopted_by`/`coopted_at` live ONLY in the `full` projection (`_USER_FULL_EXTRA` in `access_levels.py`), but the SSE **personal overlay** (`main.py`, snapshot phase ~582-635) already delivers `full`-level user objects to exactly the right viewers: IC globally (`_viewer_level`), NC/Prince for same-country users, everyone for their own profile. So the sponsor data each authorized viewer may see is already in their IndexedDB, and **presence IS the permission gate** — the UI just renders the field when present. Keep it out of member/public projections (unchanged). `coopted_by` is nullable (legacy/self-registered members) — render nothing when absent; sponsor name needs a local IndexedDB lookup by uid with graceful fallback. Assessed priority: p3.
