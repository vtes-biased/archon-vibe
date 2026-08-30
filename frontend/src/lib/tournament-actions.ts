/** Tournament mutation. A device that can own the tournament applies the event through WASM locally,
 * then posts to the server (serialized per tournament) and rolls back on rejection; a player's device
 * awaits the server first. Pure HTTP transport lives in api.ts, which this module builds on one-way. */

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

/** Serializes server POSTs per tournament so concurrent requests can't race. */
const actionQueues = new Map<string, Promise<void>>();

function enqueueServerAction(uid: string, fn: () => Promise<void>): Promise<void> {
  const prev = actionQueues.get(uid) ?? Promise.resolve();
  const next = prev.then(fn, fn); // Run fn even if previous failed
  actionQueues.set(uid, next);
  // Cleanup rides a swallowed branch: the awaiting caller owns the rejection, and a
  // second unhandled chain off `next` would surface it again as an unhandled rejection.
  next.catch(() => {}).finally(() => {
    if (actionQueues.get(uid) === next) {
      actionQueues.delete(uid);
    }
  });
  return next;
}

/** Blocks barred players (suspension, league-wide DQ) before the WASM optimistic path.
 * Mirrors backend _check_player_barred(). */
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

  const current = await getTournament(uid);
  if (current) {
    try {
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

      // A device that cannot own the tournament can never mutate offline, so the engine call
      // above was a pre-flight: nothing is written or reported until the server grants it, and
      // the rejection reaches the surface that fired the action rather than a detached toast.
      if (!actor.is_organizer) {
        await enqueueServerAction(uid, async () => {
          await apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
            method: 'POST',
            body: JSON.stringify(event),
          }, { suppressErrorToast: true });
        });
        await saveTournament(result.tournament);
        await applyDeckOps(result.deckOps, uid, decks);
        return result.tournament;
      }

      await saveTournament(result.tournament);

      const affectedDeckUids = await applyDeckOps(result.deckOps, uid, decks);

      if (isOffline(uid)) {
        for (const deckUid of affectedDeckUids) {
          await addOfflineDeckUid(uid, deckUid);
        }
        scheduleSyncOffline(uid);
        return result.tournament;
      }

      // For StartRound: forward WASM-computed seating so the server uses the same tables. Seating is
      // deterministic (seeded from tournament_uid+round) so this is a safety net, not strictly required.
      let serverEvent: TournamentEvent = event;
      if (action === 'StartRound' && result.tournament.rounds &&
          result.tournament.rounds.length > (current.rounds?.length ?? 0)) {
        const newRound = result.tournament.rounds[result.tournament.rounds.length - 1]!;
        serverEvent = { ...event, seating: newRound.map(t => t.seating.map(s => s.player_uid)) };
      }

      const hadDeckOps = (result.deckOps?.length ?? 0) > 0;
      // Snapshot our optimistic 'modified' stamps so rollback can tell our own write apart from a
      // foreign SSE update (co-judge action, server job) landed between the optimistic write and the rejection.
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
      // WASM rejected. When this tournament (or the device) is offline, there's no server to defer to —
      // surface the engine's actual reason. Otherwise fall through to server-only (covers unknown-action drift).
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

/** In online mode, SSE delivers authoritative state and overwrites. Returns affected deck UIDs for
 * offline tracking. */
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
        if (op.multideck && d.round !== (op.deck_index ?? null)) continue;
        if (offline) {
          // Soft-delete: go-online pushes offline_decks as upserts only, so the deletion must travel as a
          // tombstoned row — a local hard delete would leave the server copy live and resurrect the deck on resync.
          d.deleted_at = new Date().toISOString();
          d.modified = new Date().toISOString();
          await saveDeck(d);
          affectedUids.push(d.uid);
        } else {
          await deleteDeck(d.uid);
        }
      }
    } else if (op.op === 'set_round' && op.deck_uid) {
      const target = existingDecks.find(d => d.uid === op.deck_uid);
      if (target) {
        target.round = op.round ?? null;
        target.modified = new Date().toISOString();
        await saveDeck(target);
        affectedUids.push(target.uid);
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

/** A rejected action emits no SSE event, so optimistic IDB writes would persist forever; server actions
 * are transactional, so the pre-action state IS the post-rejection state — restore it, unless a foreign SSE write (co-judge, server job) already replaced our stored `modified` first. */
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
