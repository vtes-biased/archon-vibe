<script lang="ts">
  import { helpDocs, referenceDocs, userGuides } from "$lib/help-docs";
  import { BookOpen, Trophy, Scale, Shield, UserRound, ClipboardList, ShieldCheck, FileText } from "@lucide/svelte";
  import { ArrowLeft } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const iconMap: Record<string, typeof BookOpen> = {
    book: BookOpen,
    trophy: Trophy,
    scale: Scale,
    shield: Shield,
    user: UserRound,
    clipboard: ClipboardList,
  };

  const legalLinks = $derived([
    { href: "/legal/privacy", title: m.legal_privacy_title(), description: m.legal_privacy_description(), icon: ShieldCheck },
    { href: "/legal/terms", title: m.legal_terms_title(), description: m.legal_terms_description(), icon: FileText },
  ]);
</script>

<svelte:head>
  <title>{m.help_page_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-4xl mx-auto">
    <h1 class="text-3xl font-semibold text-accent mb-8">{m.help_page_title()}</h1>

    <!-- Reference Documents -->
    <section class="mb-8">
      <h2 class="text-lg font-medium text-ink-strong mb-4">{m.help_reference_docs()}</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {#each referenceDocs as slug}
          {@const doc = helpDocs[slug]!}
          {@const Icon = iconMap[doc.icon] || BookOpen}
          <a
            href="/help/{slug}"
            class="block bg-surface-card rounded-lg border border-line p-5 hover:border-accent-strong transition-colors group"
          >
            <div class="flex items-start gap-3">
              <div class="p-2 rounded-lg bg-accent-soft/30 text-link group-hover:bg-accent-soft/50 transition-colors">
                <Icon class="w-5 h-5" />
              </div>
              <div>
                <h3 class="text-ink-strong font-medium group-hover:text-link transition-colors">{doc.title}</h3>
                <p class="text-sm text-ink-muted mt-1">{doc.description}</p>
              </div>
            </div>
          </a>
        {/each}
      </div>
    </section>

    <!-- User Guides -->
    <section class="mb-8">
      <h2 class="text-lg font-medium text-ink-strong mb-4">{m.help_user_guides()}</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {#each userGuides as slug}
          {@const doc = helpDocs[slug]!}
          {@const Icon = iconMap[doc.icon] || BookOpen}
          <a
            href="/help/{slug}"
            class="block bg-surface-card rounded-lg border border-line p-5 hover:border-accent-strong transition-colors group"
          >
            <div class="flex items-start gap-3">
              <div class="p-2 rounded-lg bg-accent-soft/30 text-link group-hover:bg-accent-soft/50 transition-colors">
                <Icon class="w-5 h-5" />
              </div>
              <div>
                <h3 class="text-ink-strong font-medium group-hover:text-link transition-colors">{doc.title}</h3>
                <p class="text-sm text-ink-muted mt-1">{doc.description}</p>
              </div>
            </div>
          </a>
        {/each}
      </div>
    </section>

    <!-- Legal -->
    <section>
      <h2 class="text-lg font-medium text-ink-strong mb-4">{m.help_legal_section()}</h2>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {#each legalLinks as link}
          {@const Icon = link.icon}
          <a
            href={link.href}
            class="block bg-surface-card rounded-lg border border-line p-5 hover:border-accent-strong transition-colors group"
          >
            <div class="flex items-start gap-3">
              <div class="p-2 rounded-lg bg-accent-soft/30 text-link group-hover:bg-accent-soft/50 transition-colors">
                <Icon class="w-5 h-5" />
              </div>
              <div>
                <h3 class="text-ink-strong font-medium group-hover:text-link transition-colors">{link.title}</h3>
                <p class="text-sm text-ink-muted mt-1">{link.description}</p>
              </div>
            </div>
          </a>
        {/each}
      </div>
    </section>
  </div>
</div>
