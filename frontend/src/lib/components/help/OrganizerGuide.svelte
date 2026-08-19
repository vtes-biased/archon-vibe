<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";
  import ExampleBox from "./ExampleBox.svelte";
  import {
    QrCode, WifiOff, Wifi, Share2, ClipboardCopy, Download, Dices, Dice3, Undo2, Trash2,
    Pause, RotateCcw, ChevronDown, ChevronRight,
    ShieldCheck, TriangleAlert, Gavel, X, Ban,
    Wrench, Users, Swords, Plus, SquarePlus, ArrowRightLeft,
    CheckCheck, MoreHorizontal, Ellipsis, Banknote, FileX, UserMinus, Info,
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

{@html renderGuideSection(m.og_intro())}

<!-- The console in miniature; later sections name places on this picture. -->
<ExampleBox>
  <div class="space-y-4 max-w-sm">
    <!-- Masthead: title, badges and the button row sit ABOVE the console card,
         not inside it. -->
    <div class="space-y-2">
      <h3 class="text-lg font-semibold text-accent leading-tight">Alicante por la tarde</h3>
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="inline-flex items-center gap-1 rounded text-xs font-medium px-2 py-0.5 badge-pending">Check-in</span>
        <span class="inline-flex items-center gap-1 rounded text-xs font-medium px-2 py-0.5 bg-surface-muted text-ink-muted">Standard</span>
        <span class="inline-flex items-center gap-1 rounded text-xs font-medium px-2 py-0.5 bg-surface-muted text-ink-muted">Proxies allowed</span>
      </div>
      <div class="flex flex-wrap items-center gap-2 pt-0.5">
        <span class="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-line-strong text-ink"><Share2 class="w-4 h-4" /> Share</span>
        <span class="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-line-strong text-ink"><WifiOff class="w-4 h-4" /> Go Offline</span>
        <span class="inline-flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-line-strong text-ink"><Wrench class="w-4 h-4" /> Tools</span>
      </div>
    </div>

    <!-- The console card: action bar on top, then the tab row. -->
    <div class="rounded-lg border border-line overflow-hidden">
      <div class="border-b border-line px-3 py-3 space-y-3">
        <div class="flex items-center gap-1 text-xs">
          <span class="w-2 h-2 rounded-full bg-info inline-block"></span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="w-2 h-2 rounded-full bg-info inline-block"></span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="text-link font-medium whitespace-nowrap"><span class="w-2 h-2 rounded-full bg-accent inline-block mr-1 align-middle"></span>Check-in</span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="w-2 h-2 rounded-full bg-surface-active inline-block"></span>
          <span class="text-ink-faint" aria-hidden="true">—</span>
          <span class="w-2 h-2 rounded-full bg-surface-active inline-block"></span>
        </div>
        <p class="text-sm text-ink-muted">Round 1 complete. Check in for next round.</p>
        <div class="flex flex-wrap items-center gap-2">
          <span class="inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium bg-accent-strong text-white rounded-lg">Start Round 2</span>
          <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><CheckCheck class="w-4 h-4" /> Check All In</span>
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><MoreHorizontal class="w-4 h-4" /> More</span>
        </div>
      </div>
      <!-- Tab row: a tab exists only where it has something to show, and on a
           phone only the active one spells itself out. -->
      <div class="flex">
        <span class="flex items-center gap-1.5 px-4 py-3 text-sm font-medium border-b-2 border-accent text-ink-strong"><Users class="w-4 h-4" /> Players</span>
        <span class="flex items-center px-4 py-3 border-b-2 border-transparent text-ink-muted"><Swords class="w-4 h-4" /></span>
      </div>
    </div>

    <!-- the Tools drawer, opened on the group matching the state above -->
    <div class="rounded-lg border border-line overflow-hidden">
      <div class="flex items-center justify-between border-b border-line px-4 py-3">
        <span class="text-sm font-semibold text-ink-strong">Tools</span>
        <X class="w-5 h-5 text-ink-muted" />
      </div>
      <div class="flex items-center gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted"><ChevronRight class="w-4 h-4" /> Set up</div>
      <div class="flex items-center gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted"><ChevronDown class="w-4 h-4" /> At the door</div>
      <div class="flex items-center gap-3 px-4 py-3 min-h-[44px] text-sm text-ink-bright"><QrCode class="w-4 h-4 shrink-0" /><span class="flex-1">Show Check-in QR Code</span><ChevronRight class="w-4 h-4 shrink-0 text-ink-faint" /></div>
      <div class="flex items-center gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted"><ChevronRight class="w-4 h-4" /> Wrap up</div>
    </div>
  </div>
</ExampleBox>

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
      <div><dt class="text-ink inline font-medium">{m.og_cfg_round_time()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_round_time_desc()} ({m.og_cfg_timer_online_only()})</dd></div>
      <div><dt class="text-ink inline font-medium">{m.og_cfg_finals_time()}</dt> <dd class="text-ink-muted inline">— {m.og_cfg_finals_time_desc()} ({m.og_cfg_timer_online_only()})</dd></div>
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

{@html renderGuideSection(m.og_open_rounds())}

{@html renderGuideSection(m.og_self_organized())}

{@html renderGuideSection(m.og_co_organizers())}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white rounded-lg">
    Open Registration
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_registration_tips())}

