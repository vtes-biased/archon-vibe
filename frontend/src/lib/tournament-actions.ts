/** Pure HTTP transport lives in api.ts, which this module builds on one-way. */

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
  getPendingActions,
  getAllPendingActions,
  appendPendingAction,
  removePendingActions,
  type PendingAction,
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
import { syncManager } from './sync';
import { EngineError } from './error-codes';

/** Serializes server POSTs per tournament so concurrent requests can't race. */
const actionQueues = new Map<string, Promise<unknown>>();

function enqueueServerAction<T>(uid: string, fn: () => Promise<T>): Promise<T> {
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

/** One release per tournament holding an unconfirmed action, claimed at module load. Whichever
 * comes first decides the replay: the catch-up, or a console tap on that same tournament. */
const replayGates = new Map<string, () => void>();
let caughtUp = false;

function markCaughtUp(): void {
  caughtUp = true;
  for (const release of replayGates.values()) release();
  replayGates.clear();
}

syncManager.addEventListener((event) => {
  if (event.type === 'sync_complete') markCaughtUp();
});

/** Claims a queue slot per pending tournament at module load, before any console tap can enqueue
 * behind it: an action posted ahead of the replay would reach the server out of order. */
const outboxSeeded = (async () => {
  let outbox: Map<string, PendingAction[]>;
  try {
    outbox = await getAllPendingActions();
  } catch (e) {
    console.error('Failed to read the action outbox:', e);
    return;
  }
  for (const [uid, entries] of outbox) {
    // Only what already existed at launch. An entry appended later belongs to a POST some tab
    // still has in flight, and replaying it would be the second send of the same action.
    const claimed = new Set(entries.map((e) => e.id));
    const gate = new Promise<void>((resolve) => replayGates.set(uid, resolve));
    void enqueueServerAction(uid, () => replayPendingActions(uid, claimed, gate)).catch(() => {});
  }
  // Re-checked after the gates exist: a sync_complete during the read above found an empty map.
  if (caughtUp || syncManager.isSynced) markCaughtUp();
})();

async function replayPendingActions(uid: string, claimed: Set<string>, gate: Promise<void>): Promise<void> {
  await gate;
  await navigator.locks.request(`outbox:${uid}`, async () => {
    // Re-read under the lock: the owning tab removes its entry as its POST settles, so one that
    // survived to here has no live sender left.
    const pending = (await getPendingActions(uid)).filter((e) => claimed.has(e.id));
    if (pending.length === 0) return;
    const drop = (from: number) => removePendingActions(uid, pending.slice(from).map((e) => e.id));

    if (pending[0]!.user !== (getAuthState().user?.uid ?? '')) {
      await drop(0);
      return;
    }

    const stored = caughtUp ? await getTournament(uid) : undefined;
    if (!stored || stored.modified !== pending[0]!.modified) {
      await drop(0);
      showToast({ type: 'warning', message: m.tournament_action_unconfirmed() });
      return;
    }

    for (let i = 0; i < pending.length; i++) {
      const entry = pending[i]!;
      try {
        await apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
          method: 'POST',
          body: JSON.stringify(entry.event),
        });
      } catch (e) {
        console.error('Server rejected replayed action, rolling back optimistic update:', e);
        // Newest first: each entry's snapshot precedes the next one's optimistic write, so
        // unwinding forward would leave the later entries' deck writes standing.
        for (let j = pending.length - 1; j >= i; j--) await rollbackTournamentAction(uid, pending[j]!);
        await drop(i);
        if (!(e instanceof ApiError)) {
          showToast({ type: 'error', message: m.tournament_action_reverted() });
        }
        return;
      }
      await removePendingActions(uid, [entry.id]);
    }
  });
}

/** Blocks suspended players before the WASM optimistic path.
 * Mirrors backend _check_player_barred(). */
async function checkPlayerBarred(playerUid: string): Promise<void> {
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
}

