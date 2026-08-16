<script lang="ts">
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { onMount } from "svelte";
  import { replaceState } from "$app/navigation";
  import { helpDocs, extractToc } from "$lib/help-docs";
  import type { TocEntry } from "$lib/help-docs";
  import DocumentViewer from "$lib/components/DocumentViewer.svelte";
  import TableOfContents from "$lib/components/TableOfContents.svelte";
  import PlayerGuide from "$lib/components/help/PlayerGuide.svelte";
  import OrganizerGuide from "$lib/components/help/OrganizerGuide.svelte";
  import { ArrowLeft } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const slug = $derived($page.params.slug as string);
  const doc = $derived(helpDocs[slug]);
  const isComponent = $derived(doc?.isComponent ?? false);

  const html = $derived(!isComponent ? (doc?.content ?? "") : "");
  const markdownToc = $derived(!isComponent && doc ? extractToc(html, doc.tocDepth) : []);

  let componentToc = $state<TocEntry[]>([]);
  let guideEl: HTMLElement | undefined = $state();

  const tocEntries = $derived(isComponent ? componentToc : markdownToc);
  let activeHeading = $state("");

  onMount(() => {
    if (!isComponent || !guideEl || !doc) return;

    const headings = guideEl.querySelectorAll<HTMLElement>('h1[id], h2[id], h3[id], h4[id]');
    const entries: TocEntry[] = [];
    const headingEls: HTMLElement[] = [];

    for (const h of headings) {
      const depth = parseInt(h.tagName[1]!);
      if (depth > doc!.tocDepth) continue;
      entries.push({
        id: h.id,
        text: h.textContent?.replace(/\s*#\s*$/, '').trim() || '',
        depth,
      });
      headingEls.push(h);
    }
    componentToc = entries;

    if (headingEls.length === 0) return;

    const observer = new IntersectionObserver(
      (obsEntries) => {
        for (const entry of obsEntries) {
          if (entry.isIntersecting) {
            activeHeading = entry.target.id;
            replaceState(`#${entry.target.id}`, {});
            break;
          }
        }
      },
      { rootMargin: "-10% 0px -80% 0px", threshold: 0 }
    );
    for (const el of headingEls) observer.observe(el);

    if (window.location.hash) {
      const target = document.getElementById(window.location.hash.slice(1));
      if (target) setTimeout(() => target.scrollIntoView(), 100);
    }

    return () => observer.disconnect();
  });

  $effect(() => {
    if (slug && !doc) {
      goto("/help");
    }
  });
</script>

<svelte:head>
  <title>{doc?.title ?? m.help_title_fallback()} - Archon</title>
</svelte:head>

{#if doc}
  <div class="p-4 sm:p-8">
    <div class="max-w-6xl mx-auto">
      <a href="/help" class="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-link mb-4 transition-colors">
        <ArrowLeft class="w-4 h-4" />
        {m.help_back_to_list()}
      </a>

      <h1 class="text-3xl font-semibold text-accent mb-6">{doc.title}</h1>

      <div class="flex gap-8">
        <div class="flex-1 min-w-0">
          {#if isComponent}
            <article bind:this={guideEl} class="doc-prose prose max-w-none">
              {#if slug === 'player-guide'}
                <PlayerGuide />
              {:else if slug === 'organizer-guide'}
                <OrganizerGuide />
              {/if}
            </article>
          {:else}
            <DocumentViewer {html} {tocEntries} onActiveHeadingChange={(id) => (activeHeading = id)} />
          {/if}
        </div>

        {#if tocEntries.length > 0}
          <TableOfContents entries={tocEntries} {activeHeading} />
        {/if}
      </div>
    </div>
  </div>
{/if}