<!-- Back to Planning is not a button of its own: it is a row inside the action
     bar's More menu, which the prose below says in words. -->
<ExampleBox>
  <div class="flex flex-wrap items-start gap-2">
    <span class="inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium bg-accent-strong text-white rounded-lg">
      Start Check-in
    </span>
    <div>
      <span class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><MoreHorizontal class="w-4 h-4" /> More</span>
      <div class="mt-1 min-w-[12rem] rounded-lg border border-line-strong bg-surface-muted py-1 shadow-lg">
        <span class="flex w-full items-center gap-2 px-3 py-2 text-sm text-ink-bright"><Undo2 class="w-4 h-4 shrink-0" /> Back to Planning</span>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_checkin_back())}

<!-- First check-in: the two action-bar buttons of that moment, then one roster
     card in door mode, where the payment and deck controls sit open. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex flex-wrap gap-2">
      <span class="inline-flex items-center justify-center px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg">Show Check-in QR Code</span>
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><CheckCheck class="w-4 h-4" /> Check All In</span>
    </div>
    <div class="bg-surface-muted/50 rounded-lg">
      <div class="p-3 pb-0">
        <div class="flex items-center gap-1.5">
          <span class="min-w-0 truncate text-ink text-sm">Alice</span>
          <span class="flex-1"></span>
          <span class="text-xs px-2 py-0.5 rounded bg-surface-hover text-ink-muted">Registered</span>
        </div>
        <div class="mt-0.5 flex items-center gap-2 text-xs text-ink-faint">
          <span class="min-w-0 truncate">#1002345</span>
        </div>
      </div>
      <div class="px-3 pb-3 pt-2">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="inline-flex items-center justify-center gap-1 px-2 py-1 min-h-[44px] text-xs rounded-lg border border-line-strong"><Banknote class="w-3.5 h-3.5 text-warn" /><span class="text-warn">Pending</span></span>
          <span class="inline-flex items-center justify-center gap-1 px-2 py-1 min-h-[44px] text-xs rounded-lg border border-line-strong"><FileX class="w-3.5 h-3.5 text-ink-faint" /><span class="text-ink-muted">No deck uploaded</span></span>
          <span class="inline-flex items-center justify-center gap-1 px-2 py-1 min-h-[44px] text-xs bg-accent-strong text-white rounded-lg">Check in</span>
          <span class="inline-flex items-center justify-center gap-1 px-2 py-1 min-h-[44px] ml-auto text-xs rounded-lg border border-line-strong text-ink"><Ellipsis class="w-3.5 h-3.5" /> More</span>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_checkin_methods())}

<!-- Action bar names them, Rounds tab seats them. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex items-start gap-2 text-sm text-ink-muted">
      <Info class="w-4 h-4 mt-0.5 shrink-0" />
      <span>Checked in but not seated this round: Diana. Seat them at a table with room, or leave them for the next round — your call.</span>
    </div>
    <div class="bg-surface-muted/50 rounded-lg p-4">
      <div class="flex items-center justify-between mb-2">
        <h3 class="text-sm font-medium text-ink-strong">Table 2</h3>
        <span class="text-xs px-2 py-0.5 rounded badge-pending">In Progress</span>
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
        <button class="text-xs text-ink-faint">
          <Plus class="w-3.5 h-3.5 inline mr-1" />Seat a player
        </button>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_checkin_rules())}

<ExampleBox>
  <div>
    <span class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><MoreHorizontal class="w-4 h-4" /> More</span>
    <div class="mt-1 min-w-[12rem] max-w-xs rounded-lg border border-line-strong bg-surface-muted py-1 shadow-lg">
      <span class="flex w-full items-center gap-2 px-3 py-2 text-sm text-ink-bright"><Undo2 class="w-4 h-4 shrink-0" /> Reopen Registration</span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_deck_management())}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white rounded-lg">
    Start Round 1
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_round_start_details())}