export async function tournamentAction(uid: string, action: TournamentEventType, data?: Record<string, unknown>): Promise<Tournament> {
  await outboxSeeded;
  replayGates.get(uid)?.();
  replayGates.delete(uid);

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
    let awaitedServer = false;
    try {
      if (action === 'CheckIn' && data?.player_uid) {
        await checkPlayerBarred(data.player_uid as string);
      } else if ((action === 'Register' || action === 'AddPlayer') && data?.user_uid) {
        await checkPlayerBarred(data.user_uid as string);
      }
      const actor = await buildActorContext(getAuthState().user ?? null, current, action);
      // This tournament's own sanctions plus the players' VEKN suspensions
      // (needed for CheckInAll etc.) — the twin of backend _build_sanctions_json.
      const sanctions = await getSanctionsForTournament(uid);
      const seenUids = new Set(sanctions.map(s => s.uid));
      const playerUids = new Set((current.players ?? []).map(p => p.user_uid));
      for (const puid of playerUids) {
        if (!puid) continue;
        for (const s of await getSanctionsForUser(puid)) {
          if (seenUids.has(s.uid) || s.deleted_at || s.lifted_at) continue;
          if (s.level === 'suspension') {
            sanctions.push(s);
            seenUids.add(s.uid);
          }
        }
      }
      const decks = await getDecksByTournament(uid);
      const result = await processTournamentEvent(current, event, actor, sanctions, decks);

      if (!actor.is_organizer) {
        awaitedServer = true;
        const granted = await enqueueServerAction(uid, () =>
          apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
            method: 'POST',
            body: JSON.stringify(event),
          }, { suppressErrorToast: true }));
        // Re-read: a deck uid an SSE frame wrote during the round-trip must not be overwritten.
        await applyDeckOps(result.deckOps, uid, await getDecksByTournament(uid));
        return granted;
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
      const entry: PendingAction = {
        id: crypto.randomUUID(),
        user: getAuthState().user?.uid ?? '',
        event: serverEvent,
        modified: result.tournament.modified,
        tournament: current,
        decks: hadDeckOps ? decks : undefined,
        deckMods: hadDeckOps
          ? Object.fromEntries((await getDecksByTournament(uid)).map((d) => [d.uid, d.modified]))
          : undefined,
      };
      await appendPendingAction(uid, entry);
      enqueueServerAction(uid, () => navigator.locks.request(`outbox:${uid}`, async () => {
        try {
          await apiRequest<Tournament>(`/api/tournaments/${uid}/action`, {
            method: 'POST',
            body: JSON.stringify(entry.event),
          });
        } catch (e) {
          // A rejected action emits no SSE event, so the optimistic IDB write
          // won't self-correct — roll back to the pre-action state locally.
          console.error('Server rejected action, rolling back optimistic update:', e);
          await rollbackTournamentAction(uid, entry);
          // apiRequest already toasts HTTP errors with the server's reason;
          // surface network-level failures (which don't toast) too.
          if (!(e instanceof ApiError)) {
            showToast({
              type: 'error',
              message: m.tournament_action_reverted(),
            });
          }
        }
        // After the rollback, never before: an entry dropped first leaves the optimistic write
        // standing with nothing left to correct it.
        await removePendingActions(uid, [entry.id]);
      }));

      return result.tournament;
    } catch (e) {
      // WASM rejected. When this tournament (or the device) is offline, there's no server to defer to —
      // surface the engine's actual reason. Otherwise fall through to server-only (covers unknown-action drift),
      // never past `awaitedServer`, which would post the action twice.
      if (awaitedServer || isOffline(uid) || !isOnline()) throw e;
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
async function rollbackTournamentAction(uid: string, entry: PendingAction): Promise<void> {
  try {
    const stored = await getTournament(uid);
    if (!stored || stored.modified === entry.modified) {
      await saveTournament(entry.tournament);
    }
  } catch (e) {
    console.error('Failed to roll back optimistic tournament state:', e);
  }
  if (!entry.decks) return;
  try {
    const current = await getDecksByTournament(uid);
    const originalUids = new Set(entry.decks.map((d) => d.uid));
    // Remove decks the optimistic op newly created — unless a foreign update
    // has since replaced our optimistic write for that deck.
    for (const d of current) {
      if (originalUids.has(d.uid)) continue;
      if (entry.deckMods?.[d.uid] === d.modified) await deleteDeck(d.uid);
    }
    // Restore prior versions (also re-creates any optimistically deleted decks),
    // skipping decks a foreign update has since replaced.
    for (const d of entry.decks) {
      const storedDeck = current.find((c) => c.uid === d.uid);
      if (!storedDeck || entry.deckMods?.[d.uid] === storedDeck.modified) {
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
