<script lang="ts">
  import type { Tournament, TournamentState, DeckObject } from "$lib/types";
  import type { TournamentEventType } from "$lib/engine";
  import Button from "$lib/components/Button.svelte";
  import ActionMenu from "$lib/components/ActionMenu.svelte";
  import QrCheckinDisplay from "$lib/components/QrCheckinDisplay.svelte";
  import FinishedResults from "./FinishedResults.svelte";
  import InlineNotice from "$lib/components/InlineNotice.svelte";
  import { Undo2, CheckCheck, Banknote, RotateCcw } from "@lucide/svelte";
  import { translateTournamentState, seatDisplay, top5HasTies as top5HasTiesFn, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';


  let {
    tournament,
    standings,
    playerInfo,
    decksByUser,
    actionLoading,
    doAction,
    onImportArchon,
    onAddBanner,
  }: {
    tournament: Tournament;
    standings: StandingEntry[];
    playerInfo: PlayerInfoMap;
    decksByUser: Record<string, DeckObject[]>;
    actionLoading: boolean;
    doAction: (action: TournamentEventType, body?: any) => Promise<string | null>;
    onImportArchon: () => void;
    onAddBanner: () => void;
  } = $props();

  let showQrCode = $state(false);

  const isFinals = $derived(tournament?.finals != null && (tournament?.state === "Playing" || tournament?.state === "Finished"));

  const registeredCount = $derived(tournament?.players?.length ?? 0);
  const checkedInCount = $derived(tournament?.players?.filter(p => p.state === "Checked-in").length ?? 0);
  const uncheckedCount = $derived(tournament?.players?.filter(p => p.state === "Registered").length ?? 0);
  const finishedPlayerCount = $derived(tournament?.players?.filter(p => p.state === "Finished").length ?? 0);
  const hasRounds = $derived((tournament?.rounds?.length ?? 0) > 0);
  // QR self-check-in is in-person only — online players can't scan a venue code. checkin_code is always set server-side, so gate on !online.
  const qrCheckin = $derived(!tournament?.online && !!tournament?.checkin_code);
  const hasFinalsCandidate = $derived(standings.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
  const finalsReady = $derived(hasFinalsCandidate && !top5HasTiesFn(standings));
  const activeRoundIdx = $derived.by(() => {
    if (!tournament?.rounds?.length) return -1;
    const idx = tournament.rounds.findIndex(r => r.some(t => t.state !== "Finished"));
    return idx >= 0 ? idx : tournament.rounds.length - 1;
  });
  const allTablesFinished = $derived.by(() => {
    if (!tournament?.rounds?.length || activeRoundIdx < 0) return false;
    const round = tournament.rounds[activeRoundIdx]!;
    return round.length > 0 && round.every(t => t.state === "Finished");
  });
  const finalsTableFinished = $derived(tournament?.finals?.state === "Finished");
  // Detect unequal rounds played (stagger sit-outs). Open rounds (per-player cap) expect
  // unequal counts by design, so the stagger-finals warning would only be noise there.
  const hasUnequalRounds = $derived.by(() => {
    if ((tournament?.max_rounds ?? 0) > 0) return false;
    if (!tournament?.rounds?.length || !tournament?.players) return false;
    const counts = new Map<string, number>();
    const active = new Set(tournament.players.filter(p => p.state !== "Finished" && p.state !== "Disqualified").map(p => p.user_uid));
    for (const round of tournament.rounds) {
      for (const table of round) {
        for (const seat of table.seating) {
          if (active.has(seat.player_uid)) {
            counts.set(seat.player_uid, (counts.get(seat.player_uid) ?? 0) + 1);
          }
        }
      }
    }
    if (counts.size === 0) return false;
    const vals = [...counts.values()];
    return Math.min(...vals) < Math.max(...vals);
  });
  const tablesFinishedCount = $derived.by(() => {
    if (!tournament?.rounds?.length || activeRoundIdx < 0) return { done: 0, total: 0 };
    const round = tournament.rounds[activeRoundIdx]!;
    return { done: round.filter(t => t.state === "Finished").length, total: round.length };
  });
  const inProgressRoundCount = $derived(
    tournament?.rounds?.filter(r => r.some(t => t.state !== "Finished")).length ?? 0
  );
  const hasParallelRounds = $derived(inProgressRoundCount > 1);
  const playingCount = $derived(tournament?.players?.filter(p => p.state === "Playing").length ?? 0);
  // Round-1 no-show notice: who gets recorded as a no-show when the round
  // starts. Non-blocking — drops are reinstatable (CheckIn, SeatPlayer), so it
  // informs, no confirm.
  const prospectiveNoShows = $derived.by(() => {
    if (tournament?.state !== "Waiting" || tournament?.open_rounds) return [];
    const priorRealRounds = tournament?.rounds?.filter(r => r.some(t => t.state !== "Cancelled")).length ?? 0;
    if (priorRealRounds > 0) return [];
    return (tournament?.players ?? [])
      .filter(p => p.state === "Registered" && p.user_uid)
      .map(p => seatDisplay(p.user_uid!, playerInfo, tournament.online));
  });

  // Present but not seated in any live round — a late arrival or a rotation
  // sit-out; nothing in the data tells them apart, and both leave the organizer
  // the same two choices, so one notice serves both.
  const unseatedCheckedIn = $derived.by(() => {
    if (tournament?.state !== "Playing") return [];
    const seated = new Set<string>();
    for (const round of tournament.rounds ?? []) {
      for (const t of round) {
        if (t.state === "Finished") continue;
        for (const s of t.seating) seated.add(s.player_uid);
      }
    }
    return (tournament.players ?? [])
      .filter(p => p.state === "Checked-in" && p.user_uid && !seated.has(p.user_uid))
      .map(p => seatDisplay(p.user_uid!, playerInfo, tournament.online));
  });

  const nextRoundLabel = $derived(m.overview_start_round({ n: String((tournament?.rounds?.length ?? 0) + 1) }));
  // Online events start the next round while the current one is still running,
  // so seats come from both pools.
  const canStartNextOnline = $derived((checkedInCount + playingCount) >= 4);

  // The single state-appropriate CTA, as data — rendered twice (in the bar, and
  // in the sticky strip once the bar scrolls away), so it must not be markup.
  type Primary = { label: string; onclick: () => void; disabled?: boolean };
  const primary = $derived.by((): Primary | null => {
    switch (tournament.state) {
      case "Planned":
        return { label: m.overview_open_registration(), onclick: () => doAction("OpenRegistration") };
      case "Registration":
        return { label: m.overview_close_registration(), onclick: () => doAction("CloseRegistration") };
      case "Waiting":
        return finalsReady
          ? { label: m.overview_start_finals(), onclick: () => doAction("StartFinals") }
          : { label: nextRoundLabel, onclick: () => doAction("StartRound"), disabled: checkedInCount < 4 };
      case "Playing":
        if (isFinals) return { label: m.finals_finish(), onclick: () => doAction("FinishFinals"), disabled: !finalsTableFinished };
        if (!hasParallelRounds) return { label: m.rounds_end_round(), onclick: () => doAction("FinishRound", { round: activeRoundIdx }), disabled: !allTablesFinished };
        return tournament.online ? { label: nextRoundLabel, onclick: () => doAction("StartRound"), disabled: !canStartNextOnline } : null;
      default:
        return null;
    }
  });

  // Compact progress for the sticky strip: digits only, so it needs no
  // translation and stays legible at any width; the full sentence rides along
  // as the accessible label.
  const stickyProgress = $derived(
    tournament.state === "Playing" && !isFinals && !hasParallelRounds && tablesFinishedCount.total > 0
      ? `${tablesFinishedCount.done}/${tablesFinishedCount.total}`
      : null
  );
  const stickyLabel = $derived(
    stickyProgress
      ? m.action_bar_playing_round({ n: String(activeRoundIdx + 1), done: String(tablesFinishedCount.done), total: String(tablesFinishedCount.total) })
      : translateTournamentState(tournament.state)
  );

  // The sticky strip stands in for the action bar only while the bar is off
  // screen — the organizer works in the tables far below it.
  let barEl = $state<HTMLElement | null>(null);
  let barOnScreen = $state(true);
  $effect(() => {
    const el = barEl;
    if (!el) return;
    const io = new IntersectionObserver((entries) => (barOnScreen = entries[entries.length - 1]?.isIntersecting ?? true));
    io.observe(el);
    return () => io.disconnect();
  });
</script>

<!-- Sits above the tab bar, not inside tab content — it's the same panel
     whichever tab is open. -->
<div bind:this={barEl} class="border-b border-line px-3 sm:px-6 py-3 space-y-3">
  <!-- Gone once Finished: the guidance line below already answers "how far
       along" with "Tournament complete." -->
  {#if tournament.state !== "Finished"}
  <div class="flex items-center gap-1 sm:gap-2 text-xs overflow-x-auto">
    {#each ["Planned", "Registration", "Waiting", "Playing", "Finished"] as step, i}
      {@const states = ["Planned", "Registration", "Waiting", "Playing", "Finished"]}
      {@const currentIdx = states.indexOf(tournament.state)}
      {@const isDone = i < currentIdx}
      {@const isCurrent = i === currentIdx}
      {#if i > 0}<span class="text-ink-faint" aria-hidden="true">—</span>{/if}
      <!-- Phones: only the current step keeps its visible label; the rest stay
           sr-only (not display:none) so the lifecycle reads for screen readers -->
      <span class="whitespace-nowrap {isDone ? 'text-info' : isCurrent ? 'text-link font-medium' : 'text-ink-faint'}" aria-current={isCurrent ? "step" : undefined}>
        <span class="inline-block w-2 h-2 rounded-full mr-1 align-middle {isDone ? 'bg-info' : isCurrent ? 'bg-accent' : 'bg-surface-active'}" aria-hidden="true"></span>
        <span class={isCurrent ? "inline" : "sr-only sm:not-sr-only"}>{translateTournamentState(step as TournamentState)}</span>
      </span>
    {/each}
  </div>
  {/if}

  <p class="text-sm text-ink-muted">
    {#if tournament.state === "Planned"}
      {m.action_bar_planned()}
    {:else if tournament.state === "Registration"}
      {m.action_bar_registration({ count: String(registeredCount) })}
    {:else if tournament.state === "Waiting"}
      {#if hasFinalsCandidate && top5HasTiesFn(standings)}
        {m.action_bar_waiting_toss_needed({ n: String(tournament.rounds!.length) })}
      {:else if hasFinalsCandidate}
        {m.action_bar_waiting_finals_ready({ n: String(tournament.rounds!.length) })}
      {:else if hasRounds}
        {m.action_bar_waiting_after_round({ n: String(tournament.rounds!.length) })}
      {:else}
        {m.action_bar_waiting_initial({ checked: String(checkedInCount), total: String(registeredCount - finishedPlayerCount) })}
      {/if}
    {:else if tournament.state === "Playing"}
      {#if isFinals}
        {m.action_bar_playing_finals()}
      {:else if hasParallelRounds}
        {m.action_bar_playing_parallel({ count: String(inProgressRoundCount) })}
      {:else}
        {m.action_bar_playing_round({ n: String(activeRoundIdx + 1), done: String(tablesFinishedCount.done), total: String(tablesFinishedCount.total) })}
      {/if}
    {:else if tournament.state === "Finished"}
      {m.action_bar_finished()}
    {/if}
  </p>

  <div class="flex flex-wrap items-center gap-2">
    {#if primary}
      <Button variant="primary" size="lg" loading={actionLoading} disabled={primary.disabled} onclick={primary.onclick}>{primary.label}</Button>
    {/if}

    {#if tournament.state === "Registration"}
      <ActionMenu label={m.common_more()} items={[
        { label: m.overview_back_to_planning(), icon: Undo2, onclick: () => doAction("CancelRegistration"), disabled: actionLoading },
      ]} />

    {:else if tournament.state === "Waiting"}
      <!-- Whichever of start-round / start-finals the primary didn't take -->
      {#if finalsReady}
        <Button variant="secondary" size="md" loading={actionLoading} disabled={checkedInCount < 4} onclick={() => doAction("StartRound")}>{nextRoundLabel}</Button>
      {:else if hasFinalsCandidate}
        <Button variant="secondary" size="md" loading={actionLoading} disabled={!finalsReady} onclick={() => doAction("StartFinals")}>{m.overview_start_finals()}</Button>
      {/if}
      <!-- In-person first check-in: surface the QR directly (players self-check-in by scanning) instead of burying it in More -->
      {#if qrCheckin && !hasRounds}
        <Button variant="secondary" size="md" disabled={actionLoading} onclick={() => (showQrCode = !showQrCode)}>{showQrCode ? m.checkin_qr_hide_code() : m.checkin_qr_show_code()}</Button>
      {/if}
      <!-- Online between rounds: surface Reset Check-in (out of More) — online players
           silently drop out far more than IRL, and stale check-ins corrupt seating. -->
      {#if tournament.online && hasRounds}
        <Button variant="secondary" size="md" disabled={actionLoading} onclick={() => doAction("ResetCheckIn")}><RotateCcw class="w-4 h-4" aria-hidden="true" />{m.overview_reset_checkin()}</Button>
      {/if}
      <!-- Check All In: visible while registrants remain unchecked (the door-desk
           moment); pointless once everyone is in, so it appears nowhere else. -->
      {#if uncheckedCount > 0}
        <Button variant="secondary" size="md" disabled={actionLoading} onclick={() => doAction("CheckInAll")}><CheckCheck class="w-4 h-4" aria-hidden="true" />{m.overview_check_all_in()}</Button>
      {/if}
      <ActionMenu label={m.common_more()} items={[
        { label: m.payment_mark_all_paid(), icon: Banknote, onclick: () => doAction("MarkAllPaid"), disabled: actionLoading },
        ...(hasRounds && !tournament.online ? [{ label: m.overview_reset_checkin(), icon: RotateCcw, onclick: () => doAction("ResetCheckIn"), disabled: actionLoading }] : []),
        { label: m.overview_reopen_registration(), icon: Undo2, onclick: () => doAction("ReopenRegistration"), disabled: actionLoading },
      ]} />

    {:else if tournament.state === "Playing"}
      {#if isFinals}
        <!-- Revert finals seating (e.g. a finalist no-showed): back to Waiting to drop them and re-seat. -->
        <Button variant="ghost" size="md" disabled={actionLoading} onclick={() => doAction("CancelFinals")}><Undo2 class="w-4 h-4" aria-hidden="true" />{m.finals_cancel()}</Button>
      {:else if !hasParallelRounds && tournament.online}
        <Button variant="secondary" size="md" loading={actionLoading} disabled={!canStartNextOnline} onclick={() => doAction("StartRound")}>{nextRoundLabel}</Button>
      {/if}
    {/if}
  </div>

  <!-- Before the event is announced, the banner IS the share card (og.py renders
       it), so it earns a nudge here — and only here, until one exists. -->
  {#if !tournament.banner_path && (tournament.state === "Planned" || tournament.state === "Registration")}
    <InlineNotice>
      {m.banner_nudge()}
      <button type="button" onclick={onAddBanner} class="text-link hover:text-link-soft underline ml-1">
        {m.tournament_banner_add()}
      </button>
    </InlineNotice>
  {/if}

  {#if tournament.state === "Finished"}
    <FinishedResults
      {tournament}
      {playerInfo}
      {standings}
      winnerHasDeck={!!(tournament.winner && decksByUser[tournament.winner]?.length)}
      {onImportArchon}
    />
  {/if}

  {#if tournament.state === "Waiting"}
    {#if checkedInCount < 4}
      <p class="text-sm text-ink-faint">{m.overview_start_round_hint({ count: String(checkedInCount) })}</p>
    {/if}
    {#if prospectiveNoShows.length > 0}
      <p class="text-sm text-warn">{m.action_bar_noshow_notice({ names: prospectiveNoShows.join(", ") })}</p>
    {/if}
    {#if [6, 7, 11].includes(checkedInCount)}
      <p class="text-sm text-info">
        {m.overview_stagger_info({ count: String(checkedInCount) })}
        <a href="/help/judges-guide#51-event-organization-unexpected-drop" class="text-link hover:text-link-soft underline">{m.overview_stagger_guide_link()}</a>
      </p>
    {/if}
    {#if hasFinalsCandidate && hasUnequalRounds}
      <p class="text-sm text-warn">{m.overview_stagger_finals_warning()}</p>
    {/if}
  {/if}

  <!-- Checking someone in mid-round leaves them present but unseated — state it,
       but the two options are the organizer's to weigh, so the copy carries no
       default. -->
  {#if tournament.state === "Playing" && unseatedCheckedIn.length > 0}
    <InlineNotice>{m.action_bar_unseated_notice({ names: unseatedCheckedIn.join(", ") })}</InlineNotice>
  {/if}

  {#if showQrCode && (tournament.state === "Registration" || tournament.state === "Waiting") && qrCheckin && tournament.checkin_code}
    <div class="pt-3 border-t border-line">
      <QrCheckinDisplay code={tournament.checkin_code} tournamentUid={tournament.uid} tournamentName={tournament.name} />
    </div>
  {/if}
</div>

<!-- Sits flush on the mobile nav (bottom-navbar, its total footprint) and
     clears the desktop rail (sm:left-rail), where it is itself the bottom-most
     element and absorbs the inset. -->
{#if primary && !barOnScreen}
  <div
    class="fixed left-0 right-0 bottom-navbar sm:bottom-0 sm:left-rail z-30 sm:pb-safe-b pr-safe-r border-t border-line bg-surface-card/95 backdrop-blur-sm print:hidden"
  >
    <div class="max-w-4xl mx-auto px-3 sm:px-6 py-2 flex items-center justify-between gap-3">
      <span class="text-sm text-ink-muted truncate" aria-hidden="true">
        {translateTournamentState(tournament.state)}{#if stickyProgress}<span class="text-ink-faint"> · {stickyProgress}</span>{/if}
      </span>
      <Button variant="primary" size="lg" class="shrink-0" loading={actionLoading} disabled={primary.disabled} onclick={primary.onclick} aria-label="{primary.label} — {stickyLabel}">
        {primary.label}
      </Button>
    </div>
  </div>
{/if}
