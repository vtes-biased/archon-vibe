<script lang="ts">
  import { renderGuideSection } from "$lib/markdown";
  import * as m from "$lib/paraglide/messages.js";
  import ExampleBox from "./ExampleBox.svelte";
  import {
    QrCode, WifiOff, Wifi, Share2, ClipboardCopy, Download, Dices, Dice3, Undo2, Trash2,
    Play, Pause, RotateCcw, Clock, ChevronDown, ChevronRight,
    ShieldCheck, PauseCircle, PlayCircle, Gavel, X,
  } from "lucide-svelte";

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
  ];
</script>

{@html renderGuideSection(m.og_intro())}

<div class="not-prose my-4 grid gap-3 sm:grid-cols-2">
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">{m.og_cfg_play_options()}</h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_allow_proxies()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_allow_proxies_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_multideck()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_multideck_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_decklist_required()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_decklist_required_desc()}</dd></div>
    </dl>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">{m.og_cfg_standings_visibility()}</h4>
    <p class="text-xs text-ash-500 mb-1.5">{m.og_cfg_standings_visibility_hint()}</p>
    <dl class="space-y-1 text-sm">
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_private()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_private_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_cutoff()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_cutoff_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_top10()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_top10_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_public()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_public_desc()}</dd></div>
    </dl>
    <p class="text-xs text-ash-500 mt-1.5">{m.og_cfg_standings_always_public()}</p>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">{m.og_cfg_decklists_mode()}</h4>
    <p class="text-xs text-ash-500 mb-1.5">{m.og_cfg_decklists_mode_hint()}</p>
    <dl class="space-y-1 text-sm">
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_winner()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_winner_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_finalists()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_finalists_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_all()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_all_desc()}</dd></div>
    </dl>
    <p class="text-xs text-ash-500 mt-1.5">{m.og_cfg_decklists_immediate()}</p>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">{m.og_cfg_timer()} <span class="text-xs text-ash-500 font-normal">({m.og_cfg_timer_online_only()})</span></h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_round_time()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_round_time_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_finals_time()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_finals_time_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_extension_policy()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_extension_policy_desc()}</dd></div>
    </dl>
  </div>
  <div class="rounded-lg border border-ash-700 bg-dusk-900/40 p-4 sm:col-span-2">
    <h4 class="text-sm font-semibold text-bone-100 mb-2">{m.og_cfg_other_settings()}</h4>
    <dl class="space-y-1.5 text-sm">
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_max_rounds()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_max_rounds_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_league()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_league_desc()}</dd></div>
      <div><dt class="text-ash-300 inline font-medium">{m.og_cfg_table_rooms()}</dt> <dd class="text-ash-400 inline">— {m.og_cfg_table_rooms_desc()}</dd></div>
    </dl>
  </div>
</div>

{@html renderGuideSection(m.og_co_organizers())}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">
    Open Registration
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_registration_tips())}

<ExampleBox>
  <div class="flex gap-3 items-center">
    <button class="px-4 py-2 text-sm font-medium btn-amber rounded-lg">
      Start Check-in
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded-lg">
      Back to Planning
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_checkin_back())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded-lg flex items-center gap-1.5">
        <QrCode class="w-4 h-4" />
        Show Check-in QR Code
      </button>
    </div>
    <div class="flex gap-2">
      <button class="px-3 py-1.5 text-sm btn-emerald rounded">Check All In</button>
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded">Reset Check-In</button>
    </div>
    <div class="bg-dusk-950 border border-ash-800 rounded-lg p-3">
      <div class="flex justify-between items-center text-sm">
        <span class="text-ash-300">Alice</span>
        <div class="flex gap-2">
          <button class="px-2 py-1 text-xs btn-emerald rounded">Check In</button>
          <button class="px-2 py-1 text-xs text-ash-400 border border-ash-700 rounded">Check Out</button>
        </div>
      </div>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_checkin_methods())}

<ExampleBox>
  <div class="pt-2 border-t border-ash-800">
    <button class="px-3 py-1.5 text-sm text-ash-500">
      Reopen Registration
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_deck_management())}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">
    Start Round 1
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_round_start_details())}

