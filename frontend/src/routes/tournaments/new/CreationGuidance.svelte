<script lang="ts">
  import type { Component } from "svelte";
  import { Banknote, Bot, DoorOpen, Layers, LayoutGrid, MessageSquare, QrCode, Split, Upload, Users, WifiOff } from "@lucide/svelte";
  import type { WizardAnswers } from "./CreationWizard.svelte";
  import * as m from '$lib/paraglide/messages.js';

  let { answers, decklistRequired }: { answers: WizardAnswers; decklistRequired: boolean } = $props();

  const guideHref = "/help/organizer-guide";

  interface Tip {
    icon: Component<any>;
    title: string;
    body: string;
    href?: string;
  }

  const tips = $derived.by((): Tip[] => {
    const irl = answers.setting === "irl";
    const big = irl && answers.kind === "big";
    const out: Tip[] = [];
    if (answers.setting === "online") {
      if (answers.home === "official") {
        out.push({
          icon: Bot,
          title: m.tournament_wiz_tip_discord_official_t(),
          body: m.tournament_wiz_tip_discord_official_b(),
          href: `${guideHref}#running-an-online-event-on-discord`,
        });
      } else if (answers.home === "own") {
        out.push({
          icon: Bot,
          title: m.tournament_wiz_tip_discord_own_t(),
          body: m.tournament_wiz_tip_discord_own_b(),
          href: `${guideHref}#installing-the-discord-bot`,
        });
      } else if (answers.home === "elsewhere") {
        out.push({
          icon: MessageSquare,
          title: m.tournament_wiz_tip_discord_none_t(),
          body: m.tournament_wiz_tip_discord_none_b({ field: m.tfield_venue_url() }),
        });
      }
    }
    if (big) {
      out.push({
        icon: Users,
        title: m.tournament_wiz_tip_helpers_t(),
        body: m.tournament_wiz_tip_helpers_b({
          section: m.organizers_title(),
          tab: m.tools_group_setup(),
        }),
      });
      out.push({
        icon: LayoutGrid,
        title: m.tournament_wiz_tip_rooms_t(),
        body: m.tournament_wiz_tip_rooms_b({
          section: m.rooms_title(),
          venue: m.tfield_section_location(),
          tab: m.tools_group_setup(),
        }),
      });
    }
    if (irl && (big || answers.doors === "advance")) {
      out.push({
        icon: Upload,
        title: m.tournament_wiz_tip_csv_t(),
        body: m.tournament_wiz_tip_csv_b({
          tools: m.tools_title(),
          group: m.tools_group_setup(),
          action: m.csv_import_title(),
          state: m.state_registration(),
          columns: m.csv_import_columns(),
        }),
      });
    }
    if (irl && answers.offlineVenue) {
      out.push({
        icon: WifiOff,
        title: m.tournament_wiz_tip_offline_t(),
        body: m.tournament_wiz_tip_offline_b({ action: m.offline_go_offline(), checkin: m.players_check_in() }),
      });
    }
    if (irl && (big || decklistRequired)) {
      out.push({
        icon: Layers,
        title: m.tournament_wiz_tip_decklists_t(),
        body: m.tournament_wiz_tip_decklists_b(),
        href: `${guideHref}#deck-management`,
      });
    }
    if (big && !answers.offlineVenue) {
      out.push({
        icon: QrCode,
        title: m.tournament_wiz_tip_qr_t(),
        body: m.tournament_wiz_tip_qr_b({ action: m.checkin_qr_show_code() }),
      });
    }
    if (irl && answers.doors === "gate") {
      out.push({
        icon: Banknote,
        title: m.tournament_wiz_tip_paid_gate_t(),
        body: m.tournament_wiz_tip_paid_gate_b({ action: m.payment_mark_all_paid(), menu: m.common_more() }),
      });
    } else if (irl && answers.doors === "free") {
      out.push({
        icon: Banknote,
        title: m.tournament_wiz_tip_paid_free_t(),
        body: m.tournament_wiz_tip_paid_free_b(),
      });
    }
    if (answers.kind === "parallel") {
      out.push({
        icon: Split,
        title: m.tournament_wiz_tip_parallel_t(),
        body: m.tournament_wiz_tip_parallel_b({
          action: m.overview_start_round({ n: "2" }),
        }),
        href: `${guideHref}#parallel-rounds`,
      });
    }
    if (irl && answers.kind === "local") {
      out.push({
        icon: DoorOpen,
        title: m.tournament_wiz_tip_latecomers_t(),
        body: m.tournament_wiz_tip_latecomers_b(),
      });
    }
    return out;
  });
</script>

{#if tips.length > 0}
  <div class="bg-surface-card rounded-lg shadow p-6 border border-line space-y-4">
    <h2 class="text-xl font-medium text-ink-strong">{m.tournament_wiz_guide_title()}</h2>
    <ul class="space-y-4">
      {#each tips as tip}
        {@const Icon = tip.icon}
        <li class="flex items-start gap-3">
          <Icon class="w-4 h-4 mt-1 shrink-0 text-ink-muted" aria-hidden="true" />
          <div class="min-w-0">
            <p class="text-sm font-medium text-ink-strong">{tip.title}</p>
            <p class="text-sm text-ink-muted">{tip.body}</p>
            {#if tip.href}
              <a href={tip.href} target="_blank" rel="noopener noreferrer" class="text-sm text-link hover:underline">{m.help_organizer_guide_title()}</a>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
  </div>
{/if}
