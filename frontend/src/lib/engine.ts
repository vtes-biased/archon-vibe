/**
 * WASM Engine wrapper for offline-first tournament operations.
 *
 * This module provides a typed interface to the Rust engine compiled to WASM.
 * It enables identical business logic in browser (offline) and server (online).
 */

import type { Tournament, User } from './types';

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
 * Score an existing seating arrangement (no optimization).
 *
 * @param rounds Array of rounds, each round is array of tables, each table is array of player UIDs
 * @returns Score with rule violations, mean_vps, mean_transfers
 */
export async function scoreSeating(
  rounds: string[][][]
): Promise<{
  rules: number[];
  minimums: number[];
  mean_vps: number;
  mean_transfers: number;
}> {
  const engine = await initEngine();
  const resultJson = engine.scoreSeating(JSON.stringify({ rounds }));
  return JSON.parse(resultJson);
}

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
  | 'StartRound'
  | 'FinishRound'
  | 'CancelRound'
  | 'SwapSeats'
  | 'SeatPlayer'
  | 'UnseatPlayer'
  | 'AddTable'
  | 'RemoveTable'
  | 'UploadDeck'
  | 'UpdateDeck'
  | 'DeleteDeck'
  | 'SetScore'
  | 'Override'
  | 'Unoverride'
  | 'SetToss'
  | 'RandomToss'
  | 'StartFinals'
  | 'FinishFinals';

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
  deck?: { name: string; author: string; comments: string; cards: Record<string, number> };
  multideck?: boolean;
}

export interface ActorContext {
  uid: string;
  roles: string[];
  is_organizer: boolean;
}

/**
 * Process a tournament event using the WASM engine.
 *
 * @param tournament Current tournament state
 * @param event Event to process
 * @param actor User performing the action
 * @returns Updated tournament state
 */
export async function processTournamentEvent(
  tournament: Tournament,
  event: TournamentEvent,
  actor: ActorContext
): Promise<Tournament> {
  const engine = await initEngine();

  const tournamentJson = JSON.stringify(tournament);
  const eventJson = JSON.stringify(event);
  const actorJson = JSON.stringify(actor);

  const resultJson = engine.processTournamentEvent(tournamentJson, eventJson, actorJson);
  return JSON.parse(resultJson);
}

/**
 * Compute optimal seating for a tournament round.
 *
 * @param players Player UIDs for seating
 * @param roundsCount Total rounds to compute
 * @param previousRounds Previous rounds (for optimization)
 * @returns Computed rounds and score
 */
export async function computeSeating(
  players: string[],
  roundsCount: number,
  previousRounds?: string[][][]
): Promise<{
  rounds: string[][][];
  score: {
    rules: number[];
    mean_vps: number;
    mean_transfers: number;
  };
}> {
  const engine = await initEngine();

  const config = {
    players,
    rounds: roundsCount,
    previous_rounds: previousRounds ?? null,
  };

  const resultJson = engine.computeSeating(JSON.stringify(config));
  return JSON.parse(resultJson);
}

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
 * Build actor context from current user and tournament.
 */
export function buildActorContext(user: User | null, tournament: Tournament): ActorContext {
  if (!user) {
    return { uid: '', roles: [], is_organizer: false };
  }
  return {
    uid: user.uid,
    roles: user.roles || [],
    is_organizer: tournament.organizers_uids?.includes(user.uid) ?? false,
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

/**
 * Validate a deck synchronously (returns null if engine not initialized).
 */
export function validateDeckSync(
  deck: { cards: Record<string, number>; name?: string },
  cardsJson: string,
  format: string
): ValidationError[] | null {
  const engine = getEngineSync();
  if (!engine) return null;
  try {
    const deckJson = JSON.stringify({ name: deck.name || '', cards: deck.cards });
    const resultJson = engine.validateDeck(deckJson, cardsJson, format);
    return JSON.parse(resultJson);
  } catch {
    return null;
  }
}