<ExampleBox>
  <div class="bg-ash-900/50 rounded-lg p-4 max-w-sm">
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-bone-100">Table 1</h3>
      <span class="text-xs px-2 py-0.5 rounded badge-amber">Playing</span>
    </div>
    <div class="divide-y divide-ash-800">
      {#each ["Alice", "Bob", "Charlie", "Diana"] as name}
        <div class="py-1.5 flex items-center justify-between text-sm">
          <span class="text-ash-300">{name}</span>
          <div class="flex items-center gap-2">
            <span class="text-ash-400 text-xs">VP:</span>
            <select class="bg-ash-800 text-bone-100 text-xs rounded px-1.5 py-0.5 border border-ash-700" tabindex="-1">
              <option>0</option>
              <option>0.5</option>
              <option>1</option>
              <option>1.5</option>
              <option>2</option>
              <option>2.5</option>
              <option>3</option>
            </select>
            <span class="text-ash-500 text-xs">0GW 0TP</span>
          </div>
        </div>
      {/each}
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_scoring_details())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <button class="px-3 py-1.5 text-sm btn-amber rounded flex items-center gap-1">
        <ShieldCheck class="w-3.5 h-3.5" />
        Override
      </button>
      <button class="px-3 py-1.5 text-sm text-ash-400 border border-ash-700 rounded">
        Remove override
      </button>
    </div>
    <textarea
      class="w-full px-3 py-2 text-sm bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500"
      placeholder="Judge comment (required for override)"
      rows="2"
      tabindex="-1"
    ></textarea>
    <button class="px-3 py-1.5 text-sm btn-amber rounded">
      Override &rarr; Finished
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_override_remove())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <button class="px-2 py-1 text-xs text-amber-400 border border-amber-800 rounded-lg flex items-center gap-1">
      <Gavel class="w-3 h-3" />
      Call Judge
    </button>
    <div class="banner-amber border rounded-lg p-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Gavel class="w-5 h-5 text-amber-400 shrink-0" />
        <div>
          <span class="text-sm font-medium text-bone-100">Judge Call!</span>
          <span class="text-sm text-ash-300 ml-1">Table 3 &mdash; Alice</span>
        </div>
      </div>
      <button class="text-ash-400 p-1">
        <X class="w-4 h-4" />
      </button>
    </div>
    <div class="banner-amber border rounded-lg p-3 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <Gavel class="w-5 h-5 text-amber-400 shrink-0" />
        <div>
          <span class="text-sm font-medium text-bone-100">Judge Call!</span>
          <span class="text-sm text-ash-300 ml-1">Table 7 &mdash; Bob</span>
        </div>
      </div>
      <button class="text-ash-400 p-1">
        <X class="w-4 h-4" />
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_finishing_round())}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium btn-amber rounded-lg">
    End Round
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_between_rounds())}

<ExampleBox>
  <button class="px-4 py-2 text-sm font-medium text-crimson-400 border border-crimson-800 rounded-lg">
    Cancel Round
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_timer())}

<ExampleBox>
  <div class="space-y-3 max-w-xs">
    <div class="flex gap-4 justify-center">
      <div class="text-center">
        <span class="text-2xl font-mono text-emerald-400">1:23:45</span>
        <p class="text-xs text-ash-500 mt-1">Time remaining</p>
      </div>
      <div class="text-center">
        <span class="text-2xl font-mono text-amber-400">4:30</span>
        <p class="text-xs text-ash-500 mt-1">&lt; 5 minutes</p>
      </div>
      <div class="text-center">
        <span class="text-2xl font-mono text-red-400">0:00</span>
        <p class="text-xs text-ash-500 mt-1">Expired</p>
      </div>
    </div>
    <div class="flex gap-2 justify-center">
      <button class="px-3 py-1.5 text-sm btn-emerald rounded flex items-center gap-1">
        <Play class="w-3.5 h-3.5" />
        Start
      </button>
      <button class="px-3 py-1.5 text-sm btn-amber rounded flex items-center gap-1">
        <Pause class="w-3.5 h-3.5" />
        Pause
      </button>
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded flex items-center gap-1">
        <RotateCcw class="w-3.5 h-3.5" />
        Reset
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_timer_controls())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-1">
      <button class="px-2 py-1 text-xs btn-emerald rounded">+1min</button>
      <button class="px-2 py-1 text-xs btn-emerald rounded">+2min</button>
      <button class="px-2 py-1 text-xs btn-emerald rounded">+3min</button>
      <button class="px-2 py-1 text-xs btn-emerald rounded">+5min</button>
      <span class="text-xs text-ash-400 self-center ml-1">0/10 min extra</span>
    </div>
    <div class="flex gap-2 items-center">
      <button class="px-3 py-1.5 text-sm btn-amber rounded flex items-center gap-1">
        <PauseCircle class="w-3.5 h-3.5" />
        Clock Stop
      </button>
      <button class="px-3 py-1.5 text-sm btn-emerald rounded flex items-center gap-1">
        <PlayCircle class="w-3.5 h-3.5" />
        Resume Clock
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_timer_extensions())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <span class="text-ash-300 text-sm">Alice</span>
      <span class="text-xs px-2 py-0.5 rounded badge-amber">Pending</span>
      <span class="text-ash-300 text-sm ml-3">Bob</span>
      <span class="text-xs px-2 py-0.5 rounded badge-emerald">Paid</span>
    </div>
    <button class="px-3 py-1.5 text-sm btn-emerald rounded">Mark All Paid</button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_payment_tip())}

