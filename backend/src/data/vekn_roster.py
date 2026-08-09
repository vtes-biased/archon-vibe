"""Static VEKN IC bootstrap, maintained outside the VEKN API.

Reference data only — kept out of vekn_sync.py so it can drift without touching
sync logic. Consumed by _derive_role_seeds (ADMINS → IC rights), which runs ONLY
when the member sync first imports a user: roles are seeded on first import and
app-managed thereafter, so editing this file never rewrites an existing user's
roles.

This roster is the sole IC bootstrap for a rebuild from VEKN data alone — keep at
least one current IC entry accurate, or a fresh DB has no one able to grant roles.

A companion JUDGES dict used to seed judge ranks here. It was a ~44-entry
hand-maintained stand-in for legacy archon's 105 real ranks, and being the only
judge-rank source for accounts the member sync created before the legacy ETL ran,
it is what left members without their rank. Those ranks were restored from the
legacy DB (`backend/scripts/backfill_roles_from_archon.py`) and the app is now the
system of record for them — there is no vekn.net field to seed them from — so the
dict was removed rather than left to re-seed a revoked rank onto a recreated
account. Judge ranks are granted in-app by Rulemongers; a from-scratch VEKN-only
rebuild starts with none, which is the same position it starts from for every
other app-managed role.
"""

ADMINS: set[str] = {
    "3200340",
    "3200188",
    "8180022",
    "3190007",
    "2050001",
    "1002480",
}
