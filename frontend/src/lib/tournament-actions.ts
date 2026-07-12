/**
 * Optimistic tournament-action engine.
 *
 * The mutation half of the client: applies a tournament event through the WASM
 * engine locally (optimistic IndexedDB write), then posts it to the server,
 * serialized per tournament and rolled back on rejection. Reads stay offline-first
 * (no GET); see rollbackTournamentAction. Pure HTTP transport lives in api.ts,
 * which this module builds on (one-way import — api.ts never imports back).
 */

import * as m from '$lib/paraglide/messages.js';
import type { Tournament, DeckObject } from '$lib/types';
import {
  getUser,
  getTournament,
  saveTournament,
  getSanctionsForTournament,
  getSanctionsForUser,
  getDecksByTournament,
  saveDeck,
  deleteDeck,
  addOfflineDeckUid,
} from './db';
import {
  processTournamentEvent,
  buildActorContext,
  type DeckOp,
  type TournamentEvent,
  type TournamentEventType,
} from './engine';
import { showToast } from '$lib/stores/toast.svelte';
import { getAuthState } from '$lib/stores/auth.svelte';
import { isOffline, scheduleSyncOffline } from '$lib/stores/offline.svelte';
import { apiRequest, ApiError, requireOnline, isOnline } from './api';
import { EngineError } from './error-codes';

/**
 * Per-tournament action queue to serialize server POSTs.
 * Prevents concurrent requests from racing on the same tournament.
 */
const actionQueues = new Map<string, Promise<void>>();

function enqueueServerAction(uid: string, fn: () => Promise<void>): void {
  const prev = actionQueues.get(uid) ?? Promise.resolve();
  const next = prev.then(fn, fn); // Run fn even if previous failed
  actionQueues.set(uid, next);
  next.finally(() => {
    if (actionQueues.get(uid) === next) {
      actionQueues.delete(uid);
    }
  });
}

/**
 * Pre-check: block barred players (suspension, league-wide DQ) before WASM optimistic path.
 * Mirrors backend _check_player_barred() logic.
 */
async function checkPlayerBarred(playerUid: string, tournament: Tournament): Promise<void> {
  const sanctions = await getSanctionsForUser(playerUid);
  const now = new Date();
  for (const s of sanctions) {
    if (s.deleted_at || s.lifted_at) continue;
    if (s.level === 'suspension' && (!s.expires_at || new Date(s.expires_at) > now)) {
      // Coded like the engine/backend twins so the offline path localizes too
      throw new EngineError(
        'tournament.player_suspended',
        {},
        'Player is suspended and cannot participate'
      );
    }
  }
  if (tournament.league_uid) {
    for (const s of sanctions) {
      if (s.deleted_at || s.lifted_at) continue;
      if (s.level === 'disqualification' && s.tournament_uid) {
        const dqTournament = await getTournament(s.tournament_uid);
        if (dqTournament && dqTournament.league_uid === tournament.league_uid) {
          throw new EngineError(
            'tournament.player_disqualified',
            {},
            'Player is disqualified from a league tournament and cannot participate'
          );
        }
      }
    }
  }
}

