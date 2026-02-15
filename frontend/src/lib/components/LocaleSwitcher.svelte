<script lang="ts">
  import { getLocale, setLocale, locales } from '$lib/paraglide/runtime.js';

  const localeLabels: Record<string, string> = {
    en: 'EN',
    fr: 'FR',
    es: 'ES',
    pt: 'PT',
    it: 'IT',
  };

  const localeFlags: Record<string, string> = {
    en: '\u{1F1EC}\u{1F1E7}',
    fr: '\u{1F1EB}\u{1F1F7}',
    es: '\u{1F1EA}\u{1F1F8}',
    pt: '\u{1F1F5}\u{1F1F9}',
    it: '\u{1F1EE}\u{1F1F9}',
  };

  function handleChange(event: Event) {
    const target = event.target as HTMLSelectElement;
    setLocale(target.value as any);
  }
</script>

<select
  name="locale"
  value={getLocale()}
  onchange={handleChange}
  class="bg-dusk-950 text-ash-400 text-xs border border-ash-800 rounded px-1.5 py-1 cursor-pointer hover:text-ash-200 hover:border-ash-600 focus:outline-none focus:border-crimson-500"
  aria-label="Select language"
>
  {#each locales as locale}
    <option value={locale}>
      {localeFlags[locale]} {localeLabels[locale]}
    </option>
  {/each}
</select>
