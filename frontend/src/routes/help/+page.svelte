<script lang="ts">
  import { helpDocs, referenceDocs, userGuides } from "$lib/help-docs";
  import { BookOpen, Trophy, Scale, Shield, UserRound, ClipboardList } from "lucide-svelte";
  import { ArrowLeft } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  const iconMap: Record<string, typeof BookOpen> = {
    book: BookOpen,
    trophy: Trophy,
    scale: Scale,
    shield: Shield,
    user: UserRound,
    clipboard: ClipboardList,
  };
</script>

<svelte:head>
  <title>{m.help_page_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-4xl mx-auto">
    <h1 class="text-3xl font-light text-crimson-500 mb-8">{m.help_page_title()}</h1>

    <!-- Reference Documents -->
    <section class="mb-8">
      <h2 class="text-lg font-medium text-bone-100 mb-4">{m.help_reference_docs()}</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {#each referenceDocs as slug}
          {@const doc = helpDocs[slug]}
          {@const Icon = iconMap[doc.icon] || BookOpen}
          <a
            href="/help/{slug}"
            class="block bg-dusk-950 rounded-lg border border-ash-800 p-5 hover:border-crimson-700 transition-colors group"
          >
            <div class="flex items-start gap-3">
              <div class="p-2 rounded-lg bg-crimson-900/30 text-crimson-400 group-hover:bg-crimson-900/50 transition-colors">
                <Icon class="w-5 h-5" />
              </div>
              <div>
                <h3 class="text-bone-100 font-medium group-hover:text-crimson-400 transition-colors">{doc.title}</h3>
                <p class="text-sm text-ash-400 mt-1">{doc.description}</p>
              </div>
            </div>
          </a>
        {/each}
      </div>
    </section>

    <!-- User Guides -->
    <section>
      <h2 class="text-lg font-medium text-bone-100 mb-4">{m.help_user_guides()}</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {#each userGuides as slug}
          {@const doc = helpDocs[slug]}
          {@const Icon = iconMap[doc.icon] || BookOpen}
          <a
            href="/help/{slug}"
            class="block bg-dusk-950 rounded-lg border border-ash-800 p-5 hover:border-crimson-700 transition-colors group"
          >
            <div class="flex items-start gap-3">
              <div class="p-2 rounded-lg bg-crimson-900/30 text-crimson-400 group-hover:bg-crimson-900/50 transition-colors">
                <Icon class="w-5 h-5" />
              </div>
              <div>
                <h3 class="text-bone-100 font-medium group-hover:text-crimson-400 transition-colors">{doc.title}</h3>
                <p class="text-sm text-ash-400 mt-1">{doc.description}</p>
              </div>
            </div>
          </a>
        {/each}
      </div>
    </section>
  </div>
</div>
