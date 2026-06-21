<script lang="ts">
  import { toUserMessage } from '$lib/errors';
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { getLeague, getAllTournaments, getAllLeagues } from "$lib/db";
  import { updateLeague, deleteLeagueApi, addLeagueOrganizer, removeLeagueOrganizer } from "$lib/api";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAuthState } from "$lib/stores/auth.svelte";
  import { getUser } from "$lib/db";
  import type { League, Tournament, LeagueStandingsMode } from "$lib/types";
  import { canEditLeague, computeLeagueStandings } from "$lib/engine";
  import { translateTournamentState } from "$lib/tournament-utils";
  import { formatScore } from "$lib/utils";
  import OrganizerManager from "$lib/components/OrganizerManager.svelte";
  import FoldableDescription from "$lib/components/FoldableDescription.svelte";
  import Button from '$lib/components/Button.svelte';
  import { Loader2, CircleAlert, ArrowLeft, Pencil, Trash2, Plus, X, Trophy } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';

  const uid = $derived(page.params.uid);
  const countries = getCountries();
  const auth = $derived(getAuthState());

  let league = $state<League | null>(null);
  let parentLeague = $state<{ uid: string; name: string } | null>(null);
  let leagueTournaments = $state<Tournament[]>([]);
  let childLeagues = $state<League[]>([]);
  let orphanLeagues = $state<League[]>([]);
  let addChildUid = $state("");
  let organizerNames = $state<Record<string, string>>({});
  let loaded = $state(false);
  let editing = $state(false);
  let error = $state<string | null>(null);

  interface StandingEntry {
    user_uid: string;
    gw: number;
    vp: number;
    tp: number;
    points?: number;
    rank: number;
    tournaments_count: number;
    name?: string;
  }
  let standings = $state<StandingEntry[]>([]);
  let standingsError = $state(false);

  const isOrganizer = $derived(league ? canEditLeague(auth.user, league) : false);

  function standingsModeLabel(mode: LeagueStandingsMode): string {
    switch (mode) {
      case "RTP": return m.league_standings_rtp();
      case "Score": return m.league_standings_score();
      case "GP": return m.league_standings_gp();
      default: return mode;
    }
  }

  function formatDate(d: string | null): string {
    if (!d) return "—";
    try {
      return new Date(d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    } catch { return d; }
  }

  function isActive(): boolean {
    if (!league) return false;
    if (!league.finish) return true;
    return new Date(league.finish) >= new Date();
  }

  async function loadLeague() {
    if (!uid) return;
    const l = await getLeague(uid);
    if (!l || l.deleted_at) {
      league = null;
      loaded = true;
      return;
    }
    league = l;

    // Resolve parent meta-league (for the appartenance badge)
    const p = l.parent_uid ? await getLeague(l.parent_uid) : undefined;
    parentLeague = p && !p.deleted_at ? { uid: p.uid, name: p.name } : null;

    // Load associated tournaments
    const allTournaments = await getAllTournaments();
    leagueTournaments = allTournaments
      .filter(t => t.league_uid === uid && !t.deleted_at)
      .sort((a, b) => (b.start || b.modified).localeCompare(a.start || a.modified));

    // Load child leagues if meta-league
    if (l.kind === "Meta-League") {
      const allLeagues = await getAllLeagues();
      childLeagues = allLeagues
        .filter(cl => cl.parent_uid === uid && !cl.deleted_at)
        .sort((a, b) => (a.name).localeCompare(b.name));
      orphanLeagues = allLeagues
        .filter(cl => cl.kind === "League" && !cl.parent_uid && !cl.deleted_at && cl.uid !== uid)
        .sort((a, b) => (a.name).localeCompare(b.name));
      // Also include child league tournaments
      const childUids = childLeagues.map(cl => cl.uid);
      const childTournaments = allTournaments.filter(
        t => childUids.includes(t.league_uid ?? "") && !t.deleted_at
      );
      leagueTournaments = [...leagueTournaments, ...childTournaments]
        .sort((a, b) => (b.start || b.modified).localeCompare(a.start || a.modified));
    } else {
      childLeagues = [];
      orphanLeagues = [];
    }

    // Load organizer names
    const names: Record<string, string> = {};
    for (const ouid of l.organizers_uids) {
      const u = await getUser(ouid);
      names[ouid] = u?.name || ouid.slice(0, 8);
    }
    organizerNames = names;

    // Compute standings from finished tournaments
    standingsError = false;
    const finishedTournaments = leagueTournaments.filter(t => t.state === "Finished" && t.standings?.length);
    if (finishedTournaments.length > 0) {
      try {
        const tournamentData = finishedTournaments.map(t => ({
          uid: t.uid,
          rank: t.rank || "",
          player_count: t.players?.length || 0,
          winner: t.winner || "",
          standings: (t.standings || []).map(s => ({
            user_uid: s.user_uid,
            gw: s.gw,
            vp: s.vp,
            tp: s.tp,
            finalist: s.finalist,
          })),
          finals: t.finals?.seating?.map(s => ({
            player_uid: s.player_uid,
            gw: s.result.gw,
            vp: s.result.vp,
            tp: s.result.tp,
          })) || [],
        }));
        const result = await computeLeagueStandings(l.standings_mode, tournamentData);
        // Resolve user names
        for (const entry of result) {
          const u = await getUser(entry.user_uid);
          (entry as StandingEntry).name = u?.name || entry.user_uid.slice(0, 8);
        }
        standings = result as StandingEntry[];
      } catch (e) {
        // Was console-only: standings silently rendered empty with no recourse.
        console.error("Failed to compute league standings:", e);
        standings = [];
        standingsError = true;
      }
    } else {
      standings = [];
    }

    loaded = true;
  }

  // Edit fields
  let editName = $state("");
  let editFormat = $state("");
  let editCountry = $state("");
  let editStart = $state("");
  let editFinish = $state("");
  let editDescription = $state("");
  let editStandingsMode = $state<LeagueStandingsMode>("RTP");

  function toDateInput(d: string | null): string {
    if (!d) return "";
    try { return new Date(d).toISOString().slice(0, 10); } catch { return ""; }
  }

  function startEdit() {
    if (!league) return;
    editName = league.name;
    editFormat = league.format || "";
    editCountry = league.country || "";
    editStart = toDateInput(league.start);
    editFinish = toDateInput(league.finish);
    editDescription = league.description;
    editStandingsMode = league.standings_mode;
    editing = true;
  }

  async function saveEdit() {
    if (!league) return;
    if (!editName.trim()) {
      error = m.tournament_new_error_name_required();
      return;
    }
    if (!editStart) {
      error = m.tournament_new_error_start_required();
      return;
    }
    error = null;
    try {
      await updateLeague(league.uid, {
        name: editName.trim(),
        format: editFormat || null,
        country: editCountry || null,
        start: editStart || null,
        finish: editFinish || null,
        description: editDescription,
        standings_mode: editStandingsMode,
      }, { suppressErrorToast: true });
      editing = false;
      await loadLeague();
    } catch (e) {
      error = toUserMessage(e, m.league_error_update());
    }
  }

  async function handleDelete() {
    if (!league || !confirm(m.league_delete_confirm())) return;
    try {
      await deleteLeagueApi(league.uid, { suppressErrorToast: true });
      goto("/leagues");
    } catch (e) {
      error = toUserMessage(e, m.league_error_delete());
    }
  }

  async function addChildLeague() {
    if (!addChildUid) return;
    error = null;
    try {
      await updateLeague(addChildUid, { parent_uid: uid }, { suppressErrorToast: true });
      addChildUid = "";
      await loadLeague();
    } catch (e) {
      error = toUserMessage(e, m.league_error_add_child());
    }
  }

  async function removeChildLeague(childUid: string) {
    error = null;
    try {
      await updateLeague(childUid, { parent_uid: null }, { suppressErrorToast: true });
      await loadLeague();
    } catch (e) {
      error = toUserMessage(e, m.league_error_remove_child());
    }
  }

  // Initial load
  $effect(() => {
    const _uid = uid;
    loadLeague();
  });

  // SSE sync listener
  $effect(() => {
    const handleSyncEvent = (event: { type: string }) => {
      if (event.type === "league" || event.type === "tournament" || event.type === "sync_complete") {
        loadLeague();
      }
    };
    syncManager.addEventListener(handleSyncEvent);
    return () => syncManager.removeEventListener(handleSyncEvent);
  });
</script>

<svelte:head>
  <title>{league?.name || m.league_title_fallback()} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    {#if !loaded}
      <div class="text-center py-12">
        <Loader2 class="mx-auto h-12 w-12 animate-spin text-ink-faint" />
      </div>
    {:else if !league}
      <div class="text-center py-12">
        <CircleAlert class="mx-auto h-12 w-12 text-ink-faint mb-4" />
        <h3 class="text-lg font-medium text-ink-strong mb-2">{m.league_not_found()}</h3>
        <a href="/leagues" class="text-link hover:text-link-soft">{m.league_back_to_list()}</a>
      </div>
    {:else}
      <!-- Header -->
      <div class="flex items-start justify-between mb-6">
        <div class="flex items-center gap-3">
          <a href="/leagues" class="text-ink-muted hover:text-ink-strong">
            <ArrowLeft class="w-5 h-5" />
          </a>
          <div>
            <h1 class="text-3xl font-semibold text-accent">{league.name}</h1>
            <div class="flex gap-2 mt-1 text-sm text-ink-muted">
              <span class="px-2 py-0.5 rounded text-xs font-medium {isActive() ? 'badge-success' : 'bg-surface-hover text-ink-muted'}">
                {isActive() ? m.league_status_active() : m.league_status_finished()}
              </span>
              <span>{standingsModeLabel(league.standings_mode)}</span>
              {#if league.format}
                <span>· {league.format}</span>
              {/if}
              {#if league.country}
                <span>· {getCountryFlag(league.country)} {countries[league.country]?.name || league.country}</span>
              {:else}
                <span>· {m.league_worldwide()}</span>
              {/if}
              {#if league.kind === "Meta-League"}
                <span class="px-2 py-0.5 rounded text-xs font-medium badge-amethyst">{m.league_meta_badge()}</span>
              {/if}
              {#if parentLeague}
                <a href="/leagues/{parentLeague.uid}" title={m.league_kind_meta()}
                   class="px-2 py-0.5 rounded text-xs font-medium badge-amethyst hover:opacity-80 transition-opacity">{parentLeague.name}</a>
              {/if}
            </div>
          </div>
        </div>
        {#if isOrganizer}
          <div class="flex gap-2">
            <Button variant="secondary" size="md" onclick={startEdit}>
              <Pencil class="w-4 h-4 inline -mt-0.5" /> {m.common_edit()}
            </Button>
            <Button variant="secondary" size="md" onclick={handleDelete}>
              <Trash2 class="w-4 h-4 inline -mt-0.5" /> {m.common_delete()}
            </Button>
          </div>
        {/if}
      </div>

      {#if error}
        <div class="bg-accent-soft/20 border border-accent-soft-border rounded-lg p-4 mb-6">
          <p class="text-link-soft">{error}</p>
        </div>
      {/if}

      <!-- Edit form -->
      {#if editing}
        <div class="bg-surface-card rounded-lg shadow p-6 border border-line mb-6 space-y-4">
          <!-- Name -->
          <div>
            <label for="edit-name" class="block text-sm text-ink-muted mb-1">{m.tfield_name_label()} <span class="text-link text-xs">({m.common_required()})</span></label>
            <input id="edit-name" type="text" bind:value={editName} required
              class="w-full px-3 py-2 text-sm border rounded-lg bg-surface-card text-ink-bright focus:outline-none {editName.trim() ? 'border-line-strong focus:border-line-strong' : 'border-accent-strong/50 focus:border-accent'}" />
          </div>

          <!-- Standings Mode & Format -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label for="edit-mode" class="block text-sm text-ink-muted mb-1">{m.league_standings_mode_label()}</label>
              <select id="edit-mode" bind:value={editStandingsMode}
                class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
                <option value="RTP">{m.league_standings_rtp_opt()}</option>
                <option value="Score">{m.league_standings_score_opt()}</option>
                <option value="GP">{m.league_standings_gp()}</option>
              </select>
            </div>
            <div>
              <label for="edit-format" class="block text-sm text-ink-muted mb-1">{m.tfield_format()}</label>
              <select id="edit-format" bind:value={editFormat}
                class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
                <option value="">{m.tfield_format_any()}</option>
                <option value="Standard">Standard</option>
                <option value="V5">V5</option>
                <option value="Limited">Limited</option>
              </select>
            </div>
          </div>

          <!-- Dates -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label for="edit-start" class="block text-sm text-ink-muted mb-1">{m.tfield_start()} <span class="text-link text-xs">({m.common_required()})</span></label>
              <input id="edit-start" type="date" bind:value={editStart} required
                class="w-full px-3 py-2 text-sm border rounded-lg bg-surface-card text-ink-bright focus:outline-none {editStart ? 'border-line-strong focus:border-line-strong' : 'border-accent-strong/50 focus:border-accent'}" />
            </div>
            <div>
              <label for="edit-finish" class="block text-sm text-ink-muted mb-1">{m.tfield_finish()}</label>
              <input id="edit-finish" type="date" bind:value={editFinish}
                class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright focus:border-line-strong focus:outline-none" />
              <p class="text-xs text-ink-faint mt-1">{m.league_finish_hint()}</p>
            </div>
          </div>

          <!-- Country -->
          <div>
            <label for="edit-country" class="block text-sm text-ink-muted mb-1">{m.common_country()}</label>
            <select id="edit-country" bind:value={editCountry}
              class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright">
              <option value="">{m.league_worldwide()}</option>
              {#each Object.entries(countries) as [code, c]}
                <option value={code}>{c.name} {getCountryFlag(code)}</option>
              {/each}
            </select>
          </div>


          <!-- Description -->
          <div>
            <label for="edit-desc" class="block text-sm text-ink-muted mb-1">{m.common_description()}</label>
            <textarea id="edit-desc" bind:value={editDescription} rows={10}
              class="w-full px-3 py-2 text-sm border border-line-strong rounded-lg bg-surface-card text-ink-bright focus:border-line-strong focus:outline-none resize-y"></textarea>
          </div>

          <div class="flex gap-3 justify-end">
            <button onclick={() => editing = false} class="px-4 py-2 text-sm text-ink-muted hover:text-ink-strong">{m.common_cancel()}</button>
            <Button variant="primary" size="lg" onclick={saveEdit} disabled={!editName.trim() || !editStart}>{m.common_save()}</Button>
          </div>
        </div>
      {/if}

      <!-- Info cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
        <div class="bg-surface-card rounded-lg shadow p-4 border border-line">
          <div class="text-sm text-ink-muted">{m.league_col_dates()}</div>
          <div class="text-ink-strong mt-1">{formatDate(league.start)} – {league.finish ? formatDate(league.finish) : m.league_ongoing()}</div>
        </div>
        <div class="bg-surface-card rounded-lg shadow p-4 border border-line">
          <div class="text-sm text-ink-muted mb-1">{m.league_organizers_label()}</div>
          {#if isOrganizer}
            <OrganizerManager
              organizerUids={league.organizers_uids}
              onadd={async (userUid) => { await addLeagueOrganizer(league!.uid, userUid); await loadLeague(); }}
              onremove={async (userUid) => { await removeLeagueOrganizer(league!.uid, userUid); await loadLeague(); }}
            />
          {:else}
            <div class="text-ink-strong">
              {#each league.organizers_uids as ouid}
                <span class="inline-block mr-2">{organizerNames[ouid] || "..."}</span>
              {/each}
            </div>
          {/if}
        </div>
      </div>

      {#if league.description}
        <FoldableDescription description={league.description} title={league.name} />
      {/if}

      <!-- Child leagues (meta-league) -->
      {#if league.kind === "Meta-League"}
        <div class="mb-6">
          <h2 class="text-xl font-medium text-ink-strong mb-3">{m.league_child_leagues()}</h2>
          {#if isOrganizer && orphanLeagues.length > 0}
            <div class="flex gap-2 mb-3">
              <select bind:value={addChildUid}
                class="flex-1 px-3 py-2 border border-line-strong rounded-lg bg-surface-card text-ink-bright text-sm">
                <option value="">{m.league_add_child_placeholder()}</option>
                {#each orphanLeagues as ol (ol.uid)}
                  <option value={ol.uid}>{ol.name}</option>
                {/each}
              </select>
              <Button variant="primary" size="lg" onclick={addChildLeague} disabled={!addChildUid}>
                <Plus class="w-4 h-4 inline -mt-0.5" /> {m.common_add()}
              </Button>
            </div>
          {/if}
          {#if childLeagues.length > 0}
            <div class="bg-surface-card rounded-lg shadow overflow-hidden border border-line">
              <div class="divide-y divide-line">
                {#each childLeagues as child (child.uid)}
                  <div class="flex items-center justify-between px-6 py-3 hover:bg-surface-muted/50 transition-colors">
                    <a href="/leagues/{child.uid}" class="flex-1">
                      <div class="font-semibold text-ink-strong">{child.name}</div>
                      {#if child.country}
                        <div class="text-sm text-ink-muted">{getCountryFlag(child.country)} {countries[child.country]?.name}</div>
                      {/if}
                    </a>
                    {#if isOrganizer}
                      <button onclick={() => removeChildLeague(child.uid)}
                        class="ml-2 p-1 text-ink-faint hover:text-link transition-colors" title={m.league_remove_child_title()}>
                        <X class="w-4 h-4" />
                      </button>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {:else}
            <div class="bg-surface-card rounded-lg shadow p-8 border border-line text-center">
              <p class="text-ink-muted">{m.league_no_children()}</p>
            </div>
          {/if}
        </div>
      {/if}

      <!-- Tournaments -->
      <div class="mb-6">
        <h2 class="text-xl font-medium text-ink-strong mb-3">
          {m.league_tournaments_heading({ count: leagueTournaments.length })}
        </h2>
        {#if leagueTournaments.length > 0}
          <div class="bg-surface-card rounded-lg shadow overflow-hidden border border-line">
            <div class="divide-y divide-line">
              {#each leagueTournaments as t (t.uid)}
                <a href="/tournaments/{t.uid}" class="block px-6 py-3 hover:bg-surface-muted/50 transition-colors">
                  <div class="flex items-center justify-between">
                    <div>
                      <div class="font-semibold text-ink-strong">{t.name}</div>
                      <div class="text-sm text-ink-muted">
                        {formatDate(t.start)}
                        {#if t.country}
                          · {getCountryFlag(t.country)}
                        {/if}
                        · {t.format}
                      </div>
                    </div>
                    <span class="px-2 py-1 rounded text-xs font-medium {t.state === 'Finished' ? 'bg-surface-hover text-ink-muted' : 'badge-success'}">
                      {translateTournamentState(t.state)}
                    </span>
                  </div>
                </a>
              {/each}
            </div>
          </div>
        {:else}
          <div class="bg-surface-card rounded-lg shadow p-8 border border-line text-center">
            <p class="text-ink-muted">{m.league_no_tournaments()}</p>
          </div>
        {/if}
      </div>

      <!-- Standings -->
      <div>
        <h2 class="text-xl font-medium text-ink-strong mb-3">{m.league_col_standings()}</h2>
        {#if standings.length > 0}
          <!-- Mobile card layout -->
          <div class="sm:hidden bg-surface-card rounded-lg shadow overflow-hidden border border-line divide-y divide-line">
            {#each standings as entry (entry.user_uid)}
              <div class="flex items-center gap-3 px-4 py-3">
                <span class="w-6 shrink-0 text-right text-sm font-medium text-ink-muted">{entry.rank}</span>
                <div class="min-w-0 flex-1">
                  <a href="/users/{entry.user_uid}" class="block truncate text-sm text-ink-strong hover:text-link">{entry.name}</a>
                  <div class="mt-0.5 flex items-center gap-3 text-xs text-ink-faint">
                    <span class="whitespace-nowrap">{formatScore(entry.gw, entry.vp, entry.tp)}</span>
                    <span class="inline-flex items-center gap-1"><Trophy class="w-3 h-3" />{entry.tournaments_count}</span>
                  </div>
                </div>
                {#if league?.standings_mode !== "Score"}
                  <div class="shrink-0 text-right">
                    <div class="text-sm font-semibold text-ink-strong leading-tight">{entry.points}</div>
                    <div class="text-[10px] uppercase tracking-wide text-ink-faint">{m.rankings_col_points()}</div>
                  </div>
                {/if}
              </div>
            {/each}
          </div>

          <!-- Desktop table -->
          <div class="hidden sm:block bg-surface-card rounded-lg shadow overflow-hidden border border-line">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-surface-muted text-ink border-b border-line-strong">
                    <th class="px-4 py-2 text-left w-12">{m.tournament_col_rank()}</th>
                    <th class="px-4 py-2 text-left">{m.tournament_col_player()}</th>
                    {#if league?.standings_mode !== "Score"}
                      <th class="px-4 py-2 text-right">{m.rankings_col_points()}</th>
                    {/if}
                    <th class="px-4 py-2 text-right whitespace-nowrap">{m.league_standings_score()}</th>
                    <th class="px-4 py-2 text-right">{m.league_standings_events()}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line">
                  {#each standings as entry (entry.user_uid)}
                    <tr class="hover:bg-surface-muted/50">
                      <td class="px-4 py-2 text-ink-muted font-medium">{entry.rank}</td>
                      <td class="px-4 py-2 text-ink-strong">
                        <a href="/users/{entry.user_uid}" class="hover:text-link">{entry.name}</a>
                      </td>
                      {#if league?.standings_mode !== "Score"}
                        <td class="px-4 py-2 text-right text-ink-strong font-medium">{entry.points}</td>
                      {/if}
                      <td class="px-4 py-2 text-right text-ink whitespace-nowrap">{formatScore(entry.gw, entry.vp, entry.tp)}</td>
                      <td class="px-4 py-2 text-right text-ink-muted">{entry.tournaments_count}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        {:else if standingsError}
          <div class="bg-surface-card rounded-lg shadow p-8 border border-accent-soft-border/50 text-center">
            <p class="text-link-soft mb-3">{m.league_standings_error()}</p>
            <Button variant="secondary" size="lg" onclick={loadLeague}>{m.common_retry()}</Button>
          </div>
        {:else}
          <div class="bg-surface-card rounded-lg shadow p-8 border border-line text-center">
            <p class="text-ink-muted">{m.league_standings_empty()}</p>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>