export async function tournamentAction(uid: string, action: TournamentEventType, data?: Record<string, unknown>): Promise<Tournament> {
  const event: Record<string, unknown> & { type: TournamentEventType } = { type: action, ...data };

  // Inject vekn_id for CheckIn auto-registration (WASM engine requires it)
  if (action === 'CheckIn' && data?.player_uid && !data.vekn_id) {
    const targetUser = await getUser(data.player_uid as string);
    if (targetUser?.vekn_id) {
      event.vekn_id = targetUser.vekn_id;
    }
  }

  // Try optimistic update via WASM engine
  const current = await getTournament(uid);
  if (current) {
    try {
      // Pre-check: block barred players before WASM optimistic path
      if (action === 'CheckIn' && data?.player_uid) {
        await checkPlayerBarred(data.player_uid as string, current);
      } else if ((action === 'Register' || action === 'AddPlayer') && data?.user_uid) {
        await checkPlayerBarred(data.user_uid as string, current);
      }
      const actor = await buildActorContext(getAuthState().user ?? null, current, action);
      // Combine tournament-scoped sanctions with user-level suspension/DQ
      // sanctions for all tournament players (needed for CheckInAll etc.)
      const sanctions = await getSanctionsForTournament(uid);
      const seenUids = new Set(sanctions.map(s => s.uid));
      const playerUids = new Set((current.players ?? []).map(p => p.user_uid));
      for (const puid of playerUids) {
        if (!puid) continue;
        for (const s of await getSanctionsForUser(puid)) {
          if (seenUids.has(s.uid) || s.deleted_at || s.lifted_at) continue;
          if (s.level === 'suspension' || s.level === 'disqualification') {
            sanctions.push(s);
            seenUids.add(s.uid);
          }
        }
      }
      const decks = await getDecksByTournament(uid);
      const result = await processTournamentEvent(current, event, actor, sanctions, decks);
      await saveTournament(result.tournament);

      // Handle deck side-effects in IDB
      const affectedDeckUids = await applyDeckOps(result.deckOps, uid, decks);

      // If tournament is in offline mode, track deck UIDs and skip server POST
      if (isOffline(uid)) {
        for (const deckUid of affectedDeckUids) {
          await addOfflineDeckUid(uid, deckUid);
        }
        scheduleSyncOffline(uid);
        return result.tournament;
      }

      // For StartRound: forward WASM-computed seating so the server uses the
      // same tables. Seating is now deterministic (seeded from tournament_uid +
      // round), so the server would compute the same result — forwarding is a
      // safety net guaranteeing agreement even if engine builds drift.
      let serverEvent: TournamentEvent = event;
      if (action === 'StartRound' && result.tournament.rounds &&
          result.tournament.rounds.length > (current.rounds?.length ?? 0)) {
        const newRound = result.tournament.rounds[result.tournament.rounds.length - 1]!;
        serverEvent = { ...event, seating: newRound.map(t => t.seating.map(s => s.player_uid)) };
      }

      // Queue server POST (serialized per tournament, prevents concurrent races)
      const hadDeckOps = (result.deckOps?.length ?? 0) > 0;
      // Snapshot our optimistic 'modified' stamps so rollback can tell our own
      // write apart from a foreign SSE update (co-judge action, server job) that
      // landed between the optimistic write and the rejection.
      const optimisticModified = result.tournament.modified;
      const optimisticDeckMods = hadDeckOps
        ? new Map((await getDecksByTournament(uid)).map((d) => [d.uid, d.modified]))
        : undefined;
      enqueueServerAction(uid, async () => {
        try {
          await apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
            method: 'POST',
            body: JSON.stringify(serverEvent),
          });
        } catch (e) {
          // A rejected action emits no SSE event, so the optimistic IDB write
          // won't self-correct — roll back to the pre-action state locally.
          console.error('Server rejected action, rolling back optimistic update:', e);
          await rollbackTournamentAction(uid, current, decks, hadDeckOps, optimisticModified, optimisticDeckMods);
          // apiRequest already toasts HTTP errors with the server's reason;
          // surface network-level failures (which don't toast) too.
          if (!(e instanceof ApiError)) {
            showToast({
              type: 'error',
              message: m.tournament_action_reverted(),
            });
          }
        }
      });

      return result.tournament;
    } catch (e) {
      // WASM rejected. When this tournament is offline (or the device is), there's
      // no server to defer to — surface the engine's actual reason (a typed
      // EngineError) instead of a misleading "requires online".
      // Otherwise fall through to server-only (covers genuine unknown-action drift).
      if (isOffline(uid) || !isOnline()) throw e;
    }
  }

  // Fallback: server-only. Every caller surfaces the error itself (inline message
  // or its own toast), so suppress apiRequest's duplicate toast here.
  requireOnline({ suppressErrorToast: true });
  return apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
    method: 'POST',
    body: JSON.stringify(event),
  }, { suppressErrorToast: true });
}

/**
 * Apply deck operations from engine result to IndexedDB.
 * In online mode, SSE will deliver authoritative state and overwrite.
 * Returns UIDs of affected decks (for offline tracking).
 */
