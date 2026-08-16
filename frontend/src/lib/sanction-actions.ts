// Online: plain API calls (server applies DQ state + standings recompute). Offline (device-locked):
// Sanction objects write straight to IndexedDB and the client mirrors the server's DQ/standings side effects; VEKN-wide suspension/probation stay online-only.

import type { Sanction, Tournament } from './types';
import {
  createSanction as createSanctionApi,
  deleteSanctionApi,
  type CreateSanctionData,
} from './api';
import {
  addOfflineSanctionUid,
  getSanction,
  getSanctionsForTournament,
  getTournament,
  saveSanction,
  saveTournament,
} from './db';
import { updateStandings } from './engine';
import { getAuthState } from './stores/auth.svelte';
import { isOffline } from './stores/offline.svelte';
import { syncManager } from './sync';

/** Issue an event sanction; routes offline when the tournament is device-locked. */
export async function issueTournamentSanction(data: CreateSanctionData & { tournament_uid: string }): Promise<void> {
  if (!isOffline(data.tournament_uid)) {
    await createSanctionApi(data);
    return;
  }
  // Mirror the online 409: one active DQ per player per tournament.
  if (data.level === 'disqualification') {
    const existing = await getSanctionsForTournament(data.tournament_uid);
    const dup = existing.some(
      s => s.user_uid === data.user_uid && s.level === 'disqualification' && !s.lifted_at && !s.deleted_at
    );
    if (dup) {
      const { showToast } = await import('./stores/toast.svelte');
      const m = await import('./paraglide/messages.js');
      showToast({ type: 'error', message: m.sanction_dq_already_active() });
      throw new Error('duplicate active DQ');
    }
  }
  const now = new Date().toISOString();
  const sanction: Sanction = {
    uid: crypto.randomUUID(),
    modified: now,
    user_uid: data.user_uid,
    issued_by_uid: getAuthState().user?.uid ?? '',
    tournament_uid: data.tournament_uid,
    level: data.level,
    category: data.category,
    subcategory: data.subcategory ?? null,
    round_number: data.round_number ?? null,
    description: data.description,
    issued_at: now,
    expires_at: data.expires_at ?? null,
    lifted_at: null,
    lifted_by_uid: null,
  };
  await saveSanction(sanction);
  await addOfflineSanctionUid(data.tournament_uid, sanction.uid);
  await applyOfflineSanctionEffects(data.tournament_uid);
}

/** Delete (soft) an event sanction; routes offline when device-locked. */
export async function removeTournamentSanction(tournamentUid: string, sanctionUid: string): Promise<void> {
  if (!isOffline(tournamentUid)) {
    await deleteSanctionApi(sanctionUid);
    return;
  }
  const sanction = await getSanction(sanctionUid);
  if (!sanction) return;
  const now = new Date().toISOString();
  // Soft delete, like the server: go-online pushes the row with deleted_at set
  // (also covers deleting a sanction that was issued online before going offline).
  await saveSanction({ ...sanction, modified: now, deleted_at: now });
  await addOfflineSanctionUid(tournamentUid, sanctionUid);
  await applyOfflineSanctionEffects(tournamentUid);
}

/** Mirrors the server's sanction side effects on the device-locked tournament: DQ state flips
 * (backend _set_player_dq_state/_dq_restore_state) and ONE standings recompute via the shared Rust engine. */
async function applyOfflineSanctionEffects(tournamentUid: string): Promise<void> {
  const tournament = await getTournament(tournamentUid);
  if (!tournament) return;
  const sanctions = (await getSanctionsForTournament(tournamentUid)).filter(s => !s.deleted_at);

  const activeDqUids = new Set(
    sanctions.filter(s => s.level === 'disqualification' && !s.lifted_at).map(s => s.user_uid)
  );
  for (const player of tournament.players ?? []) {
    if (!player.user_uid) continue;
    if (activeDqUids.has(player.user_uid)) {
      player.state = 'Disqualified';
    } else if (player.state === 'Disqualified') {
      player.state = restoredState(tournament, player.user_uid);
    }
  }

  const updated = await updateStandings(tournament, sanctions);
  await saveTournament(updated);

  // No SSE offline: poke the same refresh hooks server events would.
  syncManager.notifyLocalMutation('sanction');
  syncManager.notifyLocalMutation('tournament');
}

/** Playable state after a DQ is removed — mirror of backend _dq_restore_state: Playing while seated
 * at a live table, Finished on a finished tournament, Checked-in otherwise. */
function restoredState(t: Tournament, userUid: string): 'Playing' | 'Finished' | 'Checked-in' {
  if (t.state === 'Finished') return 'Finished';
  const liveTables = (t.rounds ?? [])
    .flat()
    .filter(table => table.state !== 'Finished' && table.state !== 'Cancelled');
  if (t.finals && t.finals.state !== 'Finished') liveTables.push(t.finals);
  for (const table of liveTables) {
    if (table.seating.some(seat => seat.player_uid === userUid)) return 'Playing';
  }
  return 'Checked-in';
}
