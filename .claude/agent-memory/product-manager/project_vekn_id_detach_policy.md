---
name: vekn-id-detach-policy
description: Durable rule for what stays with a VEKN ID vs follows the human on detach (abandon/displace) and merge; owner chose the PURE rule + self-abandon-while-suspended guard (REJECTED the sanction-level exception)
metadata:
  type: project
---

# VEKN-record continuity rule (account detach/merge policy)

A VEKN ID is a permanent competitive/disciplinary identity. **A uid that carries a
`vekn_id` is immovable** — never re-keyed, never soft-deleted; everything keyed to it
stays linked. Only the human *without* the vekn_id ever moves. On detach (abandon by
self, or displace by organizer) the VEKN record keeps its `uid` and all competitive/
accountability data; a fresh personal account (new `uid`) gets only login + PII.

**VEKN record keeps:** uid, name, country/city/state/geoname, roles, coopted_by/at,
vekn_prefix, all 4 ratings, wins, vekn_synced bookkeeping, decks, sanctions,
community_links.
**Person (new uid) gets:** auth methods, name (copied), nickname, avatar,
contact_email/discord/phone, discord_id, phone_is_whatsapp, **calendar_token (carried,
follows the human — both merge and detach re-home it via get_calendar_token; an earlier fix
made merge carry it but left strip/split dropping it; a later one made them consistent)**.

**FINAL DECISION — owner REJECTED the sanction-level exception (do not reintroduce).**
Sanctions are NOT partitioned by level and NEVER follow the person; all stay with the
VEKN record (keying on the stable uid, untouched). The level-aware "active suspension/
probation follows the human" idea was rejected as exactly the acrobatic special-casing
the detach rework set out to remove. The sanction-dodge is closed instead by a single guard:
**self-`/abandon` is blocked while the user holds an active suspension/probation**
(`user_has_active_suspension`: not deleted, not lifted, not expired). Admin
`/force-abandon` is EXEMPT (officials act deliberately).

**Accepted sharp edge (under the pure rule):** `/link` displace inherits the holder's
full history into the new owner, including an active suspension (consistent with the
rule, admin-initiated). Owner DECISION: leave as-is, NO `/link` guard — an organizer can
lift it if inappropriate. Only self-`/abandon` is guarded (the one path where the same
person escapes their own sanction). Admin paths are deliberately not special-cased.

**Why mechanically forced, not just policy:** all history objects
(Tournament.Player.user_uid, Seat.player_uid, DeckObject.user_uid, Rating.user_uid,
Sanction.user_uid, coopted_by) key on user `uid`, never vekn_id. Detach keeps the
record's uid stable, so whatever stays on that uid stays linked; whatever moves to the
new uid is severed. Policy only decides which side each *User-table field* lands on; the
default for any new field is "stays with the record" (never leak VEKN history).

**Status: IMPLEMENTED.** `strip_vekn_from_user` + `split_user_from_vekn`
collapsed into one `detach_user_from_vekn(uid) -> (personal_account, vekn_record)`; the
displace/abandon difference (re-merge the freed record into a new owner) lives in the
caller `/link`, not in detach. `merge_users` is now field-driven via
`msgspec.structs.replace(keep_user, …)` and reassigns decks. Live-SSE propagation of the
orphan/merged record is a known pre-existing lag. country/city/state and
community_links stay with the RECORD (jurisdiction + office). See
[[vekn-account-surgery-bugs]] and .pst/details/59-vekn-detach.md.
