<script lang="ts">
    import { searchCities } from "$lib/geonames";
    import type { City } from "$lib/types";
    import { Loader2 } from "lucide-svelte";
    import * as m from '$lib/paraglide/messages.js';

    let {
        value = $bindable(""),
        countryCode,
        disabled = false,
        required = false,
        class: className = "",
        onselect,
    }: {
        value?: string;
        countryCode: string;
        disabled?: boolean;
        required?: boolean;
        class?: string;
        onselect?: () => void;
    } = $props();

    let inputValue = $state(value);
    let suggestions = $state<City[]>([]);
    let showSuggestions = $state(false);
    let selectedIndex = $state(-1);
    let searching = $state(false);
    let searchTimeout: ReturnType<typeof setTimeout> | null = null;

    // Sync input value with bound value
    $effect(() => {
        inputValue = value;
    });

    async function handleInput() {
        const query = inputValue.trim();

        if (!query || query.length < 2) {
            suggestions = [];
            showSuggestions = false;
            return;
        }

        // Debounce search
        if (searchTimeout) {
            clearTimeout(searchTimeout);
        }

        searching = true;
        searchTimeout = setTimeout(async () => {
            try {
                const results = await searchCities(query, countryCode, 10);
                suggestions = results;
                showSuggestions = results.length > 0;
                selectedIndex = -1;
            } catch (error) {
                console.error("Failed to search cities:", error);
                suggestions = [];
                showSuggestions = false;
            } finally {
                searching = false;
            }
        }, 300);
    }

    function selectCity(city: City) {
        value = city.name;
        inputValue = city.name;
        showSuggestions = false;
        suggestions = [];
        selectedIndex = -1;
        onselect?.();
    }

    function handleKeydown(e: KeyboardEvent) {
        if (!showSuggestions || suggestions.length === 0) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, suggestions.length - 1);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, -1);
        } else if (e.key === "Enter" && selectedIndex >= 0) {
            e.preventDefault();
            const selectedCity = suggestions[selectedIndex];
            if (selectedCity) {
                selectCity(selectedCity);
            }
        } else if (e.key === "Escape") {
            showSuggestions = false;
            selectedIndex = -1;
        }
    }

    function handleBlur() {
        // Delay to allow click on suggestion
        setTimeout(() => {
            showSuggestions = false;
            selectedIndex = -1;
            // Update bound value with current input
            value = inputValue;
        }, 200);
    }
</script>

<div class="relative {className}">
    <input
        type="text"
        bind:value={inputValue}
        oninput={handleInput}
        onkeydown={handleKeydown}
        onblur={handleBlur}
        onfocus={() => inputValue && inputValue.length >= 2 && handleInput()}
        {disabled}
        {required}
        placeholder={disabled
            ? m.city_select_country_first()
            : m.city_search_placeholder()}
        class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 placeholder:text-mist-dark focus:ring-2 focus:ring-crimson-500 focus:border-transparent disabled:bg-ash-900 disabled:text-mist-dark"
    />

    {#if searching}
        <div class="absolute right-3 top-1/2 -translate-y-1/2">
            <Loader2 class="animate-spin h-4 w-4 text-mist-dark" />
        </div>
    {/if}

    {#if showSuggestions && suggestions.length > 0}
        <div
            class="absolute z-10 w-full mt-1 bg-dusk-950 border border-ash-600 rounded shadow-lg max-h-60 overflow-auto"
        >
            {#each suggestions as city, i}
                <button
                    type="button"
                    onclick={() => selectCity(city)}
                    class="w-full text-left px-3 py-2 hover:bg-ash-800 {i ===
                    selectedIndex
                        ? 'bg-ash-800'
                        : ''}"
                >
                    <div class="font-medium text-ash-200">
                        {city.name}
                    </div>
                    <div class="text-xs text-mist-dark">
                        {m.city_population({ population: city.population.toLocaleString() })}
                    </div>
                </button>
            {/each}
        </div>
    {/if}
</div>
