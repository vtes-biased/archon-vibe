#!/usr/bin/env python3
"""Build script to fetch and process GeoNames data.

Downloads country and major city data from GeoNames and generates
static JSON files for use in the application.

Countries: ISO codes, names, and other basic info
Cities: GeoNames IDs for cities with population > 15,000

Usage:
    python scripts/build_geonames.py
"""

import json
import zipfile
from pathlib import Path
from urllib.request import urlretrieve


def download_and_extract(url: str, output_dir: Path) -> Path:
    """Download and extract a GeoNames data file."""
    filename = url.split("/")[-1]
    zip_path = output_dir / filename

    print(f"Downloading {filename}...")
    urlretrieve(url, zip_path)

    # Extract if it's a zip file
    if filename.endswith(".zip"):
        print(f"Extracting {filename}...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(output_dir)
        txt_filename = filename.replace(".zip", ".txt")
        zip_path.unlink()  # Remove zip after extraction
        return output_dir / txt_filename

    return zip_path


def build_countries_data(data_dir: Path, output_dir: Path) -> None:
    """Build countries JSON from GeoNames countryInfo.txt."""
    country_file = data_dir / "countryInfo.txt"

    if not country_file.exists():
        url = "http://download.geonames.org/export/dump/countryInfo.txt"
        print("Downloading countryInfo.txt...")
        urlretrieve(url, country_file)

    # Official UN/ISO 3166-1 country name overrides
    # GeoNames uses informal names, but we need official ones for political sensitivity
    name_overrides = {
        "BO": "Bolivia, Plurinational State of",
        "CZ": "Czech Republic",
        "IR": "Iran, Islamic Republic of",
        "KP": "Korea, Democratic People's Republic of",
        "KR": "Korea, Republic of",
        "LA": "Lao People's Democratic Republic",
        "MD": "Moldova, Republic of",
        "MK": "North Macedonia, Republic of",
        "NL": "Netherlands",
        "RU": "Russian Federation",
        "SY": "Syrian Arab Republic",
        "TW": "China, Republic of (Taiwan)",
        "TZ": "Tanzania, United Republic of",
        "VE": "Venezuela, Bolivarian Republic of",
        "VN": "Viet Nam",
    }

    countries = {}

    print("Processing countries data...")
    with open(country_file, encoding="utf-8") as f:
        for line in f:
            # Skip comments and empty lines
            if line.startswith("#") or not line.strip():
                continue

            parts = line.strip().split("\t")
            if len(parts) < 5:
                continue

            iso_code = parts[0]  # ISO-3166 2-letter code
            iso3 = parts[1]  # ISO-3166 3-letter code
            name = parts[4]  # Country name
            capital = parts[5] if len(parts) > 5 else ""
            continent = parts[8] if len(parts) > 8 else ""

            # Apply official name override if available
            if iso_code in name_overrides:
                name = name_overrides[iso_code]

            countries[iso_code] = {
                "iso_code": iso_code,
                "iso3": iso3,
                "name": name,
                "capital": capital,
                "continent": continent,
            }

    output_file = output_dir / "countries.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(countries, f, ensure_ascii=False, indent=2)

    print(f"✓ Created {output_file} with {len(countries)} countries")


def load_admin_codes(data_dir: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Load admin1 and admin2 code mappings to human-readable names.

    Returns:
        (admin1_names, admin2_names) where keys are "CC.Admin1" format
    """
    admin1_file = data_dir / "admin1CodesASCII.txt"
    admin2_file = data_dir / "admin2Codes.txt"

    # Download admin1 codes if not present
    if not admin1_file.exists():
        url = "http://download.geonames.org/export/dump/admin1CodesASCII.txt"
        print("Downloading admin1CodesASCII.txt...")
        urlretrieve(url, admin1_file)

    # Download admin2 codes if not present
    if not admin2_file.exists():
        url = "http://download.geonames.org/export/dump/admin2Codes.txt"
        print("Downloading admin2Codes.txt...")
        urlretrieve(url, admin2_file)

    admin1_names = {}
    admin2_names = {}

    # Parse admin1 codes (format: CC.Admin1Code\tName\tAsciiName\tGeonameId)
    with open(admin1_file, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                code = parts[0]  # e.g., "US.NY"
                name = parts[2] if len(parts) >= 3 else parts[1]  # Prefer ASCII name
                admin1_names[code] = name

    # Parse admin2 codes (format: CC.Admin1.Admin2\tName\tAsciiName\tGeonameId)
    with open(admin2_file, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                code = parts[0]  # e.g., "US.NY.001"
                name = parts[2] if len(parts) >= 3 else parts[1]  # Prefer ASCII name
                admin2_names[code] = name

    return admin1_names, admin2_names


def build_cities_data(data_dir: Path, output_dir: Path) -> None:
    """Build cities JSON from GeoNames cities15000.txt.

    Uses cities with population > 15,000 to keep the file manageable
    while still covering all major cities.

    Filters out city subdivisions (PPLX, PPLA5, etc.) and de-duplicates
    cities within the same country using admin zones for disambiguation.
    """
    txt_file = data_dir / "cities15000.txt"

    if not txt_file.exists():
        url = "http://download.geonames.org/export/dump/cities15000.zip"
        txt_file = download_and_extract(url, data_dir)

    # Feature codes to exclude (city subdivisions and minor divisions)
    excluded_feature_codes = {
        "PPLX",  # Section of populated place (e.g., Paris arrondissements, Dubai Marina)
        "PPLA5",  # Fifth-order administrative division capital
        "PPLA4",  # Fourth-order administrative division capital
        "PPLQ",  # Abandoned populated place
        "PPLH",  # Historical populated place
    }

    # Load admin code mappings for human-readable names
    admin1_names, admin2_names = load_admin_codes(data_dir)

    cities_by_country = {}  # Temporary dict for de-duplication

    print("Processing cities data...")
    with open(txt_file, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 15:
                continue

            feature_code = parts[7]

            # Skip city subdivisions and minor divisions
            if feature_code in excluded_feature_codes:
                continue

            geoname_id = int(parts[0])
            name = parts[1]
            ascii_name = parts[2]
            country_code = parts[8]
            admin1_code = parts[10]  # State/region code
            admin2_code = parts[11]  # County/district code
            admin3_code = parts[12]  # Municipality code
            admin4_code = parts[13]  # Neighborhood code
            latitude = float(parts[4])
            longitude = float(parts[5])
            population = int(parts[14]) if parts[14] else 0

            city_data = {
                "geoname_id": geoname_id,
                "name": name,
                "ascii_name": ascii_name,
                "country_code": country_code,
                "admin1_code": admin1_code,
                "admin2_code": admin2_code,
                "admin3_code": admin3_code,
                "admin4_code": admin4_code,
                "latitude": latitude,
                "longitude": longitude,
                "population": population,
            }

            # Group by country for de-duplication
            if country_code not in cities_by_country:
                cities_by_country[country_code] = []
            cities_by_country[country_code].append(city_data)

    # De-duplicate and disambiguate cities within each country
    cities = []
    for country_code, country_cities in cities_by_country.items():
        # Group cities by name
        name_groups = {}
        for city in country_cities:
            name_key = city["ascii_name"].lower()
            if name_key not in name_groups:
                name_groups[name_key] = []
            name_groups[name_key].append(city)

        # Process each name group
        for group in name_groups.values():
            if len(group) == 1:
                # No duplicates, keep as is
                cities.append(group[0])
            else:
                # Multiple cities with same name - disambiguate or deduplicate
                # Sort by population to prioritize larger cities
                group.sort(key=lambda x: x["population"], reverse=True)

                # Check if they're truly different cities or just duplicate entries
                seen_coords = set()
                for city in group:
                    coord_key = (
                        round(city["latitude"], 2),
                        round(city["longitude"], 2),
                    )

                    # Skip if we've seen a city at roughly the same location
                    if coord_key in seen_coords:
                        continue
                    seen_coords.add(coord_key)

                    # Add admin zone disambiguation if there are multiple distinct cities
                    if len(group) > 1:
                        # Prefer admin1 (state/region) as it's most meaningful
                        # Fall back to more specific divisions if admin1 is same
                        admin_suffix = None
                        if city["admin1_code"]:
                            # Check if other cities in group have same admin1
                            same_admin1 = [
                                c
                                for c in group
                                if c["admin1_code"] == city["admin1_code"]
                            ]
                            if len(same_admin1) == 1:
                                # Use human-readable admin1 name
                                admin1_key = f"{country_code}.{city['admin1_code']}"
                                admin_suffix = admin1_names.get(
                                    admin1_key, city["admin1_code"]
                                )
                            elif city["admin2_code"]:
                                # Use human-readable admin2 name
                                admin2_key = f"{country_code}.{city['admin1_code']}.{city['admin2_code']}"
                                admin_suffix = admin2_names.get(
                                    admin2_key, city["admin2_code"]
                                )
                            # Note: admin3 codes don't have a standard GeoNames mapping file,
                            # so we skip them to avoid showing non-human-readable codes

                        if admin_suffix:
                            city["name"] = f"{city['name']} ({admin_suffix})"

                    cities.append(city)

    # Remove admin code fields from output (info is in the name when needed)
    for city in cities:
        city.pop("admin1_code", None)
        city.pop("admin2_code", None)
        city.pop("admin3_code", None)
        city.pop("admin4_code", None)

    # Sort by population descending (most important cities first)
    cities.sort(key=lambda x: x["population"], reverse=True)

    output_file = output_dir / "cities.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(cities, f, ensure_ascii=False, indent=2)

    print(f"✓ Created {output_file} with {len(cities)} cities")


def main() -> None:
    """Main entry point for the build script."""
    # Setup directories
    backend_dir = Path(__file__).parent.parent
    data_dir = backend_dir / "data" / "geonames_raw"  # Raw downloads (not in package)
    output_dir = (
        backend_dir / "src" / "data" / "geonames"
    )  # Processed data (in package)

    data_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Building GeoNames data files")
    print("=" * 60)

    # Build countries data
    build_countries_data(data_dir, output_dir)

    # Build cities data
    build_cities_data(data_dir, output_dir)

    print("=" * 60)
    print("✓ Build complete!")
    print(f"  Output directory: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