<ExampleBox>
  <div class="flex gap-2 items-center">
    <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">
      Start Finals
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 rounded-lg">
      <Dice3 class="w-4 h-4 inline mr-1" />
      Random Toss
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-300 bg-ash-800 rounded-lg">
      Edit toss
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_finals_toss())}

{@html renderGuideSection(m.og_winner_deck_missing())}

<ExampleBox>
  <div class="banner-amber border rounded-lg p-3 text-sm max-w-sm">
    Winner's decklist is missing. Please remind Alice to upload their deck.
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_finish_no_finals())}

<ExampleBox>
  <div class="pt-2 border-t border-ash-800 flex flex-wrap gap-2">
    <button class="px-3 py-1.5 text-sm text-ash-500">
      Finish Tournament
    </button>
    <button class="px-3 py-1.5 text-sm text-ash-500">
      Reopen Tournament
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_reopen())}

<ExampleBox>
  <div class="flex gap-2 items-center">
    <button class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 rounded-lg flex items-center gap-2">
      <Share2 class="w-4 h-4" />
      Share Image
    </button>
    <button class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 rounded-lg flex items-center gap-2">
      <ClipboardCopy class="w-4 h-4" />
      Copy Text
    </button>
    <span class="px-3 py-1.5 text-sm bg-ash-800 text-ash-200 rounded-lg flex items-center gap-2">
      <Download class="w-4 h-4" />
      Download Report (JSON)
    </span>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_sharing_details())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="flex gap-2 items-center">
      <select class="bg-ash-800 text-bone-100 text-sm rounded px-2 py-1.5 border border-ash-700" tabindex="-1">
        <option>All Players</option>
        <option>Non-Finalists</option>
        <option>Game Winners</option>
      </select>
      <input type="text" placeholder="Prize name" class="flex-1 px-2 py-1.5 text-sm bg-dusk-900 border border-ash-700 rounded text-bone-100 placeholder-ash-500" tabindex="-1" />
    </div>
    <div class="flex gap-2">
      <button class="px-3 py-1.5 text-sm btn-emerald rounded flex items-center gap-1">
        <Dices class="w-3.5 h-3.5" />
        Draw
      </button>
      <button class="px-3 py-1.5 text-sm text-ash-300 border border-ash-600 rounded flex items-center gap-1">
        <Undo2 class="w-3.5 h-3.5" />
        Undo
      </button>
      <button class="px-3 py-1.5 text-sm text-crimson-400 border border-crimson-800 rounded flex items-center gap-1">
        <Trash2 class="w-3.5 h-3.5" />
        Clear all
      </button>
    </div>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_offline())}

<ExampleBox>
  <button class="px-4 py-2 text-sm text-amber-300 border border-amber-700 rounded-lg flex items-center gap-2">
    <WifiOff class="w-4 h-4" />
    Go Offline
  </button>
</ExampleBox>

{@html renderGuideSection(m.og_offline_prepare())}

<ExampleBox>
  <div class="space-y-3 max-w-sm">
    <div class="bg-amber-900/30 border border-amber-800/50 rounded-lg p-3 flex items-center gap-2">
      <WifiOff class="w-5 h-5 text-amber-400 shrink-0" />
      <span class="text-amber-200 font-medium text-sm">OFFLINE MODE — Changes are stored locally</span>
    </div>
    <button class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg flex items-center gap-2">
      <Wifi class="w-4 h-4" />
      Go Back Online
    </button>
  </div>
</ExampleBox>

{@html renderGuideSection(m.og_force_takeover())}

<div class="not-prose my-6 space-y-1">
  {#each faqs as faq, i}
    <div class="border border-ash-700 rounded-lg overflow-hidden">
      <button
        class="w-full px-4 py-3 flex items-center gap-2 text-left text-sm font-medium text-bone-100 hover:bg-dusk-800/50 transition-colors"
        onclick={() => openFaq = openFaq === i ? null : i}
      >
        {#if openFaq === i}
          <ChevronDown class="w-4 h-4 text-ash-400 shrink-0" />
        {:else}
          <ChevronRight class="w-4 h-4 text-ash-400 shrink-0" />
        {/if}
        {faq.q}
      </button>
      {#if openFaq === i}
        <div class="px-4 pb-3 text-sm text-ash-300 doc-prose prose max-w-none">
          {@html renderGuideSection(faq.a)}
        </div>
      {/if}
    </div>
  {/each}
</div>