<!-- The round toolbar, then the editor Alter seating opens: its Save/Cancel pair
     is the moment's real CTA, so it leads. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex flex-wrap gap-2">
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><ArrowRightLeft class="w-4 h-4" /> Alter seating</span>
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg">Finish Round 2</span>
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm btn-danger rounded-lg"><Ban class="w-4 h-4" /> Cancel Round</span>
    </div>
    <div class="space-y-3">
      <p class="text-sm text-ink">Tap a player, then tap a seat to swap them — or an open seat to move them.</p>
      <div class="flex gap-2 flex-wrap">
        <span class="inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium bg-accent-strong text-white rounded-lg">Save seating</span>
        <span class="inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium bg-surface-hover text-ink-bright rounded-lg">Cancel</span>
      </div>
      <div class="bg-surface-muted/50 rounded-lg p-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">Table 1</h3>
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
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><SquarePlus class="w-4 h-4" /> Table</span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_scoring_intro())}

<!-- A table unfolded with Manage: whole-number VP chips per seat, with the half
     as its own toggle. -->
<ExampleBox>
  <div class="bg-surface-muted/50 rounded-lg p-4 max-w-sm">
    <div class="flex items-center justify-between mb-2 gap-2">
      <div class="flex items-center gap-2 min-w-0">
        <ChevronDown class="w-4 h-4 text-ink-muted shrink-0" />
        <h3 class="text-sm font-medium truncate text-ink-strong">Table 1</h3>
      </div>
      <span class="text-xs px-2 py-0.5 rounded badge-pending shrink-0">In Progress</span>
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
          <div class="mt-1.5 flex flex-wrap items-center gap-1">
            {#each [0, 1, 2, 3, 4] as vp}
              <span class="h-11 min-w-11 px-2 flex items-center justify-center rounded-lg border text-sm font-semibold tabular-nums {vp === 0 ? 'bg-accent-strong text-white border-accent-strong-hover ring-2 ring-accent' : 'bg-surface-hover text-ink-strong border-line-strong'}">{vp}</span>
            {/each}
            <span class="h-11 min-w-11 px-2 ml-1 flex items-center justify-center rounded-lg border text-sm font-semibold tabular-nums bg-surface-hover text-ink-strong border-line-strong">+½</span>
          </div>
        </div>
      {/each}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_scoring_details())}

<!-- Three moments of one flow, not three peers: the trigger at the foot of an
     unfolded table, the comment form it opens, and — on a table that already
     carries one — the overridden line with its undo. -->
<ExampleBox>
  <div class="space-y-4 max-w-sm">
    <div class="flex justify-end">
      <span class="px-2 py-1 text-xs text-warn"><ShieldCheck class="w-3.5 h-3.5 inline mr-1" />Override</span>
    </div>
    <div class="pt-2 border-t border-line">
      <p class="text-xs text-ink-faint mb-1.5">Use Override for a judge ruling on a disputed or abandoned table — for a wrong number, correct the VPs instead.</p>
      <span class="text-xs text-ink-muted block mb-1">Judge comment (required)</span>
      <textarea
        class="w-full bg-surface-hover text-ink-strong text-xs rounded px-2 py-1 border border-line-strong resize-none"
        placeholder="Explain why this table result is being overridden..."
        rows="2"
        tabindex="-1"
      ></textarea>
      <div class="flex gap-2 mt-1 justify-end">
        <span class="px-2 py-1 text-xs text-ink-muted">Cancel</span>
        <span class="inline-flex items-center justify-center gap-1 px-2 py-1 text-xs bg-accent-strong text-white rounded-lg">Override &rarr; Finished</span>
      </div>
    </div>
    <div class="pt-2 border-t border-line flex items-center justify-between gap-2">
      <span class="text-xs text-warn min-w-0"><ShieldCheck class="w-3.5 h-3.5 inline mr-1" />Overridden: Time expired, ruling by head judge</span>
      <span class="px-2 py-1 text-xs text-ink-faint shrink-0">Remove override</span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_override_remove())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <!-- What the player taps at their table: full-width, the loudest control on
         their screen. -->
    <div class="w-full flex items-center justify-center gap-2 px-4 py-2 min-h-[44px] text-sm font-medium bg-accent-strong text-white rounded-lg">
      <Gavel class="w-5 h-5" />
      Call Judge
    </div>
    <div class="banner-warn border rounded-lg p-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Gavel class="w-5 h-5 text-warn shrink-0" />
        <div>
          <span class="text-sm font-medium text-ink-strong">Judge Call!</span>
          <span class="text-sm text-ink ml-1">Table 3 &mdash; Alice</span>
        </div>
      </div>
      <button class="text-ink-muted p-1">
        <X class="w-4 h-4" />
      </button>
    </div>
    <div class="banner-warn border rounded-lg p-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Gavel class="w-5 h-5 text-warn shrink-0" />
        <div>
          <span class="text-sm font-medium text-ink-strong">Judge Call!</span>
          <span class="text-sm text-ink ml-1">Table 7 &mdash; Bob</span>
        </div>
      </div>
      <button class="text-ink-muted p-1">
        <X class="w-4 h-4" />
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_finishing_round())}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium bg-accent-strong hover:bg-accent-strong-hover text-white rounded-lg">
    End Round
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_between_rounds())}

