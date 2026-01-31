# Backend Build Scripts

## GeoNames Data Builder

The `build_geonames.py` script fetches and processes geographic data from [GeoNames](https://www.geonames.org/) to create static JSON files for use in the application.

### What it does

1. **Downloads countries data** from GeoNames `countryInfo.txt`
   - Includes ISO codes (2 and 3 letter), names, capitals, continents
   - Output: `backend/src/data/geonames/countries.json` (~32 KB)

2. **Downloads major cities data** from GeoNames `cities15000.zip`
   - Cities with population > 15,000
   - Filters out city subdivisions (PPLX, PPLA4, PPLA5, etc.)
   - De-duplicates cities within countries using admin zones
   - Disambiguates cities with same name using state/region codes
   - Includes GeoNames IDs, names, coordinates, population
   - Output: `backend/src/data/geonames/cities.json` (~6 MB, ~30K cities)

### Usage

```bash
# Run directly
python backend/scripts/build_geonames.py

# Or use the justfile command
just build-geonames
```

### Data Structure

**Countries** (`countries.json`):
```json
{
  "FR": {
    "iso_code": "FR",
    "iso3": "FRA",
    "name": "France",
    "capital": "Paris",
    "continent": "EU"
  }
}
```

**Cities** (`cities.json`):
```json
[
  {
    "geoname_id": 2988507,
    "name": "Paris",
    "ascii_name": "Paris",
    "country_code": "FR",
    "latitude": 48.85341,
    "longitude": 2.3488,
    "population": 2138551
  },
  {
    "geoname_id": 4409896,
    "name": "Springfield (Missouri)",
    "ascii_name": "Springfield",
    "country_code": "US",
    "latitude": 37.21533,
    "longitude": -93.29824,
    "population": 170188
  }
]
```

Note: Cities with duplicate names in the same country are disambiguated with human-readable state/region names in parentheses (e.g., "Springfield (Missouri)", "Springfield (Massachusetts)").

### Using the Data

Import the utility functions from `backend.src.geonames`:

```python
from backend.src.geonames import (
    load_countries,
    load_cities,
    get_country,
    get_city_by_id,
    search_cities
)

# Get all countries
countries = load_countries()  # dict[str, Country]

# Get a specific country
france = get_country("FR")

# Get a city by GeoNames ID
paris = get_city_by_id(2988507)

# Search cities by name
results = search_cities("Paris", country_code="FR", limit=10)
```

### Notes

- Raw GeoNames data is downloaded to `backend/data/geonames_raw/` (gitignored, not in package)
- Processed JSON files in `backend/src/data/geonames/` are committed and included in package
- The script is idempotent - it can be run multiple times safely
- Cities are sorted by population (largest first) for efficient searching
- Data is loaded using `importlib.resources` for proper deployment in Docker/servers
- Data is cached in memory using `@lru_cache` for performance

#### City Filtering

The script filters out city subdivisions to avoid clutter:
- **PPLX**: Sections of populated places (e.g., Dubai Marina, Paris arrondissements)
- **PPLA4/PPLA5**: Fourth and fifth-order administrative division capitals
- **PPLQ/PPLH**: Abandoned and historical populated places

Cities with duplicate names in the same country are:
1. Disambiguated with human-readable admin1 names (state/region/province) in parentheses
2. Falls back to admin2 names (county/district) if cities share the same admin1
3. De-duplicated if they represent the same location (within ~1km)

Examples: "Springfield (Missouri)", "Suzhou (Jiangsu)", "Manhattan (New York)"

