<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";
  import ExampleBox from "./ExampleBox.svelte";
  import Button from "$lib/components/Button.svelte";
  import Badge from "$lib/components/Badge.svelte";
  import InlineNotice from "$lib/components/InlineNotice.svelte";
  import VpInput from "$lib/components/VpInput.svelte";
  import {
    QrCode, WifiOff, Wifi, Share2, ClipboardCopy, Download, Dices, Dice3, Undo2, Trash2,
    Pause, RotateCcw, ChevronDown, ChevronRight, Plus, SquarePlus, ArrowRightLeft,
    ShieldCheck, TriangleAlert, Gavel, X, Ban, Wrench, Users, Swords, Upload, Settings2,
    CheckCheck, MoreHorizontal, Ellipsis, Banknote, FileX, UserMinus, Printer, Image,
  } from "@lucide/svelte";

  let openFaq = $state<number | null>(null);
  const faqs = [
    { q: m.og_faq_q_no_registration(), a: m.og_faq_a_no_registration() },
    { q: m.og_faq_q_wrong_vp(), a: m.og_faq_a_wrong_vp() },
    { q: m.og_faq_q_change_rounds(), a: m.og_faq_a_change_rounds() },
    { q: m.og_faq_q_fewer_finals(), a: m.og_faq_a_fewer_finals() },
    { q: m.og_faq_q_wrong_scores(), a: m.og_faq_a_wrong_scores() },
    { q: m.og_faq_q_need_finals(), a: m.og_faq_a_need_finals() },
    { q: m.og_faq_q_staggered(), a: m.og_faq_a_staggered() },
    { q: m.og_faq_q_vekn_push(), a: m.og_faq_a_vekn_push() },
    { q: m.og_faq_q_delete(), a: m.og_faq_a_delete() },
    { q: m.og_faq_q_remove_vs_drop(), a: m.og_faq_a_remove_vs_drop() },
    { q: m.og_faq_q_dq(), a: m.og_faq_a_dq() },
    { q: m.og_faq_q_multiday(), a: m.og_faq_a_multiday() },
    { q: m.og_faq_q_decklists_mode(), a: m.og_faq_a_decklists_mode() },
    { q: m.og_faq_q_open_rounds(), a: m.og_faq_a_open_rounds() },
    { q: m.og_faq_q_proxy(), a: m.og_faq_a_proxy() },
    { q: m.og_faq_q_discord(), a: m.og_faq_a_discord() },
  ];
</script>

