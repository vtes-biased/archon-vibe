<script lang="ts">
  import { renderMarkdown } from "$lib/markdown";
  import raw from "$lib/legal-content/terms.md?raw";

  const html = renderMarkdown(raw);
</script>

<svelte:head>
  <title>Terms of Service - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-3xl mx-auto">
    <h1 class="text-3xl font-light text-crimson-500 mb-6">Terms of Service</h1>
    <article class="doc-prose prose max-w-none">
      {@html html}
    </article>
  </div>
</div>
