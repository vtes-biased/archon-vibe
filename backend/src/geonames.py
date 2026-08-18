"""GeoNames data utilities."""

import json
import re
from enum import StrEnum
from functools import lru_cache
from importlib.resources import files
from typing import TypedDict

from archon_engine import PyEngine

_engine = PyEngine()


class Continent(StrEnum):
    AF = "AF"  # Africa
    AN = "AN"  # Antarctica
    AS = "AS"  # Asia
    EU = "EU"  # Europe
    NA = "NA"  # North America
    OC = "OC"  # Oceania
    SA = "SA"  # South America


class Country(TypedDict):
    iso_code: str  # ISO-3166 2-letter code
    iso3: str  # ISO-3166 3-letter code
    name: str
    capital: str
    continent: str  # Continent code (AF, AS, EU, NA, OC, SA, AN)


class City(TypedDict):
    geoname_id: int
    name: str
    ascii_name: str
    country_code: str
    latitude: float
    longitude: float
    population: int


@lru_cache(maxsize=1)
def load_countries() -> dict[str, Country]:
    # files(__package__) resolves both in dev and in the wheel; a hardcoded
    # "backend.src..." path breaks post-install.
    data_file = files(__package__).joinpath("data", "geonames", "countries.json")
    return json.loads(data_file.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_cities() -> list[City]:
    """Cities are sorted by population descending."""
    data_file = files(__package__).joinpath("data", "geonames", "cities.json")
    return json.loads(data_file.read_text(encoding="utf-8"))


def get_country(iso_code: str) -> Country | None:
    countries = load_countries()
    return countries.get(iso_code.upper())


# Names GeoNames does not carry: the constituent countries of the UK, and the
# colloquial forms the TWDA's `place` field uses.
_COUNTRY_NAME_ALIASES = {
    "usa": "US",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "russia": "RU",
}


@lru_cache(maxsize=1)
def _country_names() -> dict[str, str]:
    return {c["name"].lower(): c["iso_code"] for c in load_countries().values()}


def normalize_country(value: str) -> str | None:
    """An ISO country code from a code or a country name, or None.

    `Tournament.country` is meant to hold the code but holds the name on some
    rows, and external corpora quote names — normalise both sides through here
    before comparing, or the mismatches silently drop real matches
    ([hazards](../../wiki/hazards.md)).
    """
    value = (value or "").strip()
    if not value:
        return None
    if len(value) == 2:
        return value.upper() if value.upper() in load_countries() else None
    lowered = value.lower()
    return _country_names().get(lowered) or _COUNTRY_NAME_ALIASES.get(lowered)


def country_key(value: str) -> str:
    """A key for comparing two country values, one of which may be a name.

    Unresolvable values compare as themselves rather than as "unknown", so a
    country this module has never heard of still fails a comparison against a
    different one. Resolving to None instead would make every such value equal
    to every other and silently disable the caller's guard.
    """
    return normalize_country(value) or value.strip().lower()


def get_continent(country_code: str) -> str | None:
    country = get_country(country_code)
    return country["continent"] if country else None


def get_countries_on_continent(country_code: str) -> list[str]:
    continent = get_continent(country_code)
    if not continent:
        return []
    countries = load_countries()
    return [c["iso_code"] for c in countries.values() if c["continent"] == continent]


# Regex to strip parenthetical suffixes: "Washington (DC)" -> "Washington"
_PAREN_RE = re.compile(r"\s*\(.*\)\s*$")


@lru_cache(maxsize=1)
def _build_city_index() -> tuple[
    dict[tuple[str, str], City],
    dict[tuple[str, str], City],
    dict[tuple[str, str], City],
]:
    """Build (by_name, by_ascii, by_base) lookup dicts keyed by (country_code,
    name.lower()). Cities are sorted by population desc, so setdefault keeps
    the largest city per key."""
    by_name: dict[tuple[str, str], City] = {}
    by_ascii: dict[tuple[str, str], City] = {}
    by_base: dict[tuple[str, str], City] = {}

    for city in load_cities():
        cc = city["country_code"].upper()
        name_lower = city["name"].lower()
        ascii_lower = city["ascii_name"].lower()

        by_name.setdefault((cc, name_lower), city)
        by_ascii.setdefault((cc, ascii_lower), city)

        base = _PAREN_RE.sub("", city["name"]).strip()
        if base != city["name"]:
            by_base.setdefault((cc, base.lower()), city)

    return by_name, by_ascii, by_base


def match_city(name: str, country_code: str) -> City | None:
    """Tries exact name, ASCII name, ASCII-folded, then base name (no parens),
    in that order."""
    name = name.strip()
    if not name:
        return None
    cc = country_code.upper()
    by_name, by_ascii, by_base = _build_city_index()

    if city := by_name.get((cc, name.lower())):
        return city
    if city := by_ascii.get((cc, name.lower())):
        return city
    stripped = _engine.fold_ascii(name)
    if stripped != name:
        if city := by_ascii.get((cc, stripped.lower())):
            return city
    if city := by_base.get((cc, name.lower())):
        return city
    return None