<!-- Structural chrome the app builds from tournament state, which a doc has none
     of. Controls and labels come from the real Button/Badge and the real message
     keys, so only the surrounding layout is drawn here. -->
{#snippet sheetGroup(title: string, open: boolean)}
  <div class="flex items-center gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">
    {#if open}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
    {title}
  </div>
{/snippet}

{#snippet sheetRow(label: string, Icon: any)}
  <div class="flex items-center gap-3 px-4 py-3 min-h-[44px] text-sm text-ink-bright">
    <Icon class="w-4 h-4 shrink-0" />
    <span class="flex-1">{label}</span>
  </div>
{/snippet}

{#snippet menu(label: string, Icon: any)}
  <div>
    <Button variant="secondary" size="md"><MoreHorizontal class="w-4 h-4" /> {m.common_more()}</Button>
    <div class="mt-1 min-w-[12rem] max-w-xs rounded-lg border border-line-strong bg-surface-muted py-1 shadow-lg">
      <span class="flex w-full items-center gap-2 px-3 py-2 text-sm text-ink-bright"><Icon class="w-4 h-4 shrink-0" /> {label}</span>
    </div>
  </div>
{/snippet}

{@html renderGuideSection(m.og_intro())}

{@html renderGuideSection(m.og_console())}

<ExampleBox>
  <div class="space-y-4 max-w-sm">
    <div class="space-y-2">
      <h3 class="text-lg font-semibold text-accent leading-tight">Alicante por la tarde</h3>
      <div class="flex flex-wrap items-center gap-1.5">
        <Badge kind="status" tone="pending">{m.state_checkin()}</Badge>
        <Badge>Standard</Badge>
        <Badge>{m.tournament_proxies_allowed()}</Badge>
      </div>
      <div class="flex flex-wrap items-center gap-2 pt-0.5">
        <Button variant="ghost" size="md"><Share2 class="w-4 h-4" /> {m.tournament_share()}</Button>
        <Button variant="ghost" size="md"><WifiOff class="w-4 h-4" /> {m.offline_go_offline()}</Button>
        <Button variant="ghost" size="md"><Wrench class="w-4 h-4" /> {m.tools_title()}</Button>
      </div>
    </div>

    <div class="rounded-lg border border-line overflow-hidden">
      <div class="border-b border-line px-3 py-3 space-y-3">
        <div class="flex items-center gap-1 text-xs">
          <span class="w-2 h-2 rounded-full bg-info inline-block"></span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="w-2 h-2 rounded-full bg-info inline-block"></span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="text-link font-medium whitespace-nowrap"><span class="w-2 h-2 rounded-full bg-accent inline-block mr-1 align-middle"></span>{m.state_checkin()}</span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="w-2 h-2 rounded-full bg-surface-active inline-block"></span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="w-2 h-2 rounded-full bg-surface-active inline-block"></span>
        </div>
        <p class="text-sm text-ink-muted">{m.action_bar_waiting_after_round({ n: "1" })}</p>
        <div class="flex flex-wrap items-center gap-2">
          <Button variant="primary" size="lg">{m.overview_start_round({ n: "2" })}</Button>
          <Button variant="secondary" size="md"><CheckCheck class="w-4 h-4" /> {m.overview_check_all_in()}</Button>
          <Button variant="secondary" size="md"><MoreHorizontal class="w-4 h-4" /> {m.common_more()}</Button>
        </div>
      </div>
      <div class="flex">
        <span class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 border-accent text-ink-strong"><Users class="w-4 h-4" /> {m.tournament_tab_players()}</span>
        <span class="flex items-center px-4 py-3 border-b-2 border-transparent text-ink-muted"><Swords class="w-4 h-4" /></span>
      </div>
    </div>

    <div class="rounded-lg border border-line overflow-hidden">
      <div class="flex items-center justify-between border-b border-line px-4 py-3">
        <span class="text-sm font-semibold text-ink-strong">{m.tools_title()}</span>
        <X class="w-5 h-5 text-ink-muted" />
      </div>
      {@render sheetGroup(m.tools_group_setup(), false)}
      {@render sheetGroup(m.tools_group_door(), true)}
      {@render sheetRow(m.checkin_qr_show_code(), QrCode)}
      {@render sheetGroup(m.tools_group_wrapup(), false)}
    </div>
  </div>
</ExampleBox>

<!-- ==================== A small tournament, start to finish ==================== -->

{@html renderGuideSection(m.og_step_create())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <Button variant="create" size="lg"><Plus class="w-4 h-4" /> {m.tournaments_new_btn()}</Button>
    <div class="rounded-lg border border-line-strong bg-surface-muted/40 p-4 space-y-3">
      <div>
        <span class="block text-sm text-ink-muted mb-1">{m.tfield_name_label()}</span>
        <input type="text" value="Alicante por la tarde" tabindex="-1"
          class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong" />
      </div>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <span class="block text-sm text-ink-muted mb-1">{m.tfield_format()}</span>
          <select tabindex="-1" class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong"><option>Standard</option></select>
        </div>
        <div>
          <span class="block text-sm text-ink-muted mb-1">{m.tfield_rank()}</span>
          <select tabindex="-1" class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong"><option>{m.tfield_rank_basic()}</option></select>
        </div>
      </div>
      <div>
        <span class="block text-sm text-ink-muted mb-1">{m.tfield_round_count()}</span>
        <select tabindex="-1" class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong"><option>2</option></select>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_registration())}

<ExampleBox>
  <Button variant="primary" size="lg">{m.overview_open_registration()}</Button>
</ExampleBox>

{@html renderGuideSection(m.og_step_checkin())}

<ExampleBox>
  <Button variant="primary" size="lg">{m.overview_close_registration()}</Button>
</ExampleBox>

<!-- The door desk: the action-bar button of that moment, then one roster card
     with its payment and deck controls already open. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <Button variant="secondary" size="md"><CheckCheck class="w-4 h-4" /> {m.overview_check_all_in()}</Button>
    <div class="bg-surface-muted/50 rounded-lg">
      <div class="p-3 pb-0">
        <div class="flex items-center gap-1.5">
          <span class="min-w-0 truncate text-ink text-sm">Alice</span>
          <span class="flex-1"></span>
          <Badge kind="status" tone="neutral">{m.player_state_registered()}</Badge>
        </div>
        <div class="mt-0.5 flex items-center gap-2 text-xs text-ink-faint">
          <span class="min-w-0 truncate">#1002345</span>
        </div>
      </div>
      <div class="px-3 pb-3 pt-2">
        <div class="flex items-center gap-2 flex-wrap">
          <Button variant="ghost" size="sm" class="min-h-[44px]"><Banknote class="w-3.5 h-3.5 text-warn" /><span class="text-warn">{m.payment_pending()}</span></Button>
          <Button variant="ghost" size="sm" class="min-h-[44px]"><FileX class="w-3.5 h-3.5 text-ink-faint" /><span class="text-ink-muted">{m.players_no_deck()}</span></Button>
          <Button variant="primary" size="sm" class="min-h-[44px]">{m.players_check_in()}</Button>
          <Button variant="ghost" size="sm" class="min-h-[44px] ml-auto"><Ellipsis class="w-3.5 h-3.5" /> {m.common_more()}</Button>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_payment())}

<!-- The badge IS the control — tapping it toggles the player's status. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <span class="text-ink text-sm">Alice</span>
      <Badge kind="control" tone="pending">{m.payment_pending()}</Badge>
      <span class="text-ink text-sm ml-3">Bob</span>
      <Badge kind="control" tone="info">{m.payment_paid()}</Badge>
    </div>
    {@render menu(m.payment_mark_all_paid(), Banknote)}
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_late())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <InlineNotice>{m.action_bar_unseated_notice({ names: "Diana" })}</InlineNotice>
    <div class="bg-surface-muted/50 rounded-lg p-4">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-sm font-medium text-ink-strong">{m.rounds_table_n({ n: "2" })}</h3>
        <Badge kind="status" tone="pending">{m.table_state_in_progress()}</Badge>
      </div>
      <div class="space-y-1 text-sm">
        {#each ["Alice", "Bob", "Charlie"] as name}
          <div class="py-2.5 flex items-center justify-between">
            <span class="text-ink">{name}</span>
            <span class="text-ink-faint text-xs">0GW 0TP</span>
          </div>
        {/each}
      </div>
      <div class="mt-2 pt-2 border-t border-line">
        <span class="text-xs text-ink-faint"><Plus class="w-3.5 h-3.5 inline mr-1" />{m.rounds_seat_player()}</span>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_round())}

<ExampleBox>
  <Button variant="primary" size="lg">{m.overview_start_round({ n: "1" })}</Button>
</ExampleBox>



{@html renderGuideSection(m.og_step_scoring())}

<!-- The real VpInput, so the chips can never drift from the ones players tap. -->
<ExampleBox>
  <div class="bg-surface-muted/50 rounded-lg p-4 max-w-sm">
    <div class="flex items-center justify-between mb-2 gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <ChevronDown class="w-4 h-4 text-ink-muted shrink-0" />
        <h3 class="text-sm font-medium truncate text-ink-strong">{m.rounds_table_n({ n: "1" })}</h3>
      </div>
      <Badge kind="status" tone="pending">{m.table_state_in_progress()}</Badge>
    </div>
    <div class="divide-y divide-line">
      {#each ["Alice", "Bob", "Charlie", "Diana"] as name}
        <div class="py-2.5">
          <div class="flex items-center justify-between gap-2 text-sm">
            <span class="text-ink min-w-0 truncate">{name}</span>
            <div class="flex items-center gap-2 shrink-0">
              <span class="text-ink-faint text-xs">0GW 0TP</span>
              <UserMinus class="w-3.5 h-3.5 text-ink-faint" />
              <TriangleAlert class="w-3.5 h-3.5 text-ink-faint" />
            </div>
          </div>
          <div class="mt-1.5">
            <VpInput value={0} options={[0, 0.5, 1, 1.5, 2, 3, 4]} label={name} onchange={() => {}} />
          </div>
        </div>
      {/each}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_override())}

