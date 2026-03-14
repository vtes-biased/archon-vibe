<script lang="ts">
  import type { CommunityLink } from "$lib/types";
  import { EyeOff, Eye, Star, StarOff } from "lucide-svelte";
  import * as m from '$lib/paraglide/messages.js';

  interface Props {
    userUid: string;
    links: CommunityLink[];
    onModerate: (userUid: string, url: string, action: string) => void;
  }
  let { userUid, links, onModerate }: Props = $props();
</script>

<div class="flex items-center gap-1 mt-1">
  {#each links as link}
    {#if link.moderation?.status === "hidden"}
      <button
        onclick={() => onModerate(userUid, link.url, "clear")}
        class="p-1 text-ash-500 hover:text-emerald-400 transition-colors"
        title={m.community_moderate_clear()}
      ><Eye class="w-3.5 h-3.5" /></button>
    {:else}
      <button
        onclick={() => onModerate(userUid, link.url, "hide")}
        class="p-1 text-ash-500 hover:text-amber-400 transition-colors"
        title={m.community_moderate_hide()}
      ><EyeOff class="w-3.5 h-3.5" /></button>
    {/if}
    {#if link.moderation?.status === "promoted"}
      <button
        onclick={() => onModerate(userUid, link.url, "clear")}
        class="p-1 text-amber-400 hover:text-ash-500 transition-colors"
        title={m.community_moderate_clear()}
      ><StarOff class="w-3.5 h-3.5" /></button>
    {:else}
      <button
        onclick={() => onModerate(userUid, link.url, "promote")}
        class="p-1 text-ash-500 hover:text-amber-400 transition-colors"
        title={m.community_moderate_promote()}
      ><Star class="w-3.5 h-3.5" /></button>
    {/if}
  {/each}
</div>