<ExampleBox>
  <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm btn-danger rounded-lg">
    <Ban class="w-4 h-4" />
    Cancel Round
  </span>
</ExampleBox>

<!-- Must not sit between og_timer_extensions and og_payment_tip: one section. -->
{@html renderGuideSection(m.og_proxy_players())}

{@html renderGuideSection(m.og_announcements())}

{@html renderGuideSection(m.og_timer())}

<!-- The clock counts in minutes, not hours, and runs past zero into a negative
     count-up. Pause swaps places with Start depending on whether it is running. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-4 justify-center">
      <div class="text-center">
        <span class="font-mono text-2xl font-bold tabular-nums text-info">83:45</span>
        <p class="text-xs text-ink-faint mt-1">Time remaining</p>
      </div>
      <div class="text-center">
        <span class="font-mono text-2xl font-bold tabular-nums text-warn">4:30</span>
        <p class="text-xs text-ink-faint mt-1">&lt; 5 minutes</p>
      </div>
      <div class="text-center">
        <span class="font-mono text-2xl font-bold tabular-nums text-link">-0:12</span>
        <p class="text-xs text-ink-faint mt-1">Expired</p>
      </div>
    </div>
    <div class="flex gap-2 justify-center">
      <span class="inline-flex items-center justify-center gap-1 px-2 py-1 text-xs bg-surface-hover text-ink-bright rounded-lg">
        <Pause class="w-3 h-3" />
        Pause
      </span>
      <span class="inline-flex items-center justify-center gap-1 px-2 py-1 text-xs rounded-lg border border-line-strong text-ink">
        <RotateCcw class="w-3 h-3" />
        Reset
      </span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_timer_controls())}

<ExampleBox>
  <div class="space-y-2 max-w-sm">
    <div class="text-xs text-ink-muted">+2:00 extra</div>
    <div class="flex flex-wrap gap-1">
      {#each ["+1min", "+2min", "+5min", "+10min"] as label}
        <span class="inline-flex items-center justify-center gap-1 px-2 py-1 text-xs rounded-lg border border-line-strong text-ink">{label}</span>
      {/each}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_timer_extensions())}

<!-- og_timer_extensions ends by introducing Payment Tracking — keep adjacent. -->
<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <!-- The badge IS the control — tapping it toggles the player's status. -->
    <div class="flex gap-2 items-center">
      <span class="text-ink text-sm">Alice</span>
      <button type="button" tabindex="-1" class="px-2 py-0.5 text-xs rounded badge-pending">Pending</button>
      <span class="text-ink text-sm ml-3">Bob</span>
      <button type="button" tabindex="-1" class="px-2 py-0.5 text-xs rounded badge-success">Paid</button>
    </div>
    <div>
      <span class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg"><MoreHorizontal class="w-4 h-4" /> More</span>
      <div class="mt-1 min-w-[12rem] max-w-xs rounded-lg border border-line-strong bg-surface-muted py-1 shadow-lg">
        <span class="flex w-full items-center gap-2 px-3 py-2 text-sm text-ink-bright"><Banknote class="w-4 h-4 shrink-0" /> Mark All Paid</span>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_payment_tip())}

<ExampleBox>
  <div class="flex flex-wrap gap-2 items-center">
    <span class="inline-flex items-center justify-center px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg whitespace-nowrap">
      <Dice3 class="w-4 h-4 inline mr-1" />
      Random toss
    </span>
    <span class="inline-flex items-center justify-center px-3 py-1.5 text-sm bg-surface-hover text-ink-bright rounded-lg whitespace-nowrap">
      Edit toss
    </span>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_finals_toss())}

{@html renderGuideSection(m.og_winner_deck_missing())}

<ExampleBox>
  <div class="banner-warn border rounded-lg p-3 flex items-start gap-2 text-sm max-w-sm">
    <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" />
    <span class="min-w-0">Winner's decklist is missing. Please remind Alice to upload their deck.</span>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_finish_no_finals())}