async function applyDeckOps(deckOps: DeckOp[], tournamentUid: string, existingDecks: DeckObject[]): Promise<string[]> {
  const affectedUids: string[] = [];
  for (const op of deckOps) {
    if (op.op === 'upsert' && op.deck && op.player_uid) {
      const existing = existingDecks.find(
        d => d.user_uid === op.player_uid && d.round === (op.deck!.round ?? null)
      );
      const deckObj: DeckObject = {
        uid: existing?.uid || crypto.randomUUID(),
        modified: new Date().toISOString(),
        tournament_uid: tournamentUid,
        user_uid: op.player_uid,
        round: op.deck.round ?? null,
        name: op.deck.name || '',
        author: op.deck.author || '',
        comments: op.deck.comments || '',
        cards: op.deck.cards || {},
        // Mirror the backend: an absent attribution clears it (None), never keeps the old value
        attribution: op.deck.attribution ?? null,
        public: op.deck.public || false,
      };
      await saveDeck(deckObj);
      affectedUids.push(deckObj.uid);
    } else if (op.op === 'delete' && op.player_uid) {
      const offline = isOffline(tournamentUid);
      for (const d of existingDecks) {
        if (d.user_uid !== op.player_uid) continue;
        // Mirror the backend: a multideck delete tombstones only the matching round-deck
        if (op.multideck && op.deck_index != null && d.round !== op.deck_index) continue;
        if (offline) {
          // Soft-delete: go-online pushes offline_decks as upserts only, so the
          // deletion must travel as a tombstoned row — a local hard delete would
          // leave the server copy live and the deck would resurrect on resync.
          d.deleted_at = new Date().toISOString();
          d.modified = new Date().toISOString();
          await saveDeck(d);
          affectedUids.push(d.uid);
        } else {
          await deleteDeck(d.uid);
        }
      }
    } else if (op.op === 'set_public' && op.deck_uid) {
      const target = existingDecks.find(d => d.uid === op.deck_uid);
      if (target) {
        target.public = op.public ?? false;
        target.modified = new Date().toISOString();
        await saveDeck(target);
        affectedUids.push(target.uid);
      }
    }
  }
  return affectedUids;
}

/**
 * Roll back an optimistic tournament action that the server rejected.
 *
 * A rejected action emits no SSE event, so the optimistic mutations written to
 * IndexedDB would otherwise persist forever. We do NOT GET authoritative state
 * from the server — reads are offline-first (IndexedDB only). Server actions are
 * transactional (all-or-nothing), so on rejection the authoritative state equals
 * the pre-action state we already held in memory: restore it locally.
 *
 * Guard against clobbering a newer foreign write: a co-judge action or server
 * job whose SSE landed between our optimistic write and the rejection already
 * replaced our stored state (and its cursor advanced, so it won't be redelivered).
 * Since our rejected action emits no SSE, any change to the stored `modified`
 * means that foreign update is the correct post-rejection state — skip the restore.
 */
async function rollbackTournamentAction(
  uid: string,
  preActionTournament: Tournament,
  preActionDecks: DeckObject[],
  hadDeckOps: boolean,
  optimisticModified: string,
  optimisticDeckMods?: Map<string, string>,
): Promise<void> {
  try {
    const stored = await getTournament(uid);
    if (!stored || stored.modified === optimisticModified) {
      await saveTournament(preActionTournament);
    }
  } catch (e) {
    console.error('Failed to roll back optimistic tournament state:', e);
  }
  if (!hadDeckOps) return;
  try {
    const current = await getDecksByTournament(uid);
    const originalUids = new Set(preActionDecks.map((d) => d.uid));
    // Remove decks the optimistic op newly created — unless a foreign update
    // has since replaced our optimistic write for that deck.
    for (const d of current) {
      if (originalUids.has(d.uid)) continue;
      if (optimisticDeckMods?.get(d.uid) === d.modified) await deleteDeck(d.uid);
    }
    // Restore prior versions (also re-creates any optimistically deleted decks),
    // skipping decks a foreign update has since replaced.
    for (const d of preActionDecks) {
      const storedDeck = current.find((c) => c.uid === d.uid);
      if (!storedDeck || optimisticDeckMods?.get(d.uid) === storedDeck.modified) {
        await saveDeck(d);
      }
    }
  } catch (e) {
    console.error('Failed to roll back optimistic deck changes:', e);
  }
}

export async function setTableScore(
  tournamentUid: string,
  round: number,
  table: number,
  scores: Array<{ player_uid: string; vp: number }>
): Promise<Tournament> {
  return tournamentAction(tournamentUid, 'SetScore', { round, table, scores });
}
