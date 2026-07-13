<script lang="ts">
  import type { Tournament, TournamentState, DeckObject } from "$lib/types";
  import type { TournamentEventType } from "$lib/engine";
  import type { Component } from "svelte";
  import Button from "$lib/components/Button.svelte";
  import ActionMenu from "$lib/components/ActionMenu.svelte";
  import QrCheckinDisplay from "$lib/components/QrCheckinDisplay.svelte";
  import FinishedResults from "./FinishedResults.svelte";
  import FinishConfirmModal from "./FinishConfirmModal.svelte";
  import { QrCode, Undo2, CheckCheck, Banknote, RotateCcw, TriangleAlert } from "@lucide/svelte";
  import { translateTournamentState, seatDisplay, top5HasTies as top5HasTiesFn, type StandingEntry, type PlayerInfoMap } from "$lib/tournament-utils";
  import * as m from '$lib/paraglide/messages.js';

  type MenuItem = { label: string; icon?: Component<any>; onclick: () => void; disabled?: boolean };

  let {
    tournament,
    standings,
    playerInfo,
    decksByUser,
    actionLoading,
    doAction,
    syncVeknItem,
    archonImportItem,
    csvImportItem,
    onImportArchon,
  }: {
    tournament: Tournament;
    standings: StandingEntry[];
    playerInfo: PlayerInfoMap;
    decksByUser: Record<string, DeckObject[]>;
    actionLoading: boolean;
    doAction: (action: TournamentEventType, body?: any) => Promise<void>;
    syncVeknItem: MenuItem | null;
    archonImportItem: MenuItem;
    csvImportItem: MenuItem;
    onImportArchon: () => void;
  } = $props();

  let showQrCode = $state(false);
  let showFinishConfirm = $state(false);

  const isFinals = $derived(tournament?.finals != null && (tournament?.state === "Playing" || tournament?.state === "Finished"));

  // Action bar derived values
  const registeredCount = $derived(tournament?.players?.length ?? 0);
  const checkedInCount = $derived(tournament?.players?.filter(p => p.state === "Checked-in").length ?? 0);
  const uncheckedCount = $derived(tournament?.players?.filter(p => p.state === "Registered").length ?? 0);
  const finishedPlayerCount = $derived(tournament?.players?.filter(p => p.state === "Finished").length ?? 0);
  const hasRounds = $derived((tournament?.rounds?.length ?? 0) > 0);
  // QR self-check-in is in-person only — online players can't scan a venue code. checkin_code is always set server-side, so gate on !online.
  const qrCheckin = $derived(!tournament?.online && !!tournament?.checkin_code);
  const hasFinalsCandidate = $derived(standings.length >= 5 && (tournament?.rounds?.length ?? 0) >= 2);
  const finalsReady = $derived(hasFinalsCandidate && !top5HasTiesFn(standings));
  // Find the single in-progress round (for action bar when not parallel)
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
  // Round-1 no-show notice (standard tournaments): who gets recorded as a
  // no-show when the round starts. Non-blocking — drops are reinstatable
  // (CheckIn between rounds, SeatPlayer mid-round), so it informs, no confirm.
  const prospectiveNoShows = $derived.by(() => {
    if (tournament?.state !== "Waiting" || tournament?.open_rounds) return [];
    const priorRealRounds = tournament?.rounds?.filter(r => r.some(t => t.state !== "Cancelled")).length ?? 0;
    if (priorRealRounds > 0) return [];
    return (tournament?.players ?? [])
      .filter(p => p.state === "Registered" && p.user_uid)
      .map(p => seatDisplay(p.user_uid!, playerInfo, tournament.online));
  });
</script>