<!-- A blocked table: the banner states the problem and the way out is the
     primary control, not the ghost one it is on a table that already adds up. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="banner-warn border rounded-lg p-3 space-y-1.5">
      <p class="text-xs flex items-start gap-1.5">
        <TriangleAlert class="w-4 h-4 shrink-0" />
        <span>{m.vp_blocked_redirected()}</span>
      </p>
      <p class="text-xs">{m.vp_blocked_override_hint()}</p>
    </div>
    <Button variant="primary" size="lg" block class="min-h-[44px]"><ShieldCheck class="w-4 h-4" />{m.vp_blocked_override_btn()}</Button>
    <div class="pt-2 border-t border-line">
      <p class="text-xs text-ink-faint mb-1.5">{m.override_usage_hint()}</p>
      <span class="text-xs text-ink-muted block mb-1">{m.override_judge_comment()}</span>
      <textarea
        class="w-full bg-surface-hover text-ink-strong text-xs rounded px-2 py-1 border border-line-strong resize-none"
        placeholder={m.override_placeholder()}
        rows="2"
        tabindex="-1"
      ></textarea>
      <div class="flex gap-2 mt-1 justify-end">
        <span class="px-2 py-1 text-xs text-ink-muted">{m.common_cancel()}</span>
        <Button variant="primary" size="sm">{m.override_save()}</Button>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_sanction())}

