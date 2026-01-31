# Frontend Library Modules

## geonames.ts

Provides typed access to GeoNames geographic data (countries and cities).

### Usage

```typescript
import { 
  getCountries, 
  getCountry, 
  loadCities, 
  searchCities,
  getCitiesByCountry 
} from './lib/geonames';

// Countries are loaded immediately (small file)
const countries = getCountries();
const france = getCountry('FR');

// Cities are lazy-loaded (large ~6MB file)
const cities = await loadCities();

// Search for cities
const parisResults = await searchCities('Paris', 'FR', 5);

// Get cities in a country
const usaCities = await getCitiesByCountry('US', 50);
```

### Performance

- **Countries**: ~32KB, loaded eagerly with the main bundle
- **Cities**: ~6MB, lazy-loaded on first use, cached thereafter
- Data is split into a separate chunk (`geonames-cities`) to avoid bloating the initial bundle
- All functions use in-memory search (no backend calls needed for offline-first PWA)

### Data Structure

Data is shared with the backend via symlink: `frontend/src/data/geonames` → `backend/src/data/geonames`

This ensures:
- Single source of truth
- No data duplication
- Automatic updates when running the build script

