<script lang="ts">
  import { Monitor, Sun, Moon } from "lucide-svelte";
  import { getTheme, setTheme, type ThemePref } from "$lib/stores/theme.svelte";
  import { getLocale, setLocale, locales } from '$lib/paraglide/runtime.js';
  import * as m from '$lib/paraglide/messages.js';

  const localeLabels: Record<string, string> = {
    en: 'EN', fr: 'FR', es: 'ES', pt: 'PT', it: 'IT',
  };
  const localeFlags: Record<string, string> = {
    en: '\u{1F1EC}\u{1F1E7}',
    fr: '\u{1F1EB}\u{1F1F7}',
    es: '\u{1F1EA}\u{1F1F8}',
    pt: '\u{1F1F5}\u{1F1F9}',
    it: '\u{1F1EE}\u{1F1F9}',
  };

  const themes: { value: ThemePref; label: () => string; icon: typeof Monitor }[] = [
    { value: 'system', label: () => m.theme_system(), icon: Monitor },
    { value: 'light', label: () => m.theme_light(), icon: Sun },
    { value: 'dark', label: () => m.theme_dark(), icon: Moon },
  ];
</script>

<div class="p-6 border-t border-ash-800 space-y-4">
  <h3 class="text-sm font-medium text-ash-400 uppercase tracking-wide">{m.profile_settings()}</h3>

  <!-- Theme -->
  <div class="space-y-2">
    <span class="block text-sm text-ash-400">{m.profile_theme_label()}</span>
    <div class="flex gap-2">
      {#each themes as t}
        {@const active = getTheme() === t.value}
        <button
          onclick={() => setTheme(t.value)}
          class="flex items-center gap-2 px-3 py-2 rounded text-sm transition-colors {active ? 'bg-crimson-700 text-white' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
        >
          <t.icon class="w-4 h-4" />
          {t.label()}
        </button>
      {/each}
    </div>
  </div>

  <!-- Language -->
  <div class="space-y-2">
    <span class="block text-sm text-ash-400">{m.profile_language_label()}</span>
    <div class="flex gap-2 flex-wrap">
      {#each locales as locale}
        {@const active = getLocale() === locale}
        <button
          onclick={() => setLocale(locale as any)}
          class="flex items-center gap-1.5 px-3 py-2 rounded text-sm transition-colors {active ? 'bg-crimson-700 text-white' : 'bg-ash-800 text-ash-300 hover:bg-ash-700'}"
        >
          <span>{localeFlags[locale]}</span>
          {localeLabels[locale]}
        </button>
      {/each}
    </div>
  </div>
</div>