<!-- Action Bar -->
<div class="border-b border-line px-3 sm:px-6 py-3 space-y-3">
  <!-- Step indicator -->
  <div class="flex items-center gap-1 sm:gap-2 text-xs overflow-x-auto">
    {#each ["Planned", "Registration", "Waiting", "Playing", "Finished"] as step, i}
      {@const states = ["Planned", "Registration", "Waiting", "Playing", "Finished"]}
      {@const currentIdx = states.indexOf(tournament.state)}
      {@const isDone = i < currentIdx}
      {@const isCurrent = i === currentIdx}
      {#if i > 0}<span class="text-ink-faint">—</span>{/if}
      <span class="whitespace-nowrap {isDone ? 'text-info' : isCurrent ? 'text-link font-medium' : 'text-ink-faint'}">
        <span class="inline-block w-2 h-2 rounded-full mr-1 align-middle {isDone ? 'bg-info' : isCurrent ? 'bg-accent' : 'bg-surface-active'}"></span>
        <span class="hidden sm:inline">{translateTournamentState(step as TournamentState)}</span>
      </span>
    {/each}
  </div>

  <!-- Guidance message -->
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

  <!-- Actions: ONE primary CTA per state; secondaries collapse into a More overflow -->
  <div class="flex flex-wrap items-center gap-2">
    {#if tournament.state === "Planned"}
      <Button variant="primary" size="lg" disabled={actionLoading} onclick={() => doAction("OpenRegistration")}>{m.overview_open_registration()}</Button>
      <ActionMenu label={m.common_more()} items={[...(syncVeknItem ? [syncVeknItem] : []), archonImportItem]} />

    {:else if tournament.state === "Registration"}
      <Button variant="primary" size="lg" disabled={actionLoading} onclick={() => doAction("CloseRegistration")}>{m.overview_close_registration()}</Button>
      <ActionMenu label={m.common_more()} items={[
        ...(qrCheckin ? [{ label: showQrCode ? m.checkin_qr_hide_code() : m.checkin_qr_show_code(), icon: QrCode, onclick: () => (showQrCode = !showQrCode) }] : []),
        csvImportItem,
        { label: m.overview_back_to_planning(), icon: Undo2, onclick: () => doAction("CancelRegistration"), disabled: actionLoading },
        ...(syncVeknItem ? [syncVeknItem] : []),
        archonImportItem,
      ]} />

    {:else if tournament.state === "Waiting"}
      {#if finalsReady}
        <Button variant="primary" size="lg" disabled={actionLoading} onclick={() => doAction("StartFinals")}>{m.overview_start_finals()}</Button>
        <Button variant="secondary" size="md" disabled={actionLoading || checkedInCount < 4} onclick={() => doAction("StartRound")}>{m.overview_start_round({ n: String((tournament.rounds?.length ?? 0) + 1) })}</Button>
      {:else}
        <Button variant="primary" size="lg" disabled={actionLoading || checkedInCount < 4} onclick={() => doAction("StartRound")}>{m.overview_start_round({ n: String((tournament.rounds?.length ?? 0) + 1) })}</Button>
        {#if hasFinalsCandidate}
          <Button variant="secondary" size="md" disabled={actionLoading || !finalsReady} onclick={() => doAction("StartFinals")}>{m.overview_start_finals()}</Button>
        {/if}
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
        ...(qrCheckin && hasRounds ? [{ label: showQrCode ? m.checkin_qr_hide_code() : m.checkin_qr_show_code(), icon: QrCode, onclick: () => (showQrCode = !showQrCode) }] : []),
        { label: m.overview_reopen_registration(), icon: Undo2, onclick: () => doAction("ReopenRegistration"), disabled: actionLoading },
        ...(syncVeknItem ? [syncVeknItem] : []),
        archonImportItem,
      ]} />

    {:else if tournament.state === "Playing"}
      {#if isFinals}
        <Button variant="primary" size="lg" disabled={actionLoading || !finalsTableFinished} onclick={() => doAction("FinishFinals")}>{m.finals_finish()}</Button>
        <!-- Revert finals seating (e.g. a finalist no-showed): back to Waiting to drop them and re-seat. -->
        <Button variant="ghost" size="md" disabled={actionLoading} onclick={() => doAction("CancelFinals")}><Undo2 class="w-4 h-4" aria-hidden="true" />{m.finals_cancel()}</Button>
      {:else if !hasParallelRounds}
        <Button variant="primary" size="lg" disabled={actionLoading || !allTablesFinished} onclick={() => doAction("FinishRound", { round: activeRoundIdx })}>{m.rounds_end_round()}</Button>
        {#if tournament.online}
          {@const canStartNext = (checkedInCount + playingCount) >= 4}
          <Button variant="secondary" size="md" disabled={actionLoading || !canStartNext} onclick={() => doAction("StartRound")}>{m.overview_start_round({ n: String((tournament.rounds?.length ?? 0) + 1) })}</Button>
        {/if}
      {:else if tournament.online}
        {@const canStartNext = (checkedInCount + playingCount) >= 4}
        <Button variant="primary" size="lg" disabled={actionLoading || !canStartNext} onclick={() => doAction("StartRound")}>{m.overview_start_round({ n: String((tournament.rounds?.length ?? 0) + 1) })}</Button>
      {/if}
      <ActionMenu label={m.common_more()} items={[...(syncVeknItem ? [syncVeknItem] : []), archonImportItem]} />
    {/if}
  </div>

  <!-- Finished results: winner + share/export + reopen (re-homed from the former Overview tab).
       Archon import only when there are no standings (an empty finished shell to migrate into). -->
  {#if tournament.state === "Finished"}
    <FinishedResults
      {tournament}
      {playerInfo}
      {standings}
      winnerHasDeck={!!(tournament.winner && decksByUser[tournament.winner]?.length)}
      {doAction}
      {actionLoading}
      {onImportArchon}
    />
  {/if}

  <!-- Check-in hints (Waiting state) -->
  {#if tournament.state === "Waiting"}
    {#if checkedInCount < 4}
      <p class="text-sm text-ink-faint">{m.overview_start_round_hint({ count: String(checkedInCount) })}</p>
    {/if}
    {#if prospectiveNoShows.length > 0}
      <p class="text-sm text-warn">{m.action_bar_noshow_notice({ names: prospectiveNoShows.join(", ") })}</p>
    {/if}
    {#if [6, 7, 11].includes(checkedInCount)}
      <p class="text-sm text-info">{m.overview_stagger_info({ count: String(checkedInCount) })}</p>
    {/if}
    {#if hasFinalsCandidate && hasUnequalRounds}
      <p class="text-sm text-warn">{m.overview_stagger_finals_warning()}</p>
    {/if}
  {/if}

  <!-- Danger action (Waiting state): destructive, set apart with its own hue + icon -->
  {#if tournament.state === "Waiting"}
    <div class="pt-2 border-t border-line">
      <Button variant="danger" size="md" disabled={actionLoading} onclick={() => (showFinishConfirm = true)}>
        <TriangleAlert class="w-4 h-4" aria-hidden="true" />
        {m.overview_finish_tournament()}
      </Button>
    </div>
  {/if}

  {#if showFinishConfirm}
    <FinishConfirmModal
      {tournament}
      {standings}
      {playerInfo}
      {decksByUser}
      {actionLoading}
      onConfirm={async () => { await doAction("FinishTournament"); showFinishConfirm = false; }}
      onClose={() => (showFinishConfirm = false)}
    />
  {/if}

  <!-- QR Check-in display -->
  {#if showQrCode && (tournament.state === "Registration" || tournament.state === "Waiting") && qrCheckin && tournament.checkin_code}
    <div class="pt-3 border-t border-line">
      <QrCheckinDisplay code={tournament.checkin_code} tournamentUid={tournament.uid} tournamentName={tournament.name} />
    </div>
  {/if}
</div>
