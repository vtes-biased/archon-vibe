<script lang="ts">
  import type { Tournament, Player, Sanction, DeckObject } from "$lib/types";
  import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
  import { seatDisplay as seatDisplayUtil, vpOptions, translatePlayerState, translateTableState, translateStandingsMode, roundsPlayed, getRatingPts, ratingContext } from "$lib/tournament-utils";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { formatScore } from "$lib/utils";
  import { previewScoresSync, tableLabel, type ValidationError, type TournamentEventType } from "$lib/engine";
  import { TriangleAlert, ChevronDown, ChevronRight, QrCode, Gavel, Ban, Trash2, ExternalLink, Users, Lock, ShieldCheck, Undo2 } from "@lucide/svelte";
  import SanctionIndicator from "$lib/components/SanctionIndicator.svelte";
  import SelfOrganizeDialog from "./SelfOrganizeDialog.svelte";
  import RankCell from "$lib/components/RankCell.svelte";
  import ScoreLegend from "$lib/components/ScoreLegend.svelte";
  import RankedBadge from "./RankedBadge.svelte";
  import CopyResultsButton from "./CopyResultsButton.svelte";
  import QrCheckinScanner from "$lib/components/QrCheckinScanner.svelte";
  import Button from '$lib/components/Button.svelte';
  import TimerDisplay from "./TimerDisplay.svelte";
  import VpInput from "$lib/components/VpInput.svelte";
  import PlayerDecksSection from "./PlayerDecksSection.svelte";
  import RaffleSection from "./RaffleSection.svelte";
  import { callJudge } from "$lib/api";
  import { isOnline } from "$lib/api";
  import { isUserCurrentlySanctioned } from "$lib/db";
  import * as m from '$lib/paraglide/messages.js';

  let {
    tournament,
    playerInfo,
    standings,
    playerStandings,
    cutoffScore,
    playerHasValidDeck,
    myDeckErrors,
    userUid,
    userVeknId,
    actionLoading,
    scoreSaving,
    scoreSavingSeat,
    doAction,
    dropPlayer,
    setVp,
    setFinalsVp,
    tournamentSanctions,
    decksByUser,
  }: {
    tournament: Tournament;
    playerInfo: PlayerInfoMap;
    standings: StandingEntry[];
    playerStandings: StandingEntry[];
    cutoffScore: { gw: number; vp: number; tp: number } | null;
    playerHasValidDeck: boolean;
    myDeckErrors?: ValidationError[] | null;
    userUid: string;
    userVeknId: string | null;
    actionLoading: boolean;
    scoreSaving: number | null;
    scoreSavingSeat: string | null;
    doAction: (action: TournamentEventType, body?: any, opts?: { silent?: boolean }) => Promise<string | null>;
    dropPlayer: (uid: string) => Promise<string | null>;
    setVp: (roundIndex: number, tableIndex: number, playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>, opts?: { silent?: boolean }) => Promise<string | null>;
    setFinalsVp: (playerUid: string, vp: number, seating: Array<{ player_uid: string; result: { vp: number } }>, opts?: { silent?: boolean }) => Promise<string | null>;
    tournamentSanctions: Sanction[];
    decksByUser?: Record<string, DeckObject[]>;
  } = $props();

  // Cheap page-level derivations replicated locally rather than threaded as props
  const isFinished = $derived(tournament.state === "Finished");
  const isFinals = $derived(tournament.finals != null && (tournament.state === "Playing" || tournament.state === "Finished"));
  const currentPlayerEntry = $derived(tournament.players?.find(p => p.user_uid === userUid) ?? null);

  let showRegisteredPlayers = $state(false);
  let showPreviousRounds = $state(false);
  let showQrScanner = $state(false);
  let judgeCallCooldown = $state(false);
  let userSuspended = $state(false);

  $effect(() => {
    if (userUid) {
      isUserCurrentlySanctioned(userUid).then(v => { userSuspended = v; });
    }
  });

  const myStanding = $derived(standings.find(s => s.user_uid === userUid));
  const showMyScore = $derived(
    !!myStanding &&
    (tournament.state === "Playing" || tournament.state === "Waiting") &&
    (tournament.rounds?.length ?? 0) > 0,
  );
  // Finished means played-out or walked-out; only a standings row tells them apart.
  const myStatusLabel = $derived.by(() => {
    const p = currentPlayerEntry;
    if (!p) return "";
    if (p.state !== "Finished") return translatePlayerState(p.state);
    const ended = tournament.finals !== null || tournament.state === "Finished";
    return ended && standings.some(s => s.user_uid === p.user_uid)
      ? m.tournament_status_finished()
      : m.tournament_status_dropped();
  });
  // Open rounds: gate self-check-in on rounds-played (not player state), so a
  // capped player can't self-check-in regardless of whether they rest in
  // Completed, Finished, or Registered.
  const atCap = $derived(
    (tournament.max_rounds ?? 0) > 0 && roundsPlayed(tournament, userUid) >= (tournament.max_rounds ?? 0),
  );
  // Registration is never refused: past the cap a sign-up lands on the waitlist.
  const seatedCount = $derived(tournament.players?.filter(p => !p.waitlisted).length ?? 0);
  const registrationCapReached = $derived(
    (tournament.max_players ?? 0) > 0 && seatedCount >= (tournament.max_players ?? 0),
  );
  const iAmWaitlisted = $derived(!!currentPlayerEntry?.waitlisted);

  // A registered participant can seat their own 4-5 pod without an organizer.
  // Mirrors the engine's eligibility gate (error.rs); the engine re-validates
  // server-side, the UI just avoids showing an impossible action.
  let showSelfOrganize = $state(false);
  function isSelfOrganizeEligible(p: Player): boolean {
    const uid = p.user_uid;
    if (!uid) return false;
    if (p.state !== "Registered" && p.state !== "Checked-in") return false;
    if (p.waitlisted) return false;
    // No cap (max_rounds 0) means no per-player limit; only gate when a cap is set.
    return !((tournament.max_rounds ?? 0) > 0 && roundsPlayed(tournament, uid) >= (tournament.max_rounds ?? 0));
  }
  const canSelfOrganize = $derived(
    (tournament.self_organized_rounds ?? false) &&
    !tournament.finals &&
    (tournament.state === "Waiting" || tournament.state === "Playing") &&
    !!currentPlayerEntry &&
    isSelfOrganizeEligible(currentPlayerEntry),
  );
  // The other eligible players the initiator may seat (current user excluded).
  const selfOrganizeCandidates = $derived(
    (tournament.players ?? [])
      .filter(p => p.user_uid && p.user_uid !== userUid && isSelfOrganizeEligible(p))
      .map(p => ({ uid: p.user_uid as string, name: seatDisplayUtil(p.user_uid as string, playerInfo, tournament.online) }))
      .sort((a, b) => a.name.localeCompare(b.name)),
  );

  let actionError = $state<string | null>(null);
  // Keyed by round as well as table: parallel rounds put two tables of the same index on screen.
  let scoreError = $state<{ round: number; table: number; message: string } | null>(null);

  async function playerAction(action: TournamentEventType, body?: Record<string, unknown>) {
    actionError = await doAction(action, body, { silent: true });
  }

  let selfOrganizeError = $state<string | null>(null);
  async function submitSelfOrganize(picked: string[]) {
    // On failure keep the dialog open with the error inline — the page banner
    // is at the top, likely scrolled out of view.
    selfOrganizeError = await doAction("SelfOrganizeRound", { player_uids: [userUid, ...picked] }, { silent: true });
    if (!selfOrganizeError) showSelfOrganize = false;
  }

  // Distinguish "no deck" from "deck present but invalid", and surface blocking
  // validation errors inline so the player can act at the door instead of
  // hunting for the deck section.
  const hasDeck = $derived(!!decksByUser?.[userUid]?.[0]);
  const deckErrorMessages = $derived((myDeckErrors ?? []).filter(e => e.severity === 'error').map(e => e.message));
  // A registered (or reinstatable Finished) player who still needs to check in during
  // the check-in window. Drives the prominent check-in call and the deck warning.
  const notCheckedIn = $derived(
    !!currentPlayerEntry &&
    (currentPlayerEntry.state === "Registered" || currentPlayerEntry.state === "Finished") &&
    tournament.state === "Waiting" &&
    !atCap &&
    !iAmWaitlisted
  );
  // Missing/invalid decklist is a warning beside check-in, NOT a gate: the
  // engine allows deck-less check-in (mod.rs CheckIn just stamps missing_decklist).
  const showDeckWarn = $derived(notCheckedIn && tournament.decklist_required && !playerHasValidDeck);
  const myActiveRounds = $derived.by(() => {
    if (!tournament.rounds || tournament.state !== "Playing" || isFinals) return [];
    const lastRoundIdx = tournament.rounds.length - 1;
    return tournament.rounds
      .map((round, r) => ({ round, r }))
      // Editable until the round closes, not until every table reads Finished:
      // a player-scored table carries no judge_uid, so the engine allows
      // SetScore while Playing.
      .filter(({ round, r }) => r === lastRoundIdx || round.some(t => t.state !== "Finished"))
      .map(({ round, r }) => {
        const tIdx = round.findIndex(t => t.seating.some(s => s.player_uid === userUid));
        return tIdx >= 0 ? { roundIdx: r, tableIdx: tIdx, table: round[tIdx]! } : null;
      })
      .filter((x): x is { roundIdx: number; tableIdx: number; table: typeof tournament.rounds[0][0] } => x !== null);
  });

  const hasParallelRounds = $derived(myActiveRounds.length > 1 || (
    tournament.rounds?.filter(r => r.some(t => t.state !== "Finished")).length ?? 0
  ) > 1);

  // History is whatever isn't live: deferring to myActiveRounds keeps the
  // current round out, since that list owns the last round even once every
  // table reads Finished.
  const previousRounds = $derived.by(() => {
    if (!tournament.rounds?.length) return [];
    const active = new Set(myActiveRounds.map(a => a.roundIdx));
    const result: { round: number; roundIdx: number; tableIdx: number; tableLabel: string; table: typeof tournament.rounds[0][0] }[] = [];
    for (let r = 0; r < tournament.rounds.length; r++) {
      if (active.has(r)) continue;
      const round = tournament.rounds[r]!;
      const tIdx = round.findIndex(t => t.seating.some(s => s.player_uid === userUid));
      if (tIdx >= 0) {
        result.push({
          round: r + 1,
          roundIdx: r,
          tableIdx: tIdx,
          tableLabel: tableLabel(tournament.table_rooms, tIdx) ?? m.rounds_table_n({ n: String(tIdx + 1) }),
          table: round[tIdx]!,
        });
      }
    }
    return result;
  });

  async function handleCallJudge(tableIdx: number) {
    if (judgeCallCooldown) return;
    try {
      await callJudge(tournament.uid, tableIdx);
      judgeCallCooldown = true;
      setTimeout(() => { judgeCallCooldown = false; }, 30_000);
    } catch {}
  }

  function seatDisplay(uid: string): string {
    return seatDisplayUtil(uid, playerInfo, tournament.online);
  }

  function sanctionsForPlayer(uid: string): Sanction[] {
    return tournamentSanctions.filter(s => s.user_uid === uid);
  }

  const ratingCtx = $derived(ratingContext(tournament, tournamentSanctions));
  // Anonymous viewers hold no sanctions: the SA-adjusted figure isn't computable
  // for them, so drop the column rather than show a possibly-wrong number.
  const showRating = $derived(isFinished && getAuthState().isAuthenticated);
