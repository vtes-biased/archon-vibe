"""Static VEKN IC bootstrap. ADMINS seeds IC rights via _derive_role_seeds only
on a user's first member-sync import — editing this file never touches an
existing user's roles. Keep at least one entry accurate: it's the sole IC
bootstrap for a fresh DB rebuilt from VEKN data alone.
"""

ADMINS: set[str] = {
    "3200340",
    "3200188",
    "8180022",
    "3190007",
    "2050001",
    "1002480",
}
