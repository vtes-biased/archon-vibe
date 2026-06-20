<script lang="ts">
    import { getVenuesByCountry, type VenueInfo } from "$lib/db";
    import { normalizeSearch } from "$lib/utils";
    import * as m from '$lib/paraglide/messages.js';

    let {
        value = $bindable(""),
        country,
        disabled = false,
        id,
        onselect,
        oninput,
    }: {
        value?: string;
        country: string;
        disabled?: boolean;
        id?: string;
        onselect?: (venue: VenueInfo) => void;
        oninput?: () => void;
    } = $props();

    let inputValue = $state(value);
    let allVenues = $state<VenueInfo[]>([]);
    let filtered = $state<VenueInfo[]>([]);
    let showSuggestions = $state(false);
    let selectedIndex = $state(-1);

    // Sync input value with bound value
    $effect(() => {
        inputValue = value;
    });

    // Reload venues when country changes
    $effect(() => {
        const c = country;
        getVenuesByCountry(c).then(v => { allVenues = v; });
    });

    function handleInput() {
        const query = normalizeSearch(inputValue.trim());
        if (!query || allVenues.length === 0) {
            filtered = [];
            showSuggestions = false;
        } else {
            filtered = allVenues.filter(v => normalizeSearch(v.venue).includes(query));
            showSuggestions = filtered.length > 0;
            selectedIndex = -1;
        }
        oninput?.();
    }

    function selectVenue(venue: VenueInfo) {
        value = venue.venue;
        inputValue = venue.venue;
        showSuggestions = false;
        filtered = [];
        selectedIndex = -1;
        onselect?.(venue);
    }

    function handleKeydown(e: KeyboardEvent) {
        if (!showSuggestions || filtered.length === 0) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, filtered.length - 1);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, -1);
        } else if (e.key === "Enter" && selectedIndex >= 0) {
            e.preventDefault();
            const selected = filtered[selectedIndex];
            if (selected) selectVenue(selected);
        } else if (e.key === "Escape") {
            showSuggestions = false;
            selectedIndex = -1;
        }
    }

    function handleBlur() {
        setTimeout(() => {
            showSuggestions = false;
            selectedIndex = -1;
            value = inputValue;
        }, 200);
    }
</script>

<div class="relative">
    <input
        {id}
        type="text"
        bind:value={inputValue}
        oninput={handleInput}
        onkeydown={handleKeydown}
        onblur={handleBlur}
        onfocus={() => inputValue && handleInput()}
        {disabled}
        placeholder={m.tfield_venue_placeholder()}
        class="w-full px-3 py-2 text-sm bg-surface-card border border-line-strong rounded-lg text-ink-bright focus:border-line-strong focus:outline-none"
    />

    {#if showSuggestions && filtered.length > 0}
        <div class="absolute z-10 w-full mt-1 bg-surface-card border border-line-strong rounded shadow-lg max-h-60 overflow-auto">
            {#each filtered as venue, i}
                <button
                    type="button"
                    onclick={() => selectVenue(venue)}
                    class="w-full text-left px-3 py-2 hover:bg-surface-hover {i === selectedIndex ? 'bg-surface-hover' : ''}"
                >
                    <div class="font-medium text-ink-bright">{venue.venue}</div>
                    {#if venue.address}
                        <div class="text-xs text-ink-faint">{venue.address}</div>
                    {/if}
                </button>
            {/each}
        </div>
    {/if}
</div>
