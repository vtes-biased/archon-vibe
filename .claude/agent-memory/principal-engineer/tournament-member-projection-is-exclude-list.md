---
name: tournament-member-projection-is-exclude-list
description: compute_tournament_member is a denylist — any new Tournament field auto-reaches members at SSE; secrets need explicit exclusion
metadata:
  type: project
---

`access_levels.py` `compute_tournament_member` returns `{k:v for k,v in d.items() if k not in _TOURNAMENT_MEMBER_EXCLUDE}` where `_TOURNAMENT_MEMBER_EXCLUDE = {"checkin_code", "vekn_pushed_at"}`. So the member projection is a **denylist, not an allowlist**: any new field added to the Tournament model is automatically delivered at member level over SSE with zero access_levels.py change. Public is a separate explicit allowlist (`_TOURNAMENT_PUBLIC_FIELDS`).

**Why:** explains why timer (`timer`, `table_extra_time`, `round_time`, `finals_time`) reaches players with no projection edits — it's a field on Tournament and the member denylist passes it through.

**How to apply:** when adding a Tournament sub-field that carries organizer-only secrets (codes, draft/unpublished content, private audience metadata), you MUST add it to `_TOURNAMENT_MEMBER_EXCLUDE` or it leaks to every member. Conversely, a field meant for participants needs no projection work. Public exposure always requires explicit `_TOURNAMENT_PUBLIC_FIELDS` opt-in.
