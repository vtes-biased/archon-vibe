<script lang="ts">
  import { Info } from "@lucide/svelte";
  import type { Component, Snippet } from "svelte";

  // One shape for "here is something you should know". The console had grown
  // three: a bordered muted box, a warn banner, and a bare icon + line — with
  // the same class of information (why the event is unranked, what happened to
  // the TWDA submission) rendered two different ways side by side.
  //
  // Two tones, and the distinction is what the reader must DO: `info` states a
  // fact and stays out of the way; `warn` needs attention, so it earns a box.
  // Anything that is neither is not a notice.
  let {
    tone = "info",
    icon = Info,
    children,
  }: {
    tone?: "info" | "warn";
    icon?: Component<any>;
    children: Snippet;
  } = $props();
  const Icon = $derived(icon);
</script>

<div class="flex items-start gap-2 text-sm {tone === 'warn' ? 'banner-warn border rounded-lg p-3' : 'text-ink-muted'}">
  <Icon class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
  <span class="min-w-0">{@render children()}</span>
</div>
