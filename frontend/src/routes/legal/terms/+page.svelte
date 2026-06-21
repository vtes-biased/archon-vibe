<script lang="ts">
  import { renderMarkdown } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";
  import raw from "$lib/legal-content/terms.md?raw";

  const html = renderMarkdown(raw);
</script>

<svelte:head>
  <title>{m.legal_terms_title()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-3xl mx-auto">
    <h1 class="text-3xl font-semibold text-accent mb-6">{m.legal_terms_title()}</h1>
    <article class="doc-prose prose max-w-none">
      {@html html}
    </article>
  </div>
</div>