<ExampleBox>
  <div class="flex items-center gap-2 max-w-sm">
    <span class="text-ink text-sm flex-1">Charlie</span>
    <span class="w-2 h-2 rounded-full bg-warn inline-block"></span>
    <Button variant="secondary" size="sm"><TriangleAlert class="w-4 h-4 text-warn" />{m.players_sanction_btn()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_end_round())}

<ExampleBox>
  <div class="flex flex-wrap gap-2">
    <Button variant="primary" size="lg">{m.rounds_end_round()}</Button>
    <Button variant="danger" size="md"><Ban class="w-4 h-4" /> {m.rounds_cancel_round()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_toss())}

<ExampleBox>
  <div class="flex flex-wrap gap-2 items-center">
    <Button variant="secondary" size="md"><Dice3 class="w-4 h-4" /> {m.players_random_toss()}</Button>
    <Button variant="secondary" size="md">{m.players_edit_toss()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_finals())}

<ExampleBox>
  <div class="flex flex-wrap gap-2">
    <Button variant="primary" size="lg">{m.overview_start_finals()}</Button>
    <Button variant="secondary" size="md"><ArrowRightLeft class="w-4 h-4" /> {m.rounds_alter_seating()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_finish())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <Button variant="primary" size="lg">{m.finals_finish()}</Button>
    <InlineNotice tone="warn" icon={TriangleAlert}>{m.decks_winner_nudge_organizer({ name: "Alice" })}</InlineNotice>
    <div class="rounded-lg border border-line overflow-hidden">
      {@render sheetGroup(m.tools_group_wrapup(), true)}
      {@render sheetRow(m.overview_finish_tournament(), TriangleAlert)}
      {@render sheetRow(m.overview_reopen_tournament(), Undo2)}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_share())}

<ExampleBox>
  <div class="space-y-3">
    <Button variant="ghost" size="md"><Share2 class="w-4 h-4" /> {m.tournament_share()}</Button>
    <div class="rounded-lg border border-line max-w-xs overflow-hidden">
      {@render sheetGroup(m.tools_group_wrapup(), true)}
      {@render sheetRow(m.tools_copy_results(), ClipboardCopy)}
      {@render sheetRow(m.tools_download_event(), Download)}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_step_promos())}

