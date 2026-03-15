/**
 * WASM Engine wrapper for offline-first tournament operations.
 *
 * This module provides a typed interface to the Rust engine compiled to WASM.
 * It enables identical business logic in browser (offline) and server (online).
 */

import type { DeckObject, Sanction, Tournament, User } from './types';
import { getAllLeagues } from './db';

// Import types from the WASM package (path from frontend/src/lib/ to engine/pkg/)
type WasmEngine = import('../../../engine/pkg/archon_engine').WasmEngine;

let wasmEngine: WasmEngine | null = null;
let initPromise: Promise<void> | null = null;
let initError: Error | null = null;

/**
 * Initialize the WASM engine (lazy, called once).
 * Exported for use in layout initialization.
 */
export async function initEngine(): Promise<WasmEngine> {
  if (wasmEngine) return wasmEngine;
  if (initError) throw initError;

  if (!initPromise) {
    initPromise = (async () => {
      try {
        const wasm = await import('../../../engine/pkg/archon_engine');
        await wasm.default();
        wasmEngine = new wasm.WasmEngine();
      } catch (e) {
        initError = e instanceof Error ? e : new Error(String(e));
        throw initError;
      }
    })();
  }

  await initPromise;
  return wasmEngine!;
}

/**
 * Tournament event types for the Rust engine.
 */
/**
 * Score seating synchronously (returns null if engine not initialized).
 */
export function scoreSeatingSync(
  rounds: string[][][]
): { rules: number[]; minimums: number[]; mean_vps: number; mean_transfers: number } | null {
  const engine = getEngineSync();
  if (!engine) return null;
  try {
    const resultJson = engine.scoreSeating(JSON.stringify({ rounds }));
    return JSON.parse(resultJson);
  } catch {
    return null;
  }
}

export type TournamentEventType =
  | 'OpenRegistration'
  | 'CloseRegistration'
  | 'CancelRegistration'
  | 'ReopenRegistration'
  | 'ReopenTournament'
  | 'FinishTournament'
  | 'Register'
  | 'Unregister'
  | 'AddPlayer'
  | 'RemovePlayer'
  | 'DropOut'
  | 'CheckIn'
  | 'CheckInAll'
  | 'ResetCheckIn'
  | 'SetPaymentStatus'
  | 'MarkAllPaid'
  | 'StartRound'
  | 'FinishRound'
  | 'CancelRound'
  | 'SwapSeats'
  | 'AlterSeating'
  | 'SeatPlayer'
  | 'UnseatPlayer'
  | 'AddTable'
  | 'RemoveTable'
  | 'UpsertDeck'
  | 'DeleteDeck'
  | 'SetScore'
  | 'Override'
  | 'Unoverride'
  | 'SetToss'
  | 'RandomToss'
  | 'StartFinals'
  | 'FinishFinals'
  | 'RaffleDraw'
  | 'RaffleUndo'
  | 'RaffleClear'
  | 'UpdateConfig';

export interface TournamentEvent {
  type: TournamentEventType;
  user_uid?: string;
  player_uid?: string;
  round?: number;
  table?: number;
  table1?: number;
  seat1?: number;
  table2?: number;
  seat2?: number;
  seat?: number;
  scores?: Array<{
    player_uid: string;
    vp: number;
  }>;
  comment?: string;
  toss?: number;
  status?: string;
  seating?: string[][];
  vekn_id?: string;
  deck?: { name: string; author: string; comments: string; cards: Record<string, number> };
  multideck?: boolean;
  config?: Record<string, unknown>;
  // Raffle
  label?: string;
  pool?: string;
  exclude_drawn?: boolean;
  count?: number;
  seed?: number;
}

export interface ActorContext {
  uid: string;
  roles: string[];
  is_organizer: boolean;
  can_organize_league_uids: string[];
}

/**
 * Build sanctions payload for the Rust engine.
 * Extracts only the fields the engine needs from full Sanction objects.
 */
export function buildSanctionsPayload(sanctions: Sanction[]): string {
  return JSON.stringify(
    sanctions
      .filter(s => !s.deleted_at)
      .map(s => ({
        user_uid: s.user_uid,
        level: s.level,
        round_number: s.round_number ?? null,
        lifted_at: s.lifted_at ?? null,
        deleted_at: s.deleted_at ?? null,
      }))
  );
}

