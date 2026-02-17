<script lang="ts">
  import { page } from "$app/state";
  import { goto } from "$app/navigation";
  import { getLeague, getAllTournaments, getAllLeagues } from "$lib/db";
  import { updateLeague, deleteLeagueApi, addLeagueOrganizer, removeLeagueOrganizer } from "$lib/api";
  import { syncManager } from "$lib/sync";
  import { getCountries, getCountryFlag } from "$lib/geonames";
  import { getAuthState, hasAnyRole } from "$lib/stores/auth.svelte";
  import { getUser } from "$lib/db";
  import type { League, Tournament, LeagueStandingsMode } from "$lib/types";
  import { computeLeagueStandings } from "$lib/engine";
  import OrganizerManager from "$lib/components/OrganizerManager.svelte";
  import { Loader2, CircleAlert, ArrowLeft, Pencil, Trash2, Plus, X } from "lucide-svelte";

  const uid = $derived(page.params.uid);
  const countries = getCountries();
  const auth = $derived(getAuthState());

  let league = $state<League | null>(null);
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

  const isOrganizer = $derived(
    league && auth.user && (
      league.organizers_uids.includes(auth.user.uid) ||
      hasAnyRole("IC") ||
      (hasAnyRole("NC") && league.country === auth.user.country)
    )
  );

  function standingsModeLabel(mode: LeagueStandingsMode): string {
    switch (mode) {
      case "RTP": return "Rating Points";
      case "Score": return "GW/VP/TP";
      case "GP": return "Grand Prix";
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
        console.error("Failed to compute league standings:", e);
        standings = [];
      }
    } else {
      standings = [];
    }

    loaded = true;
  }

  // Edit fields
  let editName = $state("");
  let editDescription = $state("");
  let editStandingsMode = $state<LeagueStandingsMode>("RTP");
  let editAllowNoFinals = $state(false);

  function startEdit() {
    if (!league) return;
    editName = league.name;
    editDescription = league.description;
    editStandingsMode = league.standings_mode;
    editAllowNoFinals = league.allow_no_finals;
    editing = true;
  }

  async function saveEdit() {
    if (!league) return;
    error = null;
    try {
      await updateLeague(league.uid, {
        name: editName.trim(),
        description: editDescription,
        standings_mode: editStandingsMode,
        allow_no_finals: editAllowNoFinals,
      });
      editing = false;
      await loadLeague();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to update";
    }
  }

  async function handleDelete() {
    if (!league || !confirm("Delete this league? This cannot be undone.")) return;
    try {
      await deleteLeagueApi(league.uid);
      goto("/leagues");
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to delete";
    }
  }

  async function addChildLeague() {
    if (!addChildUid) return;
    error = null;
    try {
      await updateLeague(addChildUid, { parent_uid: uid });
      addChildUid = "";
      await loadLeague();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to add child league";
    }
  }

  async function removeChildLeague(childUid: string) {
    error = null;
    try {
      await updateLeague(childUid, { parent_uid: null });
      await loadLeague();
    } catch (e) {
      error = e instanceof Error ? e.message : "Failed to remove child league";
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
  <title>{league?.name || "League"} - Archon</title>
</svelte:head>

<div class="p-4 sm:p-8">
  <div class="max-w-6xl mx-auto">
    {#if !loaded}
      <div class="text-center py-12">
        <Loader2 class="mx-auto h-12 w-12 animate-spin text-ash-500" />
      </div>
    {:else if !league}
      <div class="text-center py-12">
        <CircleAlert class="mx-auto h-12 w-12 text-ash-600 mb-4" />
        <h3 class="text-lg font-medium text-bone-100 mb-2">League not found</h3>
        <a href="/leagues" class="text-crimson-400 hover:text-crimson-300">Back to leagues</a>
      </div>
    {:else}
      <!-- Header -->
      <div class="flex items-start justify-between mb-6">
        <div class="flex items-center gap-3">
          <a href="/leagues" class="text-ash-400 hover:text-bone-100">
            <ArrowLeft class="w-5 h-5" />
          </a>
          <div>
            <h1 class="text-3xl font-light text-crimson-500">{league.name}</h1>
            <div class="flex gap-2 mt-1 text-sm text-ash-400">
              <span class="px-2 py-0.5 rounded text-xs font-medium {isActive() ? 'badge-emerald' : 'bg-ash-800 text-ash-400'}">
                {isActive() ? "Active" : "Finished"}
              </span>
              <span>{standingsModeLabel(league.standings_mode)}</span>
              {#if league.format}
                <span>· {league.format}</span>
              {/if}
              {#if league.kind === "Meta-League"}
                <span class="px-2 py-0.5 rounded text-xs font-medium bg-violet-900/50 text-violet-300">Meta</span>
              {/if}
            </div>
          </div>
        </div>
        {#if isOrganizer}
          <div class="flex gap-2">
            <button onclick={startEdit} class="px-3 py-1.5 text-sm text-ash-300 hover:text-bone-100 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors">
              <Pencil class="w-4 h-4 inline -mt-0.5" /> Edit
            </button>
            <button onclick={handleDelete} class="px-3 py-1.5 text-sm text-crimson-400 hover:text-crimson-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors">
              <Trash2 class="w-4 h-4 inline -mt-0.5" /> Delete
            </button>
          </div>
        {/if}
      </div>

      {#if error}
        <div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4 mb-6">
          <p class="text-crimson-300">{error}</p>
        </div>
      {/if}

      <!-- Edit form -->
      {#if editing}
        <div class="bg-dusk-950 rounded-lg shadow p-6 border border-ash-800 mb-6 space-y-4">
          <div>
            <label for="edit-name" class="block text-sm font-medium text-ash-400 mb-1">Name</label>
            <input id="edit-name" type="text" bind:value={editName}
              class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200" />
          </div>
          <div>
            <label for="edit-mode" class="block text-sm font-medium text-ash-400 mb-1">Standings Mode</label>
            <select id="edit-mode" bind:value={editStandingsMode}
              class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200">
              <option value="RTP">Rating Points</option>
              <option value="Score">GW/VP/TP (prelims only)</option>
              <option value="GP">Grand Prix</option>
            </select>
          </div>
          <div>
            <label for="edit-desc" class="block text-sm font-medium text-ash-400 mb-1">Description</label>
            <textarea id="edit-desc" bind:value={editDescription} rows={3}
              class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 resize-y"></textarea>
          </div>
          <label class="flex items-center gap-2 text-sm text-ash-400 cursor-pointer">
            <input type="checkbox" bind:checked={editAllowNoFinals}
              class="rounded border-ash-600 bg-dusk-950 text-crimson-500" />
            Allow tournaments without finals
          </label>
          <div class="flex gap-3 justify-end">
            <button onclick={() => editing = false} class="px-4 py-2 text-sm text-ash-400 hover:text-bone-100">Cancel</button>
            <button onclick={saveEdit} class="px-4 py-2 text-sm font-medium btn-emerald rounded-lg">Save</button>
          </div>
        </div>
      {/if}

      <!-- Info cards -->
      <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div class="bg-dusk-950 rounded-lg shadow p-4 border border-ash-800">
          <div class="text-sm text-ash-400">Dates</div>
          <div class="text-bone-100 mt-1">{formatDate(league.start)} – {league.finish ? formatDate(league.finish) : "ongoing"}</div>
        </div>
        <div class="bg-dusk-950 rounded-lg shadow p-4 border border-ash-800">
          <div class="text-sm text-ash-400">Country</div>
          <div class="text-bone-100 mt-1">
            {#if league.country}
              {getCountryFlag(league.country)} {countries[league.country]?.name || league.country}
            {:else}
              Worldwide
            {/if}
          </div>
        </div>
        <div class="bg-dusk-950 rounded-lg shadow p-4 border border-ash-800">
          {#if isOrganizer}
            <OrganizerManager
              organizerUids={league.organizers_uids}
              onadd={async (userUid) => { await addLeagueOrganizer(league!.uid, userUid); await loadLeague(); }}
              onremove={async (userUid) => { await removeLeagueOrganizer(league!.uid, userUid); await loadLeague(); }}
            />
          {:else}
            <div class="text-sm text-ash-400">Organizers</div>
            <div class="text-bone-100 mt-1">
              {#each league.organizers_uids as ouid}
                <span class="inline-block mr-2">{organizerNames[ouid] || "..."}</span>
              {/each}
            </div>
          {/if}
        </div>
      </div>

      {#if league.description}
        <div class="bg-dusk-950 rounded-lg shadow p-4 border border-ash-800 mb-6">
          <p class="text-ash-300 whitespace-pre-wrap">{league.description}</p>
        </div>
      {/if}

      <!-- Child leagues (meta-league) -->
      {#if league.kind === "Meta-League"}
        <div class="mb-6">
          <h2 class="text-xl font-medium text-bone-100 mb-3">Child Leagues</h2>
          {#if isOrganizer && orphanLeagues.length > 0}
            <div class="flex gap-2 mb-3">
              <select bind:value={addChildUid}
                class="flex-1 px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 text-sm">
                <option value="">Select a league to add...</option>
                {#each orphanLeagues as ol (ol.uid)}
                  <option value={ol.uid}>{ol.name}</option>
                {/each}
              </select>
              <button onclick={addChildLeague} disabled={!addChildUid}
                class="px-3 py-2 text-sm font-medium btn-emerald rounded-lg disabled:opacity-50">
                <Plus class="w-4 h-4 inline -mt-0.5" /> Add
              </button>
            </div>
          {/if}
          {#if childLeagues.length > 0}
            <div class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800">
              <div class="divide-y divide-ash-800">
                {#each childLeagues as child (child.uid)}
                  <div class="flex items-center justify-between px-6 py-3 hover:bg-ash-900/50 transition-colors">
                    <a href="/leagues/{child.uid}" class="flex-1">
                      <div class="font-semibold text-bone-100">{child.name}</div>
                      {#if child.country}
                        <div class="text-sm text-ash-400">{getCountryFlag(child.country)} {countries[child.country]?.name}</div>
                      {/if}
                    </a>
                    {#if isOrganizer}
                      <button onclick={() => removeChildLeague(child.uid)}
                        class="ml-2 p-1 text-ash-500 hover:text-crimson-400 transition-colors" title="Remove from meta-league">
                        <X class="w-4 h-4" />
                      </button>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {:else}
            <div class="bg-dusk-950 rounded-lg shadow p-8 border border-ash-800 text-center">
              <p class="text-ash-400">No child leagues yet.</p>
            </div>
          {/if}
        </div>
      {/if}

      <!-- Tournaments -->
      <div class="mb-6">
        <h2 class="text-xl font-medium text-bone-100 mb-3">
          Tournaments ({leagueTournaments.length})
        </h2>
        {#if leagueTournaments.length > 0}
          <div class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800">
            <div class="divide-y divide-ash-800">
              {#each leagueTournaments as t (t.uid)}
                <a href="/tournaments/{t.uid}" class="block px-6 py-3 hover:bg-ash-900/50 transition-colors">
                  <div class="flex items-center justify-between">
                    <div>
                      <div class="font-semibold text-bone-100">{t.name}</div>
                      <div class="text-sm text-ash-400">
                        {formatDate(t.start)}
                        {#if t.country}
                          · {getCountryFlag(t.country)}
                        {/if}
                        · {t.format}
                      </div>
                    </div>
                    <span class="px-2 py-1 rounded text-xs font-medium {t.state === 'Finished' ? 'bg-ash-800 text-ash-400' : 'badge-emerald'}">
                      {t.state}
                    </span>
                  </div>
                </a>
              {/each}
            </div>
          </div>
        {:else}
          <div class="bg-dusk-950 rounded-lg shadow p-8 border border-ash-800 text-center">
            <p class="text-ash-400">No tournaments in this league yet.</p>
          </div>
        {/if}
      </div>

      <!-- Standings -->
      <div>
        <h2 class="text-xl font-medium text-bone-100 mb-3">Standings</h2>
        {#if standings.length > 0}
          <div class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800">
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-ash-900 text-ash-300 border-b border-ash-700">
                    <th class="px-4 py-2 text-left w-12">#</th>
                    <th class="px-4 py-2 text-left">Player</th>
                    {#if league?.standings_mode !== "Score"}
                      <th class="px-4 py-2 text-right">Points</th>
                    {/if}
                    <th class="px-4 py-2 text-right">GW</th>
                    <th class="px-4 py-2 text-right">VP</th>
                    <th class="px-4 py-2 text-right">TP</th>
                    <th class="px-4 py-2 text-right">Events</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-ash-800">
                  {#each standings as entry (entry.user_uid)}
                    <tr class="hover:bg-ash-900/50">
                      <td class="px-4 py-2 text-ash-400 font-medium">{entry.rank}</td>
                      <td class="px-4 py-2 text-bone-100">
                        <a href="/users/{entry.user_uid}" class="hover:text-crimson-400">{entry.name}</a>
                      </td>
                      {#if league?.standings_mode !== "Score"}
                        <td class="px-4 py-2 text-right text-bone-100 font-medium">{entry.points}</td>
                      {/if}
                      <td class="px-4 py-2 text-right text-ash-300">{entry.gw}</td>
                      <td class="px-4 py-2 text-right text-ash-300">{entry.vp}</td>
                      <td class="px-4 py-2 text-right text-ash-300">{entry.tp}</td>
                      <td class="px-4 py-2 text-right text-ash-400">{entry.tournaments_count}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        {:else}
          <div class="bg-dusk-950 rounded-lg shadow p-8 border border-ash-800 text-center">
            <p class="text-ash-400">Standings will appear when tournaments finish.</p>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</div>