<ExampleBox>
  <!-- The Tools sheet's Wrap up group. Reopen Tournament takes this row's place
       once the event is Finished — the two never show together. -->
  <div class="rounded-lg border border-line max-w-xs overflow-hidden">
    <div class="flex items-center gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted"><ChevronDown class="w-4 h-4" /> Wrap up</div>
    <div class="flex items-center gap-3 px-4 py-3 min-h-[44px] text-sm text-ink-bright">
      <TriangleAlert class="w-4 h-4 shrink-0" />
      Finish Tournament
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_reopen())}

<ExampleBox>
  <div class="space-y-3">
    <div>
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-line-strong text-ink">
        <Share2 class="w-4 h-4" />
        Share
      </span>
    </div>
    <div class="rounded-lg border border-line max-w-xs overflow-hidden">
      <div class="flex items-center gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-ink-muted"><ChevronDown class="w-4 h-4" /> Wrap up</div>
      <div class="flex items-center gap-3 px-4 py-3 min-h-[44px] text-sm text-ink-bright">
        <ClipboardCopy class="w-4 h-4 shrink-0" />
        Copy results
      </div>
      <div class="flex items-center gap-3 px-4 py-3 min-h-[44px] text-sm text-ink-bright">
        <Download class="w-4 h-4 shrink-0" />
        Download a copy of the event
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_sharing_details())}

<ExampleBox>
  <!-- A labelled single-column form; each pool carries its eligible count. The
       optional Prize picker is left out here — it only lists promos you have
       already configured. -->
  <div class="space-y-3 max-w-sm">
    <div>
      <span class="block text-sm text-ink-muted mb-1">Draw name</span>
      <input type="text" value="Raffle 1" tabindex="-1"
        class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong" />
    </div>
    <div>
      <span class="block text-sm text-ink-muted mb-1">Draw from</span>
      <select tabindex="-1" class="w-full px-3 py-2 min-h-[44px] text-sm bg-surface-hover border border-line-strong rounded-lg text-ink-strong">
        <option>All players (12)</option>
        <option>Non-finalists (7)</option>
        <option>Game winners (4)</option>
        <option>No game win (8)</option>
        <option>No victory point (3)</option>
      </select>
    </div>
    <div>
      <span class="block text-sm text-ink-muted mb-1">Winners</span>
      <div class="flex items-center gap-1.5">
        <span class="min-w-[44px] min-h-[44px] flex items-center justify-center bg-surface-hover border border-line-strong rounded-lg text-ink-strong">&minus;</span>
        <input type="number" value="1" tabindex="-1" class="w-16 px-2 py-2 min-h-[44px] text-sm text-center bg-surface-hover border border-line-strong rounded-lg text-ink-strong" />
        <span class="min-w-[44px] min-h-[44px] flex items-center justify-center bg-surface-hover border border-line-strong rounded-lg text-ink-strong">+</span>
      </div>
    </div>
    <div class="flex items-center gap-1.5 py-2 min-h-[44px] text-sm text-ink">
      <input type="checkbox" tabindex="-1" class="rounded border-line-strong" />
      Exclude previous winners
    </div>
    <div class="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm bg-accent-strong text-white rounded-lg">
      <Dices class="w-4 h-4" />
      Draw 1 winner
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-line-strong text-ink">
        <Undo2 class="w-3.5 h-3.5" />
        Undo last draw
      </span>
      <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm btn-danger rounded-lg">
        <Trash2 class="w-3.5 h-3.5" />
        Clear all draws
      </span>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_offline())}

<ExampleBox>
  <span class="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-line-strong text-ink">
    <WifiOff class="w-4 h-4" />
    Go Offline
  </span>
</ExampleBox>

{@html renderGuideSection(m.og_offline_prepare())}

<ExampleBox>
  <!-- One banner: the way back online rides inside it, not underneath. -->
  <div class="banner-warn border rounded-lg p-4 flex items-center justify-between gap-4 max-w-md">
    <div class="flex items-center gap-2 min-w-0">
      <WifiOff class="w-5 h-5 shrink-0" />
      <div class="min-w-0">
        <span class="text-warn font-medium text-sm">OFFLINE MODE — Changes are stored locally</span>
        <span class="text-xs text-ink-muted ml-2">Last saved: 14:32</span>
      </div>
    </div>
    <span class="shrink-0 inline-flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium bg-accent-strong text-white rounded-lg">
      <Wifi class="w-4 h-4" />
      Go Back Online
    </span>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_force_takeover())}

{@html renderGuideSection(m.og_discord())}

{@html renderGuideSection(m.og_community_curation())}

{@html renderGuideSection(m.og_reference())}

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