export interface DeckOp {
  op: 'upsert' | 'delete' | 'set_public';
  player_uid?: string;
  deck?: { name: string; author: string; comments: string; cards: Record<string, number>; round?: number | null; public?: boolean };
  deck_uid?: string;
  public?: boolean;
}

export interface EngineResult {
  tournament: Tournament;
  deckOps: DeckOp[];
}

/**
 * Build decks metadata JSON for the engine's decks parameter.
 */
function buildDecksPayload(decks: DeckObject[]): string {
  return JSON.stringify(
    decks.map(d => ({
      user_uid: d.user_uid,
      round: d.round,
      uid: d.uid,
    }))
  );
}

/**
 * Process a tournament event using the WASM engine.
 *
 * @param tournament Current tournament state
 * @param event Event to process
 * @param actor User performing the action
 * @param sanctions Sanctions for this tournament
 * @param decks Existing deck objects for this tournament
 * @returns Updated tournament state and deck operations
 */
export async function processTournamentEvent(
  tournament: Tournament,
  event: TournamentEvent,
  actor: ActorContext,
  sanctions: Sanction[] = [],
  decks: DeckObject[] = []
): Promise<EngineResult> {
  const engine = await initEngine();

  const tournamentJson = JSON.stringify(tournament);
  const eventJson = JSON.stringify(event);
  const actorJson = JSON.stringify(actor);
  const sanctionsJson = buildSanctionsPayload(sanctions);
  const decksJson = buildDecksPayload(decks);

  const resultJson = engine.processTournamentEvent(tournamentJson, eventJson, actorJson, sanctionsJson, decksJson);
  const result = JSON.parse(resultJson);
  return {
    tournament: result.tournament,
    deckOps: result.deck_ops || [],
  };
}

/**
 * Compute optimal seating for a tournament round.
 *
 * @param players Player UIDs for seating
 * @param roundsCount Total rounds to compute
 * @param previousRounds Previous rounds (for optimization)
 * @returns Computed rounds and score
 */
/**
 * Permission result from the engine.
 */
export interface PermissionResult {
  allowed: boolean;
  reason: string | null;
}

/**
 * Get the engine synchronously (returns null if not initialized).
 */
function getEngineSync(): WasmEngine | null {
  return wasmEngine;
}

// Type for user context in permission checks
type UserContext = { uid: string; roles: string[]; country?: string | null; vekn_id?: string | null };

/**
 * Check if actor can change a role on target user (sync version).
 * Returns {allowed: false, reason: null} if engine not initialized.
 */
export function canChangeRole(
  actor: UserContext,
  target: UserContext,
  role: string
): PermissionResult {
  const engine = getEngineSync();
  if (!engine) return { allowed: false, reason: null };

  const actorJson = JSON.stringify({
    uid: actor.uid,
    roles: actor.roles,
    country: actor.country,
  });
  const targetJson = JSON.stringify({
    uid: target.uid,
    roles: target.roles,
    country: target.country,
    vekn_id: target.vekn_id ?? null,
  });

  const resultJson = engine.canChangeRole(actorJson, targetJson, role);
  return JSON.parse(resultJson);
}

/**
 * Check if actor can manage VEKN IDs for target user (sync version).
 * Returns {allowed: false, reason: null} if engine not initialized.
 */
export function canManageVekn(
  actor: UserContext,
  target: UserContext
): PermissionResult {
  const engine = getEngineSync();
  if (!engine) return { allowed: false, reason: null };

  const actorJson = JSON.stringify({
    uid: actor.uid,
    roles: actor.roles,
    country: actor.country,
  });
  const targetJson = JSON.stringify({
    uid: target.uid,
    roles: target.roles,
    country: target.country,
  });

  const resultJson = engine.canManageVekn(actorJson, targetJson);
  return JSON.parse(resultJson);
}

/**
 * Check if actor can edit target user's profile (sync version).
 * Returns {allowed: false, reason: null} if engine not initialized.
 */
export function canEditUser(
  actor: UserContext,
  actorUid: string,
  targetUid: string,
  target: UserContext
): PermissionResult {
  const engine = getEngineSync();
  if (!engine) return { allowed: false, reason: null };

  const actorJson = JSON.stringify({
    uid: actor.uid,
    roles: actor.roles,
    country: actor.country,
  });
  const targetJson = JSON.stringify({
    uid: target.uid,
    roles: target.roles,
    country: target.country,
  });

  const resultJson = engine.canEditUser(actorJson, actorUid, targetUid, targetJson);
  return JSON.parse(resultJson);
}

