"""Static VEKN role assignments, maintained outside the VEKN API.

Reference data only — kept out of vekn_sync.py so it can drift without touching
sync logic. Consumed by _derive_role_seeds (ADMINS → IC rights, JUDGES →
judge/rulemonger/judgekin role), which runs ONLY when the member sync first
imports a user: roles are seeded on first import and app-managed thereafter,
so editing this file never rewrites an existing user's roles.

After the legacy-archon decommission this roster is the sole IC bootstrap for
a rebuild from VEKN data alone — keep at least one current IC entry accurate,
or a fresh DB has no one able to grant roles.
"""

from ..models import Role

ADMINS: set[str] = {
    "3200340",
    "3200188",
    "8180022",
    "3190007",
    "2050001",
    "1002480",
}

JUDGES: dict[str, Role] = {
    "8180022": Role.RULEMONGER,
    "3200188": Role.RULEMONGER,
    "3190007": Role.JUDGE,
    "4200005": Role.RULEMONGER,
    "8530107": Role.JUDGE,
    "2340000": Role.JUDGE,
    "6260014": Role.JUDGE,
    "1940030": Role.JUDGE,
    "1003731": Role.JUDGE,
    "1003455": Role.RULEMONGER,
    "3200340": Role.RULEMONGER,
    "1003030": Role.JUDGE,
    "3070069": Role.JUDGE,
    "4960027": Role.JUDGE,
    "2810001": Role.JUDGE,
    "3190133": Role.JUDGE,
    "3190041": Role.JUDGE,
    "8030009": Role.JUDGE,
    "9510021": Role.JUDGE,
    "3370036": Role.JUDGE,
    "1000629": Role.JUDGE,
    "1002855": Role.JUDGEKIN,
    "3340152": Role.JUDGEKIN,
    "5360022": Role.JUDGE,
    "8390001": Role.JUDGEKIN,
    "3070006": Role.JUDGEKIN,
    "4960046": Role.JUDGEKIN,
    "6140001": Role.JUDGEKIN,
    "3020044": Role.JUDGEKIN,
    "3020010": Role.JUDGEKIN,
    "1003584": Role.JUDGEKIN,
    "1003214": Role.JUDGEKIN,
    "4110004": Role.JUDGEKIN,
    "4110113": Role.JUDGEKIN,
    "4100033": Role.JUDGEKIN,
    "2331000": Role.JUDGEKIN,
    "3680057": Role.JUDGEKIN,
    "4100008": Role.JUDGEKIN,
    "3120101": Role.JUDGEKIN,
    "4960000": Role.JUDGEKIN,
    "3010501": Role.JUDGEKIN,
    "6060022": Role.JUDGEKIN,
    "5540005": Role.JUDGEKIN,
    "3530067": Role.JUDGE,
}