</script>

{#snippet refusal(message: string)}
  <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-3">
    <p class="text-link-soft text-sm">{message}</p>
  </div>
{/snippet}

<!-- Warning beside the check-in CTA, not a gate (engine treats missing/invalid
     decklist as non-blocking). No jump-to-deck button: the section is right
     below, and a button here would read as a spurious "upload" action. -->
{#snippet deckWarn()}
  <div class="banner-warn border rounded-lg p-3">
    <div class="flex items-start gap-2 text-sm">
      <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
      <div class="min-w-0">
        <p class="font-medium">{hasDeck ? m.tournament_checkin_invalid_deck_warn() : m.tournament_checkin_no_deck_warn()}</p>
        {#if deckErrorMessages.length > 0}
          <ul class="mt-1 list-disc list-inside text-xs space-y-0.5">
            {#each deckErrorMessages as msg}<li>{msg}</li>{/each}
          </ul>
        {/if}
      </div>
    </div>
  </div>
{/snippet}

<!-- Online has no on-site QR: check-in happens server-side (Discord bot
     self-serve or organizer). Point at the join link instead; mirrors Button's
     primary/lg/block styling since this is an <a>, not a button. -->
{#snippet onlineJoin()}
  {#if tournament.venue_url}
    <a href={tournament.venue_url} target="_blank" rel="noopener"
       class="inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium min-h-[44px] bg-accent-strong hover:bg-accent-strong-hover text-white transition-colors">
      <ExternalLink class="w-4 h-4" aria-hidden="true" />
      {m.tournament_join_online_btn({ venue: tournament.venue ?? "" })}
    </a>
  {/if}
{/snippet}

<div class="bg-surface-card rounded-lg shadow border border-line mb-6 p-6 space-y-4">
  {#if iAmWaitlisted}
    <div class="banner-warn border rounded-lg p-3 text-sm flex items-start gap-2">
      <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
      <span>{m.tournament_waitlisted_player()}</span>
    </div>
  {/if}
  {#if tournament.state === "Registration" && !currentPlayerEntry}
    {#if userSuspended}
      <div class="text-sm text-link">{m.error_suspended_cannot_register()}</div>
    {:else if !userVeknId}
      <div class="banner-warn border rounded-lg p-3 text-sm">
        <div class="flex items-center gap-2">
          <TriangleAlert class="w-4 h-4 shrink-0" aria-hidden="true" />
          <span class="font-medium">{m.tournament_vekn_id_required_to_register()}</span>
        </div>
        <p class="mt-2">
          {m.vekn_guidance_have_id()}
          <a href="/profile?claim=1" class="underline hover:text-warn">{m.vekn_guidance_claim_link()}</a>
        </p>
        <p class="mt-1">{m.vekn_guidance_new_member()}</p>
      </div>
    {:else}
      {#if registrationCapReached}
        <div class="banner-warn border rounded-lg p-3 text-sm flex items-start gap-2">
          <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>{m.tournament_cap_waitlist_player({ count: String(seatedCount), cap: String(tournament.max_players ?? 0) })}</span>
        </div>
      {/if}
      <Button
        variant="primary"
        size="lg"
        onclick={() => playerAction("Register", { user_uid: userUid, vekn_id: userVeknId })}
        disabled={actionLoading}
      >{m.tournament_register_btn()}</Button>
      {#if actionError}{@render refusal(actionError)}{/if}
    {/if}
  {:else if tournament.state === "Registration" && currentPlayerEntry}
    <div class="text-sm mb-3 flex items-center justify-between gap-2">
      <span class="text-ink-bright">
        <span class="sr-only">{m.tournament_your_status()}</span>
        {translatePlayerState(currentPlayerEntry.state)}
      </span>
      <Button
        variant="danger"
        onclick={() => playerAction("Unregister", { user_uid: userUid })}
        disabled={actionLoading}
      ><Ban class="w-4 h-4" aria-hidden="true" />{m.tournament_unregister_btn()}</Button>
    </div>
    {#if actionError}{@render refusal(actionError)}{/if}
  {:else if tournament.state === "Waiting" && !currentPlayerEntry}
    {#if tournament.online}
      {@render onlineJoin()}
      <p class="text-sm text-ink-muted">{m.tournament_online_checkin_unregistered()}</p>
    {:else}
      {#if registrationCapReached}
        <div class="banner-warn border rounded-lg p-3 text-sm flex items-start gap-2">
          <TriangleAlert class="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
          <span>{m.tournament_cap_warning_player({ count: String(seatedCount), cap: String(tournament.max_players ?? 0) })}</span>
        </div>
      {/if}
      <Button
        variant="primary"
        size="lg"
        onclick={() => showQrScanner = true}
        disabled={actionLoading}
      >
        <QrCode class="w-4 h-4" />
        {m.tournament_register_checkin_btn()}
      </Button>
    {/if}
  {:else if currentPlayerEntry || tournament.state === "Playing"}
    <!-- Prominent check-in call: during the check-in window this is the loudest
         message a not-yet-checked-in player sees — above status and deck notes. -->
    {#if notCheckedIn}
      <div class="banner-info border rounded-lg p-3 mb-3 text-sm">
        <p class="font-medium">{m.tournament_checkin_call_player()}</p>
        <p class="text-ink-muted">{tournament.online ? m.tournament_checkin_call_player_online() : m.tournament_checkin_call_player_qr()}</p>
      </div>
    {/if}
    {#if !currentPlayerEntry}
      <!-- Spectator (no entry) during play: neutral copy, then finals/standings below.
           Before finals, tell a would-be latecomer they can still get in. -->
      <div class="banner-info border rounded-lg p-3 mb-3 text-sm">
        <p>{m.tournament_event_in_progress()}</p>
        {#if !isFinals}
          <p class="text-ink-muted mt-1">{m.tournament_playing_latecomer()}</p>
        {/if}
      </div>
    {:else}
    <!-- State, score and the bar to clear are one fact: one line. -->
    <div class="text-sm mb-3 flex items-start justify-between gap-2">
      <div class="min-w-0 flex flex-wrap items-center gap-x-1.5 gap-y-1">
        <span class="text-ink-bright">
          <span class="sr-only">{m.tournament_your_status()}</span>
          {myStatusLabel}
        </span>
        {#if showMyScore && myStanding}
          <span class="text-ink-faint" aria-hidden="true">·</span>
          <span class="text-ink-strong font-medium">
            <span class="sr-only">{m.tournament_your_score()}</span>
            {formatScore(myStanding.gw, myStanding.vp, myStanding.tp)}
          </span>
          <ScoreLegend compact />
        {/if}
        {#if cutoffScore}
          <span class="w-full text-xs text-ink-faint">
            {m.tournament_cutoff_threshold()}
            <span class="text-ink-muted">{formatScore(cutoffScore.gw, cutoffScore.vp, cutoffScore.tp)}</span>
          </span>
        {/if}
      </div>
      {#if !tournament.online && !atCap && !iAmWaitlisted && currentPlayerEntry.state === "Registered" && tournament.state === "Waiting"}
        <Button
          variant="ghost"
          onclick={() => showQrScanner = !showQrScanner}
          disabled={actionLoading}
        >
          <QrCode class="w-4 h-4" />
          {m.checkin_qr_scan_btn()}
        </Button>
      {:else if currentPlayerEntry.state === "Finished" && (tournament.state === "Waiting" || tournament.state === "Playing")}
        <!-- Reversible, not confirmed: a drop-out never left the venue, so a self
             check-in (at cap: to Completed, mid-round: back to their seat) is enough. -->
        <Button
          variant="ghost"
          onclick={() => playerAction("CheckIn", { player_uid: userUid })}
          disabled={actionLoading}
        >
          <Undo2 class="w-4 h-4" aria-hidden="true" />
          {m.tournament_check_in_btn()}
        </Button>
      {:else if currentPlayerEntry.state !== "Finished" && (tournament.state === "Waiting" || tournament.state === "Playing")}
        <Button
          variant="danger"
          onclick={async () => { actionError = await dropPlayer(userUid); }}
          disabled={actionLoading}
        ><Trash2 class="w-4 h-4" aria-hidden="true" />{m.tournament_drop_out_btn()}</Button>
      {/if}
    </div>
    {#if actionError}<div class="mb-3">{@render refusal(actionError)}</div>{/if}
    {/if}
    <!-- Online check-in is server-side (bot self-serve or organizer). The check-in
         call banner above carries the instruction; here we just surface the Join link. -->
    {#if tournament.online && notCheckedIn}
      <div class="mb-3">
        {@render onlineJoin()}
      </div>
    {/if}
    <!-- Open rounds: capped player gets no check-in CTA — tell them they're done and finals-eligible. -->
    {#if atCap && tournament.state === "Waiting"}
      <p class="text-sm text-ink-muted mb-3">{m.player_completed_awaiting_finals()}</p>
    {/if}
    {#if showDeckWarn}
      <div class="mb-3">{@render deckWarn()}</div>
    {/if}
    {#if canSelfOrganize}
      <div class="border-t border-line pt-4 space-y-2">
        <div class="flex items-start gap-2">
          <Users class="w-4 h-4 mt-0.5 text-link shrink-0" aria-hidden="true" />
          <div class="min-w-0">
            <h3 class="text-sm font-medium text-ink-strong">{m.self_organize_title()}</h3>
            <p class="text-xs text-ink-muted mt-0.5">{m.self_organize_tip()}</p>
          </div>
        </div>
        <Button
          variant="primary"
          size="lg"
          block
          class="min-h-[44px]"
          disabled={actionLoading}
          onclick={() => showSelfOrganize = true}
        >
          {m.self_organize_start_btn()}
        </Button>
      </div>
    {/if}
    <!-- Your table + seat — the primary card during play; standings/cutoff/history follow below -->
    {#if isFinals && !isFinished && tournament.finals}
      {@const finalsSeatIdx = tournament.finals.seating.findIndex(s => s.player_uid === userUid)}
      {@const finalsSize = tournament.finals.seating.length}
      <div class="border-t border-line pt-4">
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-medium text-ink-strong">{m.tournament_finals_heading()}</h3>
          <span class="text-xs px-2 py-0.5 rounded {tournament.finals.state === 'Finished' ? 'badge-success' : tournament.finals.state === 'Invalid' ? 'bg-accent-soft/60 text-link-soft' : 'badge-pending'}">
            {translateTableState(tournament.finals.state)}
          </span>
        </div>
        <!-- Finals timer (read-only; hidden in offline tournaments) -->
        {#if !tournament.offline_mode && (tournament.finals_time || tournament.round_time || 0) > 0}
          <div class="mb-2">
            <TimerDisplay {tournament} finals />
          </div>
        {/if}
        <div class="space-y-1.5">
          {#each tournament.finals.seating as seat, j}
            {@const tVps = tournament.finals.seating.map(s => s.result.vp)}
            {@const preview = previewScoresSync(tournament, tournamentSanctions, tournament.rounds?.length ?? 0, 0, tVps)}
            {@const tGws = preview ? preview.gw : tournament.finals.seating.map(s => s.result.gw)}
            {@const tTps = preview ? preview.tp : tournament.finals.seating.map(s => s.result.tp)}
            {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
            {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
            {@const isMe = seat.player_uid === userUid}
            {@const isPrey = finalsSeatIdx >= 0 && j === (finalsSeatIdx + 1) % finalsSize}
            {@const isPredator = finalsSeatIdx >= 0 && j === (finalsSeatIdx - 1 + finalsSize) % finalsSize}
            <div class="px-2.5 -mx-2.5 py-2 rounded-md {isMe ? 'ring-1 ring-inset ring-accent/40 bg-accent-soft/10' : ''}">
              <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
                <div class="min-w-0">
                  <span class="min-w-0 inline-flex items-center gap-1.5">
                    <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: String(j + 1) })}</span>
                    <span class="text-ink truncate min-w-0">{seatDisplay(seat.player_uid)}</span>
                    {#if isMe}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_you()}</span>
                    {:else if isPrey}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_prey()}</span>
                    {:else if isPredator}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_predator()}</span>{/if}
                  </span>
                  <div class="text-xs text-ink-faint">{m.tournament_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if} · {tGws[j]}GW {tTps[j]}TP</div>
                </div>
              </div>
              {#if finalsSeatIdx >= 0}
                <VpInput
                  value={seat.result.vp}
                  options={vpOptions(tournament.finals.seating.length, false)}
                  label={seatDisplay(seat.player_uid)}
                  disabled={scoreSaving === -1}
                  saving={scoreSavingSeat === seat.player_uid && scoreSaving === -1}
                  onchange={async (v) => { const e = await setFinalsVp(seat.player_uid, v, tournament.finals!.seating, { silent: true }); scoreError = e ? { round: -1, table: -1, message: e } : null; }}
                />
              {:else}
                <!-- The engine rejects non-finalists' VP edits: read-only, not chips. -->
                <span class="inline-flex items-center gap-1 text-xs text-ink-muted">
                  {seat.result.vp}VP
                  <Lock class="w-3.5 h-3.5" aria-hidden="true" />
                </span>
              {/if}
            </div>
          {/each}
        </div>
        {#if scoreError?.round === -1}<div class="mt-2">{@render refusal(scoreError.message)}</div>{/if}
      </div>
    {:else if tournament.state === "Playing" && (tournament.rounds?.length ?? 0) > 0}
      <!-- Idle is uneventful, not an alert. -->
      {#if currentPlayerEntry?.state === "Completed"}
        <p class="text-sm text-ink-muted">{m.player_completed_awaiting_finals()}</p>
      {:else if myActiveRounds.length === 0 && currentPlayerEntry?.state === "Checked-in"}
        <p class="text-sm text-ink-muted">{m.player_sitting_out()}</p>
      {:else}
        {#each myActiveRounds as active}
          {@const myTable = active.table}
          {@const myTableIdx = active.tableIdx}
          {@const roundIdx = active.roundIdx}
          {@const mySeatIdx = myTable.seating.findIndex(s => s.player_uid === userUid)}
          {@const tableSize = myTable.seating.length}
          {@const tableLocked = myTable.seating.some(s => s.judge_uid) || !!myTable.override}
          <div class="border-t border-line pt-4">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium text-ink-strong">
                {#if hasParallelRounds}{m.rounds_round_n({ n: String(roundIdx + 1) })} · {/if}{m.tournament_your_table({ label: tableLabel(tournament.table_rooms, myTableIdx) ?? m.rounds_table_n({ n: String(myTableIdx + 1) }) })}
              </h3>
              <span class="text-xs px-2 py-0.5 rounded {myTable.state === 'Finished' ? 'badge-success' : myTable.state === 'Invalid' ? 'bg-accent-soft/60 text-link-soft' : 'badge-pending'}">
                {translateTableState(myTable.state)}
              </span>
            </div>
            <!-- Judge-adjudicated table: scores are locked (the engine rejects
                 player edits) and the ruling is visible to the seated players. -->
            {#if tableLocked}
              <p class="text-xs text-ink-muted mb-2 inline-flex items-center gap-1">
                <Lock class="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                {m.player_table_locked()}
              </p>
            {/if}
            {#if myTable.override}
              <p class="text-xs text-warn mb-2">
                <ShieldCheck class="w-3.5 h-3.5 inline mr-1" aria-hidden="true" />
                {m.override_overridden({ comment: myTable.override.comment })}
              </p>
            {/if}
            {#if !hasParallelRounds && !tournament.offline_mode && (tournament.round_time ?? 0) > 0}
              <div class="mb-2">
                <TimerDisplay {tournament} tableIndex={myTableIdx} />
              </div>
            {/if}
            <div class="space-y-1.5">
              {#each myTable.seating as seat, j}
                {@const tVps = myTable.seating.map(s => s.result.vp)}
                {@const preview = previewScoresSync(tournament, tournamentSanctions, roundIdx, myTableIdx, tVps)}
                {@const tGws = preview ? preview.gw : myTable.seating.map(s => s.result.gw)}
                {@const tTps = preview ? preview.tp : myTable.seating.map(s => s.result.tp)}
                {@const isMe = seat.player_uid === userUid}
                {@const isPrey = mySeatIdx >= 0 && j === (mySeatIdx + 1) % tableSize}
                {@const isPredator = mySeatIdx >= 0 && j === (mySeatIdx - 1 + tableSize) % tableSize}
                <div class="px-2.5 -mx-2.5 py-2 rounded-md {isMe ? 'ring-1 ring-inset ring-accent/40 bg-accent-soft/10' : ''}">
                  <div class="flex items-center justify-between gap-2 mb-1.5 text-sm">
                    <span class="min-w-0 inline-flex items-center gap-1.5">
                      <span class="text-ink-faint text-xs tabular-nums shrink-0">{m.tournament_seat_n({ n: String(j + 1) })}</span>
                      <span class="text-ink truncate min-w-0">{seatDisplay(seat.player_uid)}</span>
                      {#if isMe}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_you()}</span>
                      {:else if isPrey}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_prey()}</span>
                      {:else if isPredator}<span class="shrink-0 px-1.5 py-0.5 rounded text-xs badge-slate">{m.tournament_seat_predator()}</span>{/if}
                    </span>
                    <span class="text-ink-faint text-xs shrink-0">{tGws[j]}GW {tTps[j]}TP</span>
                  </div>
                  {#if tableLocked}
                    <span class="inline-flex items-center gap-1 text-xs text-ink-muted">
                      {seat.result.vp}VP
                      <Lock class="w-3.5 h-3.5" aria-hidden="true" />
                    </span>
                  {:else}
                    <VpInput
                      value={seat.result.vp}
                      options={vpOptions(myTable.seating.length, false)}
                      label={seatDisplay(seat.player_uid)}
                      disabled={scoreSaving === myTableIdx}
                      saving={scoreSavingSeat === seat.player_uid && scoreSaving === myTableIdx}
                      onchange={async (v) => { const e = await setVp(roundIdx, myTableIdx, seat.player_uid, v, myTable.seating, { silent: true }); scoreError = e ? { round: roundIdx, table: myTableIdx, message: e } : null; }}
                    />
                  {/if}
                </div>
              {/each}
            </div>
            {#if scoreError?.round === roundIdx && scoreError.table === myTableIdx}<div class="mt-2">{@render refusal(scoreError.message)}</div>{/if}
            {#if !tournament.offline_mode && isOnline()}
              <Button
                variant="primary"
                size="lg"
                block
                disabled={judgeCallCooldown}
                onclick={() => handleCallJudge(myTableIdx)}
                class="mt-3 min-h-[44px]"
              >
                <Gavel class="w-5 h-5" />
                {judgeCallCooldown ? m.judge_call_cooldown() : m.judge_call_btn()}
              </Button>
            {/if}
          </div>
        {/each}
      {/if}
    {/if}
    <!-- Spectators have no score line to carry the cutoff. -->
    {#if cutoffScore && !currentPlayerEntry}
      <p class="text-sm text-ink-muted">
        {m.tournament_cutoff_threshold()}
        <span class="text-ink font-medium">{formatScore(cutoffScore.gw, cutoffScore.vp, cutoffScore.tp)}</span>
      </p>
    {/if}
    {#if tournament.state !== "Finished" && playerStandings.length > 0}
      <div class="border-t border-line pt-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">
          {m.tournament_standings()}
          {#if tournament.standings_mode !== "Public"}
            <span class="text-xs text-ink-faint font-normal ml-1">({translateStandingsMode(tournament.standings_mode)})</span>
          {/if}
        </h3>
        <!-- The score line above already carries it. -->
        {#if !showMyScore}<ScoreLegend />{/if}
        <table class="w-full text-sm">
          <thead>
            <tr class="text-ink-faint text-xs">
              <th class="text-left py-1 pr-2">{m.tournament_col_rank()}</th>
              <th class="text-left py-1 pr-2">{m.tournament_col_player()}</th>
              <th class="text-right py-1 px-2">{m.tournament_col_score()}</th>
            </tr>
          </thead>
          <tbody>
            {#each playerStandings as entry, idx}
              <tr class="{idx < 5 ? 'text-ink-strong' : 'text-ink-muted'} border-t border-line">
                <td class="py-1 pr-2 text-ink-faint">{#if entry.unplaced}—{:else}<RankCell rank={entry.rank} finalist={entry.finalist} />{/if}</td>
                <td class="py-1 pr-2">
                  <span class="inline-flex items-center gap-1">
                    {seatDisplay(entry.user_uid)}
                    <SanctionIndicator sanctions={sanctionsForPlayer(entry.user_uid)} />
                    {#if entry.disqualified}<span class="text-xs text-link">{m.tournament_disqualified()}</span>{/if}
                  </span>
                </td>
                <td class="text-right py-1 px-2">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
    {#if previousRounds.length > 0}
      <div>
        <button
          onclick={() => showPreviousRounds = !showPreviousRounds}
          class="text-sm text-ink-muted hover:text-ink-bright transition-colors flex items-center gap-1"
        >
          {#if showPreviousRounds}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          {m.tournament_previous_rounds()}
        </button>
        {#if showPreviousRounds}
          <div class="mt-2 space-y-3">
            {#each previousRounds as prev}
              <div class="border-t border-line pt-3">
                <h4 class="text-xs font-medium text-ink-muted mb-1.5">{m.tournament_round_table({ round: String(prev.round), table: prev.tableLabel })}</h4>
                {#if prev.table.override}
                  <p class="text-xs text-warn mb-1.5">
                    <ShieldCheck class="w-3.5 h-3.5 inline mr-1" aria-hidden="true" />
                    {m.override_overridden({ comment: prev.table.override.comment })}
                  </p>
                {/if}
                <div class="divide-y divide-line">
                  {#each prev.table.seating as seat, j}
                    {@const tVps = prev.table.seating.map(s => s.result.vp)}
                    {@const preview = previewScoresSync(tournament, tournamentSanctions, prev.roundIdx, prev.tableIdx, tVps)}
                    {@const tGws = preview ? preview.gw : prev.table.seating.map(s => s.result.gw)}
                    {@const tTps = preview ? preview.tp : prev.table.seating.map(s => s.result.tp)}
                    <div class="py-1 flex items-center justify-between text-sm {seat.player_uid === userUid ? 'text-ink-strong' : 'text-ink-muted'}">
                      <span>{seatDisplay(seat.player_uid)}</span>
                      <span class="text-xs">{seat.result.vp}VP {tGws[j]}GW {tTps[j]}TP</span>
                    </div>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  {:else if tournament.state === "Finished"}
    <!-- Results render right below; no misleading registration copy. -->
    <p class="text-ink-muted text-sm">{m.tournament_event_finished()}</p>
  {:else}
    <p class="text-ink-muted text-sm">{m.tournament_registration_not_open()}</p>
  {/if}

  {#if showQrScanner}
    <QrCheckinScanner tournamentUid={tournament.uid} onclose={() => showQrScanner = false} />
  {/if}

  {#if showSelfOrganize}
    <SelfOrganizeDialog
      selfName={seatDisplay(userUid)}
      candidates={selfOrganizeCandidates}
      submitting={actionLoading}
      error={selfOrganizeError}
      onSubmit={submitSelfOrganize}
      onClose={() => { showSelfOrganize = false; selfOrganizeError = null; }}
    />
  {/if}

  {#if (tournament.state === "Planned" || tournament.state === "Registration") && (tournament.players?.length ?? 0) > 0}
    {@const registered = tournament.players!.filter(p => p.state === "Registered" && !p.waitlisted)}
    {#if registered.length > 0}
      <div class="mt-4">
        <button
          onclick={() => showRegisteredPlayers = !showRegisteredPlayers}
          class="text-sm text-ink-muted hover:text-ink-bright transition-colors flex items-center gap-1"
        >
          {#if showRegisteredPlayers}<ChevronDown class="w-4 h-4" />{:else}<ChevronRight class="w-4 h-4" />{/if}
          {m.tournament_registered_players({ count: String(registered.length) })}
        </button>
        {#if showRegisteredPlayers}
          <div class="mt-2 flex flex-wrap gap-2">
            {#each registered as player}
              {@const puid = player.user_uid ?? ""}
              <span class="px-2 py-1 text-sm bg-surface-hover rounded text-ink-bright">
                {seatDisplay(puid)}
              </span>
            {/each}
          </div>
        {/if}
      </div>
    {/if}
  {/if}

  {#if currentPlayerEntry || (tournament.state === 'Finished' && tournament.decklists_mode)}
    <div id="player-deck-section" class="mt-4 scroll-mt-4">
      <PlayerDecksSection
        {tournament}
        {playerInfo}
        {decksByUser}
      />
    </div>
  {/if}
</div>

{#if (tournament.state === "Waiting" || tournament.state === "Playing" || tournament.state === "Finished") && (tournament.raffles?.length ?? 0) > 0}
  <div class="bg-surface-card rounded-lg shadow border border-line mb-6 p-6">
    <h3 class="text-sm font-medium text-ink mb-3">{m.raffle_title()}</h3>
    <RaffleSection
      {tournament}
      {playerInfo}
      isOrganizer={false}
      sanctions={[]}
    />
  </div>
{/if}

<!-- Finished tournament results — public once finished, no VEKN-ID gate -->
{#if tournament.state === "Finished"}
  {@const hasFinals = standings.some(e => e.finals)}
  <div class="bg-surface-card rounded-lg shadow border border-line mb-6 p-6 space-y-4">
    {#if tournament.winner}
      <div class="banner-highlight border rounded-lg p-4">
        <div class="text-ink-faint text-sm">{m.tournament_winner()}</div>
        <div class="text-xl font-medium text-ink-strong">{seatDisplay(tournament.winner)}</div>
      </div>
    {/if}
    <!-- Unranked events: state the rule inline (a player's missing winner/
         finalist bonus must read as a rule, not a bug) -->
    <RankedBadge {tournament} variant="note" />
    {#if standings.length > 0}
      <!-- Players are the ones motivated to post their placement: share stays
           here too, not only on the organizer view (reports stay organizer-only) -->
      <div class="flex flex-wrap items-center gap-2">
        <CopyResultsButton {tournament} {playerInfo} {standings} />
      </div>
      <div class="border-t border-line pt-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">{m.tournament_standings()}</h3>
        <ScoreLegend showRtp />
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-ink-faint text-xs">
                <th class="text-left py-1 pr-2">{m.tournament_col_rank()}</th>
                <th class="text-left py-1 pr-2">{m.tournament_col_player()}</th>
                <th class="text-right py-1 px-2">{m.tournament_col_score()}</th>
                {#if hasFinals}
                  <th class="text-right py-1 px-2">{m.tournament_col_finals()}</th>
                {/if}
                {#if showRating}
                  <th class="text-right py-1 px-2">{m.tournament_col_rating()}</th>
                {/if}
              </tr>
            </thead>
            <tbody>
              {#each standings as entry, idx}
                <tr class="{idx < 5 ? 'text-ink-strong' : 'text-ink-muted'} border-t border-line">
                  <td class="py-1 pr-2 text-ink-faint">{#if entry.unplaced}—{:else}<RankCell rank={entry.rank} finalist={entry.finalist} />{/if}</td>
                  <td class="py-1 pr-2">
                    <span class="inline-flex items-center gap-1">
                      {seatDisplay(entry.user_uid)}
                      <SanctionIndicator sanctions={sanctionsForPlayer(entry.user_uid)} />
                      {#if entry.disqualified}<span class="text-xs text-link">{m.tournament_disqualified()}</span>{/if}
                    </span>
                  </td>
                  <td class="text-right py-1 px-2">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
                  {#if hasFinals}
                    <td class="text-right py-1 px-2">{entry.finals ?? ""}</td>
                  {/if}
                  {#if showRating}
                    {@const pts = getRatingPts(entry, tournament, ratingCtx)}
                    <td class="text-right py-1 px-2 text-ink-muted">{pts ?? "—"}</td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
    {#if tournament.finals}
      <div class="border-t border-line pt-4">
        <h3 class="text-sm font-medium text-ink-strong mb-2">{m.tournament_finals_table()}</h3>
        <div class="divide-y divide-line">
          {#each tournament.finals.seating as seat, j}
            <!-- Finished: stored gw/tp are the engine-refreshed, SA-adjusted truth. -->
            {@const tGws = tournament.finals.seating.map(s => s.result.gw)}
            {@const tTps = tournament.finals.seating.map(s => s.result.tp)}
            {@const seedIdx = tournament.finals.seed_order.indexOf(seat.player_uid) + 1}
            {@const seedStanding = standings.find(s => s.user_uid === seat.player_uid)}
            <div class="py-1.5 flex items-center justify-between text-sm">
              <div>
                <span class="text-ink">{seatDisplay(seat.player_uid)}</span>
                <div class="text-xs text-ink-faint">{m.tournament_seed({ n: String(seedIdx) })}{#if seedStanding} · {formatScore(seedStanding.gw, seedStanding.vp, seedStanding.tp)}{/if}</div>
              </div>
              <span class="text-ink-faint text-xs">{seat.result.vp}VP {tGws[j]}GW {tTps[j]}TP</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </div>
{/if}