/**
 * Compute rating points for a single tournament entry using the WASM engine.
 * Returns 0 if engine is not initialized.
 */
export function computeRatingPoints(
  vp: number,
  gw: number,
  finalistPosition: number,
  playerCount: number,
  rank: string
): number {
  const engine = getEngineSync();
  if (!engine) return 0;
  return engine.computeRatingPoints(vp, gw, finalistPosition, playerCount, rank);
}

/**
 * Compute league standings using the WASM engine.
 *
 * @param standingsMode "RTP" | "Score" | "GP"
 * @param tournaments Array of finished tournament data
 * @returns Array of standing entries sorted by ranking
 */
export async function computeLeagueStandings(
  standingsMode: string,
  tournaments: Array<{
    uid: string;
    rank: string;
    player_count: number;
    winner?: string;
    standings: Array<{ user_uid: string; gw: number; vp: number; tp: number; finalist: boolean }>;
    finals: Array<{ player_uid: string; gw: number; vp: number; tp: number }>;
  }>
): Promise<Array<{
  user_uid: string;
  gw: number;
  vp: number;
  tp: number;
  points?: number;
  rank: number;
  tournaments_count: number;
}>> {
  const engine = await initEngine();
  const config = { standings_mode: standingsMode, tournaments };
  const resultJson = engine.computeLeagueStandings(JSON.stringify(config));
  return JSON.parse(resultJson);
}

/**
 * Compute per-player seating issues synchronously.
 * Returns null if engine not initialized.
 */
export function computePlayerIssuesSync(
  rounds: string[][][]
): { rule: number; players: string[] }[] | null {
  const engine = getEngineSync();
  if (!engine) return null;
  try {
    const resultJson = engine.computePlayerIssues(JSON.stringify({ rounds }));
    return JSON.parse(resultJson);
  } catch (e) {
    console.error('computePlayerIssues failed:', e);
    return null;
  }
}

/**
 * Create a tournament using the WASM engine (for offline creation).
 */
export async function createTournamentWithEngine(
  config: Record<string, unknown>,
  actor: { uid: string; roles: string[]; is_organizer: boolean; can_organize_league_uids: string[] }
): Promise<Record<string, unknown>> {
  const engine = await initEngine();
  const result = engine.createTournament(JSON.stringify(config), JSON.stringify(actor));
  return JSON.parse(result);
}

/**
 * Build actor context from current user and tournament.
 */
export async function buildActorContext(
  user: User | null, tournament: Tournament, actionType?: string
): Promise<ActorContext> {
  if (!user) {
    return { uid: '', roles: [], is_organizer: false, can_organize_league_uids: [] };
  }
  const isIC = user.roles?.includes('IC');
  let canOrganize: string[] = [];
  if (actionType === 'UpdateConfig' && !isIC) {
    const leagues = await getAllLeagues();
    canOrganize = leagues
      .filter(l => (user.uid && l.organizers_uids?.includes(user.uid))
        || (user.roles?.includes('NC') && l.country === user.country))
      .map(l => l.uid);
  }
  return {
    uid: user.uid,
    roles: user.roles || [],
    is_organizer: !!(tournament.organizers_uids?.includes(user.uid) || isIC
      || (user.roles?.includes('NC')
        && user.country && tournament.country
        && user.country === tournament.country)),
    can_organize_league_uids: canOrganize,
  };
}

/**
 * Validation error from deck validation.
 */
export interface ValidationError {
  severity: 'error' | 'warning';
  message: string;
}

/**
 * Validate a deck against format rules using WASM engine.
 * Returns empty array if engine not initialized or on error.
 */
export async function validateDeck(
  deck: { cards: Record<string, number>; name?: string },
  format: string
): Promise<ValidationError[]> {
  const engine = await initEngine();
  try {
    // Get cards JSON from cards module
    const { getCardsJson } = await import('./cards');
    const cardsJson = await getCardsJson();
    if (!cardsJson) return [];

    const deckJson = JSON.stringify({ name: deck.name || '', cards: deck.cards });
    const resultJson = engine.validateDeck(deckJson, cardsJson, format);
    return JSON.parse(resultJson);
  } catch {
    return [];
  }
}