<ExampleBox>
  <!-- A labelled single-column form; each pool carries its eligible count. The
       optional Prize picker is left out here — it only lists promos you have
       already configured. -->
  <div class="space-y-3 max-w-sm">
    <div class="rounded-lg border border-line overflow-hidden">
      {@render sheetGroup(m.tools_group_wrapup(), true)}
      {@render sheetRow(m.promos_title(), Dices)}
      {@render sheetRow(m.raffle_title(), Dices)}
    </div>
    <div>
      <span class="block text-sm text-ink-muted mb-1">{m.raffle_name_label()}</span>
      <input type="text" value={m.raffle_name_default({ n: "1" })} tabindex="-1"
        class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong" />
    </div>
    <div>
      <span class="block text-sm text-ink-muted mb-1">{m.raffle_pool_label()}</span>
      <select tabindex="-1" class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong">
        <option>{m.raffle_pool_all_players()} (12)</option>
        <option>{m.raffle_pool_non_finalists()} (7)</option>
        <option>{m.raffle_pool_game_winners()} (4)</option>
        <option>{m.raffle_pool_no_game_win()} (8)</option>
        <option>{m.raffle_pool_no_victory_point()} (3)</option>
      </select>
    </div>
    <div>
      <span class="block text-sm text-ink-muted mb-1">{m.raffle_winners()}</span>
      <div class="flex items-center gap-1.5">
        <span class="min-w-[44px] min-h-[44px] flex items-center justify-center bg-surface-hover border border-line-strong rounded-lg text-ink-strong">&minus;</span>
        <input type="number" value="1" tabindex="-1" class="w-16 px-2 py-2 min-h-[44px] text-sm text-center bg-surface-hover border border-line-strong rounded-lg text-ink-strong" />
        <span class="min-w-[44px] min-h-[44px] flex items-center justify-center bg-surface-hover border border-line-strong rounded-lg text-ink-strong">+</span>
      </div>
    </div>
    <div class="flex items-center gap-1.5 py-2 min-h-[44px] text-sm text-ink">
      <input type="checkbox" tabindex="-1" class="rounded border-line-strong" />
      {m.raffle_exclude_drawn()}
    </div>
    <Button variant="primary" size="md" block><Dices class="w-4 h-4" /> {m.raffle_draw_one({ count: "1" })}</Button>
    <div class="flex flex-wrap items-center gap-2">
      <Button variant="ghost" size="md"><Undo2 class="w-3.5 h-3.5" /> {m.raffle_undo_last()}</Button>
      <Button variant="danger" size="md"><Trash2 class="w-3.5 h-3.5" /> {m.raffle_clear()}</Button>
    </div>
  </div>
</ExampleBox>

<!-- ==================== Offline: the first option branch ==================== -->

{@html renderGuideSection(m.og_offline())}

<ExampleBox>
  <Button variant="ghost" size="md"><WifiOff class="w-4 h-4" /> {m.offline_go_offline()}</Button>
</ExampleBox>

{@html renderGuideSection(m.og_offline_prepare())}

<ExampleBox>
  <!-- One banner: the way back online rides inside it, not underneath. -->
  <div class="banner-warn border rounded-lg p-4 flex items-center justify-between gap-4 max-w-md">
    <div class="flex items-center gap-2 min-w-0">
      <WifiOff class="w-5 h-5 shrink-0" />
      <div class="min-w-0">
        <span class="text-warn font-medium text-sm">{m.offline_mode_banner()}</span>
        <span class="text-xs text-ink-muted ml-2">{m.offline_last_sync({ time: "14:32" })}</span>
      </div>
    </div>
    <div class="shrink-0">
      <Button variant="primary" size="lg"><Wifi class="w-4 h-4" /> {m.offline_go_online()}</Button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_force_takeover())}

<!-- ==================== Bigger events ==================== -->

{@html renderGuideSection(m.og_adv_prereg())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex items-center gap-2">
      <span class="text-ink text-sm flex-1">Erik</span>
      <Badge kind="status" tone="pending">{m.waitlist_label()}</Badge>
      <Button variant="secondary" size="sm">{m.waitlist_promote()}</Button>
    </div>
    <div class="rounded-lg border border-line overflow-hidden">
      {@render sheetGroup(m.tools_group_setup(), true)}
      {@render sheetRow(m.csv_import_title(), Upload)}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_adv_qr())}

<ExampleBox>
  <Button variant="secondary" size="md"><QrCode class="w-4 h-4" /> {m.checkin_qr_show_code()}</Button>
</ExampleBox>

{@html renderGuideSection(m.og_adv_approach())}

{@html renderGuideSection(m.og_adv_seating())}

<ExampleBox>
  <Button variant="secondary" size="md"><Printer class="w-4 h-4" /> {m.rounds_print_seating()}</Button>
</ExampleBox>



