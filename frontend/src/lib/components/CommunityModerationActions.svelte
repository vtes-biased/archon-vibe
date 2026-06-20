<script lang="ts">
  import type { CommunityLink } from "$lib/types";
  import { EyeOff, Star, Globe } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    userUid: string;
    link: CommunityLink;
    onModerate: (userUid: string, url: string, action: string) => void;
    canPromoteNational?: boolean;
    canPromoteGlobal?: boolean;
  }
  let { userUid, link, onModerate, canPromoteNational = false, canPromoteGlobal = false }: Props = $props();

  // Mutually exclusive states: hidden | national pin | global pin | none.
  const isHidden = $derived(link.moderation?.status === "hidden");
  const scope = $derived(link.moderation?.status === "promoted" ? link.moderation.scope : null);

  // Active state = amethyst; idle = neutral. Same icon always, colour conveys state.
  const active = "text-purple-400 hover:text-ink-muted";
  const idle = "text-ink-faint hover:text-purple-400";
</script>

<div class="flex items-center justify-center gap-2">
  <button
    onclick={() => onModerate(userUid, link.url, isHidden ? "clear" : "hide")}
    class="p-1 transition-colors {isHidden ? active : idle}"
    title={isHidden ? m.community_moderate_clear() : m.community_moderate_hide()}
  ><EyeOff class="w-4 h-4" /></button>

  {#if canPromoteNational}
    <button
      onclick={() => onModerate(userUid, link.url, scope === "national" ? "clear" : "promote_national")}
      class="p-1 transition-colors {scope === 'national' ? active : idle}"
      title={scope === "national" ? m.community_moderate_clear() : m.community_moderate_promote_national()}
    ><Star class="w-4 h-4" /></button>
  {/if}

  {#if canPromoteGlobal}
    <button
      onclick={() => onModerate(userUid, link.url, scope === "global" ? "clear" : "promote_global")}
      class="p-1 transition-colors {scope === 'global' ? active : idle}"
      title={scope === "global" ? m.community_moderate_clear() : m.community_moderate_promote_global()}
    ><Globe class="w-4 h-4" /></button>
  {/if}
</div>
