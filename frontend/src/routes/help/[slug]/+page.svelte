<script lang="ts">
  import { page } from "$app/stores";
  import { goto } from "$app/navigation";
  import { helpDocs, extractToc } from "$lib/help-docs";
  import DocumentViewer from "$lib/components/DocumentViewer.svelte";
  import TableOfContents from "$lib/components/TableOfContents.svelte";
  import { ArrowLeft } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  const slug = $derived($page.params.slug as string);
  const doc = $derived(helpDocs[slug]);

  // Rendered HTML and TOC entries (derived from doc)
  const html = $derived(doc?.content ?? "");
  const tocEntries = $derived(doc ? extractToc(html, doc.tocDepth) : []);

  let activeHeading = $state("");

  // Redirect if invalid slug
  $effect(() => {
    if (slug && !doc) {
      goto("/help");
    }
  });
</script>

<svelte:head>
  <title>{doc?.title ?? "Help"} - Archon</title>
</svelte:head>

{#if doc}
  <div class="p-4 sm:p-8">
    <div class="max-w-6xl mx-auto">
      <!-- Back link -->
      <a href="/help" class="inline-flex items-center gap-1 text-sm text-ash-400 hover:text-crimson-400 mb-4 transition-colors">
        <ArrowLeft class="w-4 h-4" />
        {m.help_back_to_list()}
      </a>

      <!-- Title -->
      <h1 class="text-3xl font-light text-crimson-500 mb-6">{doc.title}</h1>

      <!-- Layout: TOC sidebar + content -->
      <div class="flex gap-8">
        <!-- Content -->
        <div class="flex-1 min-w-0">
          <DocumentViewer {html} {tocEntries} onActiveHeadingChange={(id) => (activeHeading = id)} />
        </div>

        <!-- TOC (desktop sidebar + mobile drawer) -->
        {#if tocEntries.length > 0}
          <TableOfContents entries={tocEntries} {activeHeading} />
        {/if}
      </div>
    </div>
  </div>
{/if}