<!-- The round toolbar, then the editor Alter seating opens: its Save/Cancel pair
     is the moment's real CTA, so it leads. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex flex-wrap gap-2">
      <Button variant="secondary" size="md"><ArrowRightLeft class="w-4 h-4" /> {m.rounds_alter_seating()}</Button>
      <Button variant="danger" size="md"><Ban class="w-4 h-4" /> {m.rounds_cancel_round()}</Button>
    </div>
    <div class="space-y-3">
      <div class="flex gap-2 flex-wrap">
        <Button variant="primary" size="lg">{m.rounds_save_seating()}</Button>
        <Button variant="secondary" size="lg">{m.common_cancel()}</Button>
      </div>
      <div class="bg-surface-muted/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">{m.rounds_table_n({ n: "1" })}</h3>
        <div class="divide-y divide-line">
          {#each ["Alice", "Bob", "Charlie", "Diana"] as name, i}
            <div class="w-full min-h-[44px] py-1.5 px-1 flex items-center gap-2 text-sm">
              <span class="w-5 text-center text-xs text-ink-faint tabular-nums">{i + 1}</span>
              <span class="flex-1 text-ink">{name}</span>
              <ArrowRightLeft class="w-4 h-4 shrink-0 text-ink-faint" />
            </div>
          {/each}
        </div>
      </div>
      <Button variant="secondary" size="md"><SquarePlus class="w-4 h-4" /> {m.rounds_add_table()}</Button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_adv_cancel_round())}

{@html renderGuideSection(m.og_adv_banner())}

{@html renderGuideSection(m.og_timer())}

<!-- The clock counts in minutes, not hours, and runs past zero into a negative
     count-up. Pause swaps places with Start depending on whether it is running. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-4 justify-center">
      {#each [{ t: "83:45", c: "text-info" }, { t: "4:30", c: "text-warn" }, { t: "-0:12", c: "text-link" }] as clock}
        <span class="font-mono text-2xl font-bold tabular-nums {clock.c}">{clock.t}</span>
      {/each}
    </div>
    <p class="text-xs text-ink-muted text-center">+2:00 {m.timer_extra_time()}</p>
    <div class="flex gap-2 justify-center">
      <Button variant="secondary" size="sm"><Pause class="w-3 h-3" /> {m.timer_pause()}</Button>
      <Button variant="ghost" size="sm"><RotateCcw class="w-3 h-3" /> {m.timer_reset()}</Button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_timer_controls())}

<ExampleBox>
  <div class="flex flex-wrap gap-1 max-w-sm">
    {#each ["1", "2", "5", "10"] as n}
      <Button variant="ghost" size="sm">+{n}min</Button>
    {/each}
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_timer_extensions())}

{@html renderGuideSection(m.og_judge_calls())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <Button variant="primary" size="lg" block><Gavel class="w-5 h-5" /> {m.judge_call_btn()}</Button>
    {#each [{ t: "3", p: "Alice" }, { t: "7", p: "Bob" }] as call}
      <div class="banner-warn border rounded-lg p-3 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Gavel class="w-5 h-5 text-warn shrink-0" />
          <div>
            <span class="text-sm font-medium text-ink-strong">{m.judge_call_alert()}</span>
            <span class="text-sm text-ink ml-1">{m.rounds_table_n({ n: call.t })} &mdash; {call.p}</span>
          </div>
        </div>
        <X class="w-4 h-4 text-ink-muted" />
      </div>
    {/each}
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_online_checkin())}

<ExampleBox>
  <Button variant="secondary" size="md"><RotateCcw class="w-4 h-4" /> {m.overview_reset_checkin()}</Button>
</ExampleBox>

{@html renderGuideSection(m.og_deck_management())}

<ExampleBox>
  <Button variant="secondary" size="md"><QrCode class="w-4 h-4" /> {m.deck_upload_scan_qr()}</Button>
</ExampleBox>

{@html renderGuideSection(m.og_announcements())}

<ExampleBox>
  <div class="flex gap-2 items-start max-w-sm">
    <textarea tabindex="-1" rows="2" placeholder={m.announcement_composer_placeholder()}
      class="flex-1 bg-surface-hover text-ink-strong text-sm rounded-lg px-3 py-2 border border-line-strong resize-none"></textarea>
    <Button variant="primary" size="md">{m.announcement_post()}</Button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_co_organizers())}

{@html renderGuideSection(m.og_proxy_players())}

<!-- ==================== Online events ==================== -->

{@html renderGuideSection(m.og_online_intro())}

{@html renderGuideSection(m.og_discord())}

{@html renderGuideSection(m.og_parallel_rounds())}

<!-- ==================== Open rounds ==================== -->

{@html renderGuideSection(m.og_open_rounds())}

