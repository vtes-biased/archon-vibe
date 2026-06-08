"""Country/city → IANA timezone reference data for VEKN event sync.

Reference data only — kept out of vekn_tournament_sync.py so it can grow without
touching the sync logic. Consumed by vekn_tournament_sync._guess_timezone.
"""

# Country code → IANA timezone (single-timezone countries, common VTES countries)
COUNTRY_TIMEZONE: dict[str, str] = {
    "AR": "America/Argentina/Buenos_Aires",
    "AT": "Europe/Vienna",
    "BE": "Europe/Brussels",
    "BY": "Europe/Minsk",
    "CH": "Europe/Zurich",
    "CL": "America/Santiago",
    "CZ": "Europe/Prague",
    "DE": "Europe/Berlin",
    "DK": "Europe/Copenhagen",
    "ES": "Europe/Madrid",
    "FI": "Europe/Helsinki",
    "FO": "Atlantic/Faroe",
    "FR": "Europe/Paris",
    "GB": "Europe/London",
    "GR": "Europe/Athens",
    "HR": "Europe/Zagreb",
    "HU": "Europe/Budapest",
    "IE": "Europe/Dublin",
    "IS": "Atlantic/Reykjavik",
    "IT": "Europe/Rome",
    "JP": "Asia/Tokyo",
    "LT": "Europe/Vilnius",
    "NL": "Europe/Amsterdam",
    "NO": "Europe/Oslo",
    "NZ": "Pacific/Auckland",
    "PH": "Asia/Manila",
    "PL": "Europe/Warsaw",
    "PT": "Europe/Lisbon",
    "RS": "Europe/Belgrade",
    "SE": "Europe/Stockholm",
    "SG": "Asia/Singapore",
    "SK": "Europe/Bratislava",
    "ZA": "Africa/Johannesburg",
    # Multi-timezone defaults (overridden by city lookup below)
    "AU": "Australia/Melbourne",
    "BR": "America/Sao_Paulo",
    "CA": "America/Toronto",
    "MX": "America/Mexico_City",
    "RU": "Europe/Moscow",
    "US": "America/New_York",
}

# City substring → timezone for multi-timezone countries.
# Checked case-insensitively against venue city and address fields.
CITY_TZ_OVERRIDES: list[tuple[str, str, str]] = [
    # US
    ("US", "Berkeley", "America/Los_Angeles"),
    ("US", "Los Angeles", "America/Los_Angeles"),
    ("US", "San Francisco", "America/Los_Angeles"),
    ("US", "Seattle", "America/Los_Angeles"),
    ("US", "Portland", "America/Los_Angeles"),
    ("US", "Denver", "America/Denver"),
    ("US", "Longmont", "America/Denver"),
    ("US", "Wheatridge", "America/Denver"),
    ("US", "Chicago", "America/Chicago"),
    ("US", "Minneapolis", "America/Chicago"),
    ("US", "Houston", "America/Chicago"),
    ("US", "Dallas", "America/Chicago"),
    ("US", "Phoenix", "America/Phoenix"),
    # BR
    ("BR", "Manaus", "America/Manaus"),
    # CA
    ("CA", "Vancouver", "America/Vancouver"),
    ("CA", "Victoria", "America/Vancouver"),
    ("CA", "Winnipeg", "America/Winnipeg"),
    ("CA", "St. Albert", "America/Edmonton"),
    ("CA", "Edmonton", "America/Edmonton"),
    ("CA", "Calgary", "America/Edmonton"),
    ("CA", "Halifax", "America/Halifax"),
    ("CA", "Amherst", "America/Halifax"),
    # AU
    ("AU", "Brisbane", "Australia/Brisbane"),
    ("AU", "Rockhampton", "Australia/Brisbane"),
    ("AU", "Townsville", "Australia/Brisbane"),
    ("AU", "Annerley", "Australia/Brisbane"),
    ("AU", "Perth", "Australia/Perth"),
    ("AU", "Canning", "Australia/Perth"),
    ("AU", "Sydney", "Australia/Sydney"),
    ("AU", "Newcastle", "Australia/Sydney"),
    ("AU", "Burwood", "Australia/Sydney"),
]
