import type { Country, City } from '$lib/types';
import { normalizeSearch } from './utils';

// Countries are small (~32KB), load eagerly.
import countriesData from '$lib/data/geonames/countries.json';

let citiesCache: City[] | null = null;
let citiesLoadingPromise: Promise<City[]> | null = null;

export function getCountries(): Record<string, Country> {
    return countriesData as Record<string, Country>;
}

/**
 * Get all countries sorted by display name — the order every dropdown wants
 * (the raw record is keyed by ISO code, which sorts by native name, not label).
 */
let sortedCountriesCache: Country[] | null = null;
export function getSortedCountries(): Country[] {
    sortedCountriesCache ??= Object.values(getCountries()).sort((a, b) =>
        a.name.localeCompare(b.name)
    );
    return sortedCountriesCache;
}

export function getCountry(isoCode: string): Country | undefined {
    const countries = getCountries();
    return countries[isoCode.toUpperCase()];
}

/** ISO 3166-1 alpha-2 → flag emoji, e.g. "US" → "🇺🇸". */
export function getCountryFlag(isoCode: string): string {
    const code = isoCode.toUpperCase();
    if (code.length !== 2) return '';
    const offset = 0x1F1E6 - 65; // Regional indicator A starts at U+1F1E6
    return String.fromCodePoint(
        code.charCodeAt(0) + offset,
        code.charCodeAt(1) + offset
    );
}

export function getContinent(isoCode: string): string | undefined {
    const country = getCountry(isoCode);
    return country?.continent;
}

export function getCountriesOnContinent(isoCode: string): string[] {
    const continent = getContinent(isoCode);
    if (!continent) return [];
    const countries = getCountries();
    return Object.values(countries)
        .filter(c => c.continent === continent)
        .map(c => c.iso_code);
}

/** Cities file is ~6MB, so it's loaded on-demand and cached after first load. */
export async function loadCities(): Promise<City[]> {
    if (citiesCache) {
        return citiesCache;
    }

    if (citiesLoadingPromise) {
        return citiesLoadingPromise;
    }

    citiesLoadingPromise = import('$lib/data/geonames/cities.json')
        .then((module) => {
            citiesCache = module.default as City[];
            citiesLoadingPromise = null;
            return citiesCache;
        });

    return citiesLoadingPromise;
}


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