{@html renderGuideSection(m.og_self_organized())}

<!-- ==================== Reference ==================== -->

{@html renderGuideSection(m.og_configuration())}

<!-- One card per section of the real settings form (Tools > Settings), in the same order, so the
     reference reads as a map of the screen rather than a second taxonomy to translate. -->
<div class="not-prose my-4 grid gap-3 sm:grid-cols-2">
  <div class="rounded-lg border border-line-strong bg-surface-muted/40 p-4">
    <h4 class="text-sm font-semibold text-ink-strong mb-2">{m.og_cfg_play_options()}</h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ink inline font-medium">{m.og_cfg_allow_proxies()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_allow_proxies_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_multideck()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_multideck_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_decklist_required()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_decklist_required_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_league()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_league_desc()}</dd></div>
    </dl>
  </div>
  <div class="rounded-lg border border-line-strong bg-surface-muted/40 p-4">
    <h4 class="text-sm font-semibold text-ink-strong mb-2">{m.og_cfg_other_settings()}</h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ink inline font-medium">{m.og_cfg_max_rounds()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_max_rounds_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_max_players()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_max_players_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_open_rounds()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_open_rounds_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_self_organized()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_self_organized_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_round_time()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_round_time_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_finals_time()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_finals_time_desc()}</dd></div>
    </dl>
  </div>
  <div class="rounded-lg border border-line-strong bg-surface-muted/40 p-4">
    <h4 class="text-sm font-semibold text-ink-strong mb-2">{m.og_cfg_standings_visibility()}</h4>
    <p class="text-xs text-ink-faint mb-1.5">{m.og_cfg_standings_visibility_hint()}</p>
    <dl class="space-y-1 text-sm">
      <div><dt class="text-ink inline font-medium">{m.og_cfg_private()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_private_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_cutoff()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_cutoff_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_top10()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_top10_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_public()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_public_desc()}</dd></div>
    </dl>
    <p class="text-xs text-ink-faint mt-1.5">{m.og_cfg_standings_always_public()}</p>
  </div>
  <div class="rounded-lg border border-line-strong bg-surface-muted/40 p-4">
    <h4 class="text-sm font-semibold text-ink-strong mb-2">{m.og_cfg_decklists_mode()}</h4>
    <p class="text-xs text-ink-faint mb-1.5">{m.og_cfg_decklists_mode_hint()}</p>
    <dl class="space-y-1 text-sm">
      <div><dt class="text-ink inline font-medium">{m.og_cfg_winner()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_winner_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_finalists()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_finalists_desc()}</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_all()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_all_desc()}</dd></div>
    </dl>
    <p class="text-xs text-ink-faint mt-1.5">{m.og_cfg_decklists_immediate()}</p>
  </div>
  <div class="rounded-lg border border-line-strong bg-surface-muted/40 p-4 sm:col-span-2">
    <h4 class="text-sm font-semibold text-ink-strong mb-2">{m.og_cfg_venue()}</h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ink inline font-medium">{m.og_cfg_table_rooms()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_table_rooms_desc()}</dd></div>
    </dl>
  </div>
</div>

{@html renderGuideSection(m.og_scoring_reference())}

{@html renderGuideSection(m.og_sanctions_reference())}

{@html renderGuideSection(m.og_delete_tournament())}

{@html renderGuideSection(m.og_reference())}

{@html renderGuideSection(m.og_community_curation())}

{@html renderGuideSection(m.og_faq_heading())}

<div class="not-prose my-6 space-y-1">
  {#each faqs as faq, i}
    <div class="border border-line-strong rounded-lg overflow-hidden">
      <button
        class="w-full px-4 py-3 flex items-center gap-2 text-left text-sm font-medium text-ink-strong hover:bg-surface-muted/50 transition-colors"
        onclick={() => openFaq = openFaq === i ? null : i}
      >
        {#if openFaq === i}
          <ChevronDown class="w-4 h-4 text-ink-muted shrink-0" />
        {:else}
          <ChevronRight class="w-4 h-4 text-ink-muted shrink-0" />
        {/if}
        {faq.q}
      </button>
      {#if openFaq === i}
        <div class="px-4 pb-3 text-sm text-ink doc-prose prose max-w-none">
          {@html renderGuideSection(faq.a)}
        </div>
      {/if}
    </div>
  {/each}
</div>
