# GeoNames Data in Frontend

## Overview

GeoNames data (countries and cities) is available statically in the frontend for offline-first functionality.

## Setup

### Data Location

- **Symlink**: `frontend/src/data/geonames` → `backend/src/data/geonames`
- **Source**: Single source of truth in backend, shared with frontend
- **No duplication**: Data is not copied, updates automatically

### Files

- `countries.json` (~32KB) - All countries with ISO codes, names, capitals
- `cities.json` (~6MB) - ~30K cities with populations > 15,000

## Usage

```typescript
import { 
  getCountries, 
  getCountry, 
  loadCities, 
  searchCities,
  getCitiesByCountry,
  getCityById
} from './lib/geonames';

// Countries (loaded immediately)
const countries = getCountries();
const france = getCountry('FR');

// Cities (lazy-loaded on first use)
const cities = await loadCities();
const parisResults = await searchCities('Paris', 'FR', 5);
const usaCities = await getCitiesByCountry('US', 50);
```

## Performance

### Bundle Optimization

- **Countries**: Loaded with main bundle (small ~32KB)
- **Cities**: Lazy-loaded on first use (large ~6MB)
- **Code splitting**: Cities chunk is split automatically (`geonames-cities.js`)
- **Caching**: Data is cached in memory after first load

### Build Configuration

Vite config includes:
- JSON import support
- Manual chunk splitting for cities.json
- Optimized for production builds

## Development

### Updating Data

When you run the backend build script, the frontend data updates automatically:

```bash
python backend/scripts/build_geonames.py
# Frontend data is updated via symlink
```

### Testing

A test file is provided: `frontend/test-geonames.html`

Run the dev server and navigate to it:
```bash
npm run dev
# Open http://localhost:5173/test-geonames.html
```

## Types

TypeScript types are defined in `frontend/src/types.ts`:
- `Country` - Country information
- `City` - City information  
- `Continent` - Continent codes

## Notes

- Data is offline-first: no backend calls needed
- Perfect for PWA functionality
- Symlink works in Docker (as long as files are copied during build)
- All search operations are in-memory (fast)

