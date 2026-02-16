"""GeoNames data utilities.

Provides access to countries and cities data from GeoNames.
"""

import json
from enum import Enum
from functools import lru_cache
from importlib.resources import files
from typing import TypedDict


class Continent(str, Enum):
    """Continent codes from GeoNames."""

    AF = "AF"  # Africa
    AN = "AN"  # Antarctica
    AS = "AS"  # Asia
    EU = "EU"  # Europe
    NA = "NA"  # North America
    OC = "OC"  # Oceania
    SA = "SA"  # South America


class Country(TypedDict):
    """Country information from GeoNames."""

    iso_code: str  # ISO-3166 2-letter code
    iso3: str  # ISO-3166 3-letter code
    name: str
    capital: str
    continent: str  # Continent code (AF, AS, EU, NA, OC, SA, AN)


class City(TypedDict):
    """City information from GeoNames."""

    geoname_id: int
    name: str
    ascii_name: str
    country_code: str
    latitude: float
    longitude: float
    population: int


@lru_cache(maxsize=1)
def load_countries() -> dict[str, Country]:
    """Load countries data from JSON file.

    Returns:
        Dictionary mapping ISO codes to Country objects
    """
    data_file = files("backend.src.data.geonames").joinpath("countries.json")
    return json.loads(data_file.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_cities() -> list[City]:
    """Load cities data from JSON file.

    Returns:
        List of City objects sorted by population (descending)
    """
    data_file = files("backend.src.data.geonames").joinpath("cities.json")
    return json.loads(data_file.read_text(encoding="utf-8"))


def get_city_by_id(geoname_id: int) -> City | None:
    """Get a city by its GeoNames ID.

    Args:
        geoname_id: The GeoNames ID of the city

    Returns:
        City object or None if not found
    """
    cities = load_cities()
    for city in cities:
        if city["geoname_id"] == geoname_id:
            return city
    return None


def get_country(iso_code: str) -> Country | None:
    """Get a country by its ISO code.

    Args:
        iso_code: ISO-3166 2-letter country code

    Returns:
        Country object or None if not found
    """
    countries = load_countries()
    return countries.get(iso_code.upper())


def get_continent(country_code: str) -> str | None:
    """Get the continent code for a country."""
    country = get_country(country_code)
    return country["continent"] if country else None


def get_countries_on_continent(country_code: str) -> list[str]:
    """Get all country ISO codes on the same continent as given country."""
    continent = get_continent(country_code)
    if not continent:
        return []
    countries = load_countries()
    return [c["iso_code"] for c in countries.values() if c["continent"] == continent]


def search_cities(
    query: str, country_code: str | None = None, limit: int = 10
) -> list[City]:
    """Search cities by name.

    Args:
        query: Search term (case-insensitive)
        country_code: Optional country code to filter by
        limit: Maximum number of results

    Returns:
        List of matching cities
    """
    cities = load_cities()
    query_lower = query.lower()
    results = []

    for city in cities:
        if len(results) >= limit:
            break

        # Filter by country if specified
        if country_code and city["country_code"] != country_code.upper():
            continue

        # Match query against name or ASCII name
        if (
            query_lower in city["name"].lower()
            or query_lower in city["ascii_name"].lower()
        ):
            results.append(city)

    return results
