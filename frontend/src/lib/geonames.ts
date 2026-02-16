/**
 * GeoNames data access for frontend.
 * 
 * Provides typed access to countries and cities data.
 * Cities are lazy-loaded to avoid bloating the initial bundle.
 */

import type { Country, City } from '$lib/types';
import { normalizeSearch } from './utils';

// Countries are small (~32KB), load eagerly
import countriesData from '$lib/data/geonames/countries.json';

// Cache for lazy-loaded cities data
let citiesCache: City[] | null = null;
let citiesLoadingPromise: Promise<City[]> | null = null;

/**
 * Get all countries.
 * Returns immediately as data is already loaded.
 */
export function getCountries(): Record<string, Country> {
    return countriesData as Record<string, Country>;
}

/**
 * Get a specific country by ISO code.
 */
export function getCountry(isoCode: string): Country | undefined {
    const countries = getCountries();
    return countries[isoCode.toUpperCase()];
}

/**
 * Convert ISO 3166-1 alpha-2 country code to flag emoji.
 * Example: "US" → "🇺🇸", "FR" → "🇫🇷"
 */
export function getCountryFlag(isoCode: string): string {
    const code = isoCode.toUpperCase();
    if (code.length !== 2) return '';
    const offset = 0x1F1E6 - 65; // Regional indicator A starts at U+1F1E6
    return String.fromCodePoint(
        code.charCodeAt(0) + offset,
        code.charCodeAt(1) + offset
    );
}

/**
 * Load cities data (lazy-loaded, cached after first load).
 * Cities file is ~6MB, so we load it on-demand.
 */
export async function loadCities(): Promise<City[]> {
    // Return cached data if available
    if (citiesCache) {
        return citiesCache;
    }

    // Return existing loading promise if already loading
    if (citiesLoadingPromise) {
        return citiesLoadingPromise;
    }

    // Start loading
    citiesLoadingPromise = import('$lib/data/geonames/cities.json')
        .then((module) => {
            citiesCache = module.default as City[];
            citiesLoadingPromise = null;
            return citiesCache;
        });

    return citiesLoadingPromise;
}

/**
 * Get a city by its GeoNames ID.
 */
export async function getCityById(geonameId: number): Promise<City | undefined> {
    const cities = await loadCities();
    return cities.find((city) => city.geoname_id === geonameId);
}

/**
 * Search cities by name.
 * 
 * @param query - Search term (case-insensitive)
 * @param countryCode - Optional country code to filter by
 * @param limit - Maximum number of results (default: 10)
 */
export async function searchCities(
    query: string,
    countryCode?: string,
    limit: number = 10
): Promise<City[]> {
    const cities = await loadCities();
    const queryNorm = normalizeSearch(query);
    const results: City[] = [];

    for (const city of cities) {
        if (results.length >= limit) {
            break;
        }

        // Filter by country if specified
        if (countryCode && city.country_code !== countryCode.toUpperCase()) {
            continue;
        }

        // Match query against name or ASCII name (diacritic-insensitive)
        if (
            normalizeSearch(city.name).includes(queryNorm) ||
            city.ascii_name.toLowerCase().includes(queryNorm)
        ) {
            results.push(city);
        }
    }

    return results;
}

/**
 * Get cities for a specific country.
 * 
 * @param countryCode - ISO 3166-1 alpha-2 country code
 * @param limit - Maximum number of results (default: 100)
 */
export async function getCitiesByCountry(
    countryCode: string,
    limit: number = 100
): Promise<City[]> {
    const cities = await loadCities();
    const results: City[] = [];
    const code = countryCode.toUpperCase();

    for (const city of cities) {
        if (results.length >= limit) {
            break;
        }

        if (city.country_code === code) {
            results.push(city);
        }
    }

    return results;
}

