/**
 * WASM Engine wrapper for offline-first tournament operations.
 *
 * This module provides a typed interface to the Rust engine compiled to WASM.
 * It enables identical business logic in browser (offline) and server (online).
 */

import type { DeckObject, Sanction, SanctionCategory, SanctionLevel, SanctionSubcategory, Tournament, User } from './types';
import { getAllLeagues } from './db';
import { engineReady, markEngineReady, markEngineLoadFailed } from './stores/engine-ready.svelte';
import { engineErrorFromThrown } from './error-codes';

// Import types from the WASM package (path from frontend/src/lib/ to engine/pkg/)
type WasmEngine = import('../../../engine/pkg/archon_engine').WasmEngine;

// Content-hashed .wasm asset URL, resolved by Vite. We hand it to the
// wasm-bindgen init explicitly (see initEngine) rather than relying on the glue's
// default — `new URL('archon_engine_bg.wasm', import.meta.url)` resolves relative
// to the *chunk* it's bundled into (/_app/immutable/chunks/), doubling the path
// to /_app/immutable/chunks/_app/immutable/assets/…wasm → 404 (engine never loads).
// Vite emits this as a base-relative string ("./_app/immutable/assets/…wasm").
import wasmUrl from '../../../engine/pkg/archon_engine_bg.wasm?url';

/**
 * Run a raw WASM engine call. wasm-bindgen throws the `Err` arm as a JS string
 * primitive — since that string is the engine's `{code,params,message}`
 * wire JSON — so re-throw it as a typed `EngineError` for localized display.
 * The catch wraps the call itself, NOT the `JSON.parse` of its success result.
 */
export function callEngine<T>(fn: () => T): T {
  try {
    return fn();
  } catch (e) {
    throw engineErrorFromThrown(e) ?? e;
  }
}

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
        // Root the base-relative `wasmUrl` against the origin. The glue feeds it
        // to fetch(), which would otherwise resolve "./_app/…" against the current
        // page — fine on "/", but 404 on deep routes (e.g. /tournaments/<uid>).
        // paths.base is empty, so origin-rooted "/_app/…" matches every other asset.
        await wasm.default({ module_or_path: new URL(wasmUrl, location.origin).href });
        wasmEngine = new wasm.WasmEngine();
        markEngineReady();
      } catch (e) {
        initError = e instanceof Error ? e : new Error(String(e));
        markEngineLoadFailed(); // reactive signal so the UI can surface the degraded state
        throw initError;
      }
    })();
  }

  await initPromise;
  return wasmEngine!;
}

/**
 * Score seating synchronously (returns null if engine not initialized).
 */
export function scoreSeatingSync(
  rounds: string[][][]
): { rules: number[]; minimums: number[]; mean_vps: number; mean_transfers: number } | null {
  const engine = getEngineReactive();
  if (!engine) return null;
  try {
    const resultJson = callEngine(() => engine.scoreSeating(JSON.stringify({ rounds })));
    return JSON.parse(resultJson);
  } catch {
    return null;
  }
}

// Preview memo: template {@const}s call previewScoresSync once per rendered
// seat, so key on object identity (tournament/sanctions are replaced wholesale
// on every update) and serialize the tournament only once per table per update.
let previewCache: {
  tournament: Tournament;
  sanctions: Sanction[] | undefined;
  results: Map<string, { gw: number[]; tp: number[] } | null>;
} | null = null;

/**
 * Preview GW/TP for one table exactly as the engine's SetScore computes them —
 * including standings-adjustment penalties — so the live preview can never
 * drift from persisted results. `round === tournament.rounds.length` previews
 * the finals table (`table` ignored). Returns null if the engine isn't
 * initialized (callers fall back to stored results).
 */
export function previewScoresSync(
  tournament: Tournament,
  sanctions: Sanction[] | undefined,
  round: number,
  table: number,
  vps: number[],
): { gw: number[]; tp: number[] } | null {
  const engine = getEngineReactive();
  if (!engine) return null;
  if (!previewCache || previewCache.tournament !== tournament || previewCache.sanctions !== sanctions) {
    previewCache = { tournament, sanctions, results: new Map() };
  }
  const key = `${round}:${table}:${vps.join(',')}`;
  const hit = previewCache.results.get(key);
  if (hit !== undefined) return hit;
  let result: { gw: number[]; tp: number[] } | null = null;
  try {
    const config = JSON.stringify({
      tournament,
      sanctions: JSON.parse(buildSanctionsPayload(sanctions ?? [])),
      round,
      table,
      vps,
    });
    result = JSON.parse(callEngine(() => engine.previewScores(config)));
  } catch {
    result = null;
  }
  previewCache.results.set(key, result);
  return result;
}

/** Why a table's VPs won't validate. `seats` are 0-based seating indices. */
export type VpIssue = {
  code:
    | 'invalid_table_size'
    | 'incomplete'
    | 'excessive_total'
    | 'redirected_vp'
    | 'impossible_oust_order'
    | 'missing_half_vp';
  seats: number[];
};

/**
 * Explain why a table won't close, using the same check that decides its state
 * server-side. Returns null when the VPs are scorable (or the engine isn't up —
 * callers then say nothing rather than guessing).
 */
export function checkTableVpsSync(vps: number[]): VpIssue | null {
  const engine = getEngineReactive();
  if (!engine) return null;
  try {
    return JSON.parse(callEngine(() => engine.checkTableVps(JSON.stringify({ vps }))));
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
  | 'CheckOut'
  | 'CheckInAll'
  | 'ResetCheckIn'
  | 'SetPaymentStatus'
  | 'MarkAllPaid'
  | 'SetNonCompeting'
  | 'StartRound'
  | 'SelfOrganizeRound'
  | 'FinishRound'
  | 'CancelRound'
  | 'RestoreRound'
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
  | 'CancelFinals'
  | 'RaffleDraw'
  | 'ReportPromos'
  | 'RaffleUndo'
  | 'RaffleClear'
  | 'UpdateConfig';

export interface TournamentEvent {
  type: TournamentEventType;
  user_uid?: string;
  player_uid?: string;
  display_name?: string; // Register/AddPlayer/CheckIn: offline name-only player
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
  non_competing?: boolean;
  seating?: string[][];
  player_uids?: string[]; // SelfOrganizeRound: the chosen pod
  vekn_id?: string;
  deck?: { name: string; author: string; comments: string; cards: Record<string, number>; round?: number; attribution?: string | null };
  deck_index?: number | null;
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
  now?: string; // request timestamp (ISO-8601 UTC); resolves suspension expiry in the engine
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
        // Canonicalize to match actor.now's toISOString() format so the engine's
        // lexicographic expires_at vs now compare is chronological (suspension expiry).
        expires_at: s.expires_at ? new Date(s.expires_at).toISOString() : null,
      }))
  );
}

export interface DeckOp {
  op: 'upsert' | 'delete' | 'set_public';
  player_uid?: string;
  deck?: { name: string; author: string; comments: string; cards: Record<string, number>; round?: number | null; public?: boolean; attribution?: string | null };
  deck_uid?: string;
  deck_index?: number | null; // delete: multideck round-deck selector
  multideck?: boolean;
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

  const resultJson = callEngine(() =>
    engine.processTournamentEvent(tournamentJson, eventJson, actorJson, sanctionsJson, decksJson)
  );
  const result = JSON.parse(resultJson);
  return {
    tournament: result.tournament,
    deckOps: result.deck_ops || [],
  };
}

/**
 * Recompute standings from current sanctions. Offline sanction management:
 * the device-locked client mirrors the server's PyEngine.update_standings —
 * same shared Rust, fed from IDB sanctions instead of Postgres.
 */
export async function updateStandings(
  tournament: Tournament,
  sanctions: Sanction[]
): Promise<Tournament> {
  const engine = await initEngine();
  const tournamentJson = JSON.stringify(tournament);
  const sanctionsJson = buildSanctionsPayload(sanctions);
  const resultJson = callEngine(() => engine.updateStandings(tournamentJson, sanctionsJson));
  return JSON.parse(resultJson) as Tournament;
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

/**
 * Subscribe the current reaction to WASM readiness and return the engine.
 *
 * `wasmEngine` is a plain module `let` Svelte can't track, so a sync wrapper
 * called inside a `$derived`/render that only read `getEngineSync()` would
 * compute once cold (engine null → fallback) and never recover. Reading
 * `engineReady()` here registers a reactive dependency, so every sync wrapper
 * below re-runs once the engine lands. Harmless outside a reaction (returns the
 * flag, registers nothing). Async wrappers don't need this — they `await
 * initEngine()` and so always resolve hot.
 */
function getEngineReactive(): WasmEngine | null {
  engineReady();
  return getEngineSync();
}

// Judges-Guide penalty tables, owned by engine/src/sanctions.rs.
export interface SanctionReference {
  subcategoriesByCategory: Record<SanctionCategory, SanctionSubcategory[]>;
  baselinePenalties: Record<SanctionSubcategory, SanctionLevel>;
  escalationSequence: SanctionLevel[];
}

let sanctionReference: SanctionReference | null = null;

/**
 * Judges-Guide penalty reference from the engine (sync; null until the
 * engine is initialized). Static data — parsed once, then cached.
 */
export function getSanctionReference(): SanctionReference | null {
  if (sanctionReference) return sanctionReference;
  const engine = getEngineReactive();
  if (!engine) return null;
  const raw = JSON.parse(callEngine(() => engine.sanctionReference()));
  sanctionReference = {
    subcategoriesByCategory: Object.fromEntries(
      raw.categories.map((c: any) => [c.key, c.subcategories.map((s: any) => s.key)])
    ) as Record<SanctionCategory, SanctionSubcategory[]>,
    baselinePenalties: Object.fromEntries(
      raw.categories.flatMap((c: any) => c.subcategories.map((s: any) => [s.key, s.baseline]))
    ) as Record<SanctionSubcategory, SanctionLevel>,
    escalationSequence: raw.escalation,
  };
  return sanctionReference;
}

// Type for user context in permission checks
type UserContext = { uid: string; roles?: string[] | null; country?: string | null; vekn_id?: string | null };
type Resource = { country?: string | null; organizers_uids?: string[] };

/**
 * Ask the engine whether `actor` holds `capability` in this context.
 *
 * The single authorization entry point: every gate below is one call of this,
 * naming a capability from the engine's table (engine/src/permissions.rs).
 * Fill only what the capability reads — an absent field matches no grant.
 *
 * Fail-closed: denies with a null reason until the WASM engine is loaded, so a
 * cold page never shows a control the backend would refuse. Callers rendering a
 * deny reason should treat null as "not yet known".
 */
function checkPermission(
  capability: string,
  actor: UserContext | null,
  context: { target?: UserContext; targetCountry?: string | null; resource?: Resource } = {}
): PermissionResult {
  if (!actor) return { allowed: false, reason: null };
  const engine = getEngineReactive();
  if (!engine) return { allowed: false, reason: null };

  const { target, resource } = context;
  const request: Record<string, unknown> = {
    actor: { roles: actor.roles ?? [], country: actor.country ?? null, vekn_id: actor.vekn_id ?? null },
    actor_uid: actor.uid,
    target_uid: target?.uid ?? null,
    target_country: target ? target.country ?? null : context.targetCountry ?? null,
  };
  if (resource) {
    request.resource = {
      country: resource.country ?? null,
      organizers_uids: resource.organizers_uids ?? [],
    };
    // For a resource-scoped capability, "same country" means the resource's
    // — an NC is an implicit organizer of their country's tournaments.
    if (!target && context.targetCountry === undefined) {
      request.target_country = resource.country ?? null;
    }
  }
  return JSON.parse(callEngine(() => engine.checkPermission(capability, JSON.stringify(request))));
}

/** Grant or revoke one role — see the engine's appointment matrix. */
export function canChangeRole(
  actor: UserContext,
  target: UserContext,
  role: string
): PermissionResult {
  const engine = getEngineReactive();
  if (!engine) return { allowed: false, reason: null };

  const actorJson = JSON.stringify({ roles: actor.roles ?? [], country: actor.country });
  const targetJson = JSON.stringify({
    roles: target.roles ?? [],
    country: target.country,
    vekn_id: target.vekn_id ?? null,
  });

  const resultJson = callEngine(() => engine.canChangeRole(actorJson, targetJson, role));
  return JSON.parse(resultJson);
}

/**
 * Move a member between countries. For an official target this takes the
 * authority that could change their highest official role.
 */
export function canChangeCountry(actor: UserContext, target: UserContext): PermissionResult {
  const engine = getEngineReactive();
  if (!engine) return { allowed: false, reason: null };

  const actorJson = JSON.stringify({ roles: actor.roles ?? [], country: actor.country });
  const targetJson = JSON.stringify({
    roles: target.roles ?? [],
    country: target.country,
    vekn_id: target.vekn_id ?? null,
  });

  const resultJson = callEngine(() => engine.canChangeCountry(actorJson, targetJson));
  return JSON.parse(resultJson);
}

/**
 * Whether a member holds the official badge (IC/NC/Prince).
 *
 * Identity, not authority — badges, quotas and warnings only. Never gate on it:
 * ask for the capability the control actually needs.
 */
export function isOfficial(user: UserContext | null): boolean {
  if (!user) return false;
  const engine = getEngineReactive();
  if (!engine) return false;
  return callEngine(() => engine.isOfficial(JSON.stringify({ roles: user.roles ?? [] })));
}

/**
 * Bring someone into VEKN: mint a member record, or issue a VEKN ID to an
 * account that has none. One authority — both allocate an ID and stamp
 * coopted_by. Deliberately cross-country.
 */
export function canSponsorMember(actor: UserContext | null): PermissionResult {
  return checkPermission('sponsor_member', actor);
}

/** Edit a user's profile fields. */
export function canEditUser(actor: UserContext | null, target: UserContext): PermissionResult {
  return checkPermission('edit_member_profile', actor, { target });
}

/** Link or force-abandon a target's VEKN ID. */
export function canManageVekn(actor: UserContext | null, target: UserContext): PermissionResult {
  return checkPermission('manage_vekn', actor, { target });
}

/** Merge one account into another. */
export function canMergeAccounts(actor: UserContext | null): PermissionResult {
  return checkPermission('merge_accounts', actor);
}

/** Set or clear a member's deceased status. */
export function canMarkDeceased(
  actor: UserContext | null,
  targetCountry: string | null
): PermissionResult {
  return checkPermission('mark_deceased', actor, { targetCountry });
}

/** Soft-delete a member. The target-must-be-VEKN-less rule is enforced by the route. */
export function canDeleteMember(actor: UserContext | null): PermissionResult {
  return checkPermission('delete_member', actor);
}

/** Hide or clear a member's community link (self-moderation included). */
export function canModerateLink(actor: UserContext | null, target: UserContext): PermissionResult {
  return checkPermission('moderate_link', actor, { target });
}

/** Promote a link to the national listing. */
export function canPromoteLinkNational(
  actor: UserContext | null,
  target: UserContext
): PermissionResult {
  return checkPermission('promote_link_national', actor, { target });
}

/** Promote a link to the global listing. */
export function canPromoteLinkGlobal(actor: UserContext | null): PermissionResult {
  return checkPermission('promote_link_global', actor);
}

/** Create a tournament. */
export function canCreateTournament(actor: UserContext | null): PermissionResult {
  return checkPermission('create_tournament', actor);
}

/** Create and delete leagues. */
export function canManageLeagues(actor: UserContext | null): PermissionResult {
  return checkPermission('manage_leagues', actor);
}

/**
 * Take a tournament offline, or force-take its lock: run the event AND hold the
 * member-creation power the lock carries. Fail-closed until WASM is loaded.
 */
export function canTakeTournamentOffline(
  user: UserContext | null,
  tournament: Resource
): boolean {
  if (!user) return false;
  const engine = getEngineReactive();
  if (!engine) return false;
  const actorJson = JSON.stringify({ roles: user.roles ?? [], country: user.country ?? null });
  const tournamentJson = JSON.stringify({
    country: tournament.country ?? null,
    organizers_uids: tournament.organizers_uids ?? [],
  });
  return JSON.parse(
    callEngine(() => engine.canTakeTournamentOffline(actorJson, user.uid, tournamentJson))
  ).allowed;
}

/** Break an offline device lock. */
export function canForceUnlockTournament(actor: UserContext | null): PermissionResult {
  return checkPermission('force_unlock_tournament', actor);
}

/** Create, edit and allocate promos. */
export function canManagePromos(actor: UserContext | null): PermissionResult {
  return checkPermission('manage_promos', actor);
}

/** See the whole promo ledger rather than one's own entries. */
export function canViewFullPromoLedger(actor: UserContext | null): PermissionResult {
  return checkPermission('view_full_promo_ledger', actor);
}

/** Register and revoke OAuth clients. */
export function canManageOauthClients(actor: UserContext | null): PermissionResult {
  return checkPermission('manage_oauth_clients', actor);
}

/** Trigger and inspect the VEKN/TWDA sync jobs. */
export function canRunAdminSync(actor: UserContext | null): PermissionResult {
  return checkPermission('run_admin_sync', actor);
}

/** Issue an organizer-level sanction at a tournament. */
export function canIssueTournamentSanction(
  actor: UserContext | null,
  tournament: Resource
): PermissionResult {
  return checkPermission('issue_tournament_sanction', actor, { resource: tournament });
}

/** Issue a suspension or probation. */
export function canIssueRestrictedSanction(actor: UserContext | null): PermissionResult {
  return checkPermission('issue_restricted_sanction', actor);
}

/**
 * Run a tournament: an explicit organizer, or implicitly IC/NC.
 * Fail-closed (false) until the WASM engine is loaded — never default-allow.
 */
export function isOrganizer(
  user: UserContext | null,
  tournament: Resource
): boolean {
  return checkPermission('organize_tournament', user, { resource: tournament }).allowed;
}

/**
 * Edit a league. Fail-closed (false) until the WASM engine is loaded.
 */
export function canEditLeague(
  user: UserContext | null,
  league: Resource
): boolean {
  return checkPermission('edit_league', user, { resource: league }).allowed;
}

/**
 * Check if a user can attach a tournament to a league (sync): league editors,
 * or a same-country Prince when the league is open to them.
 * Fail-closed (false) until the WASM engine is loaded.
 */
export function canLinkTournamentToLeague(
  user: { uid: string; roles?: string[]; country?: string | null } | null,
  league: { country?: string | null; organizers_uids?: string[]; open_to_country_princes?: boolean }
): boolean {
  if (!user) return false;
  const engine = getEngineReactive();
  if (!engine) return false;
  const actorJson = JSON.stringify({ uid: user.uid, roles: user.roles ?? [], country: user.country });
  const leagueJson = JSON.stringify({
    country: league.country ?? null,
    organizers_uids: league.organizers_uids ?? [],
    open_to_country_princes: league.open_to_country_princes ?? false,
  });
  return JSON.parse(callEngine(() => engine.canLinkTournamentToLeague(actorJson, user.uid, leagueJson))).allowed;
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
  const engine = getEngineReactive();
  if (!engine) return 0;
  return engine.computeRatingPoints(vp, gw, finalistPosition, playerCount, rank);
}

/**
 * A player's SA-adjusted (vp, gw), finals included — the same aggregation backend
 * ratings.py stores. Null while the engine isn't loaded.
 */
export function computeRatingVpGw(
  tournamentJson: string,
  sanctionsJson: string,
  userUid: string
): [vp: number, gw: number] | null {
  const engine = getEngineReactive();
  if (!engine) return null;
  // Null rather than a fabricated 0 the caller would render as a real score.
  const [vp, gw] = engine.computeRatingVpGw(tournamentJson, sanctionsJson, userUid);
  return vp === undefined || gw === undefined ? null : [vp, gw];
}

/**
 * Ranking-eligibility gate (VEKN rules 3.1/3.1.6), single-sourced in the engine
 * alongside backend ratings.py's inclusion filter.
 * Returns "eligible" | "open_rounds" | "few_players" | "no_final",
 * or null while the engine isn't loaded yet.
 */
export function rankingEligibility(tournament: unknown): string | null {
  const engine = getEngineReactive();
  if (!engine) return null;
  return engine.rankingEligibility(JSON.stringify(tournament));
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
    standings: Array<{ user_uid: string; gw: number; vp: number; tp: number; finalist: boolean; disqualified?: boolean; non_competing?: boolean }>;
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
  const resultJson = callEngine(() => engine.computeLeagueStandings(JSON.stringify(config)));
  return JSON.parse(resultJson);
}

/**
 * Reorder preliminary standings into final placement (winner first, other
 * finalists tied for 2nd per VEKN §3.7.5, then non-finalists), tagging each with
 * a 1-based `rank`. Single source of truth shared with league scoring.
 *
 * Synchronous (used inside `$derived`); returns [] if the engine isn't yet
 * initialized. `standings` must be pre-sorted descending by preliminary score;
 * "did a final happen?" is read from the `finalist` flags.
 */
export function computeFinalStandings(
  standings: Array<{ user_uid: string; gw: number; vp: number; tp: number; toss?: number; finalist?: boolean; disqualified?: boolean; non_competing?: boolean }>,
  winner: string
): Array<{ user_uid: string; gw: number; vp: number; tp: number; toss: number; finalist: boolean; rank: number; disqualified?: boolean; non_competing?: boolean }> {
  const engine = getEngineReactive();
  if (!engine) return [];
  const resultJson = callEngine(() => engine.computeFinalStandings(JSON.stringify({ standings, winner })));
  return JSON.parse(resultJson);
}

/**
 * Compute per-player seating issues synchronously.
 * Returns null if engine not initialized.
 */
export function computePlayerIssuesSync(
  rounds: string[][][]
): { rule: number; players: string[] }[] | null {
  const engine = getEngineReactive();
  if (!engine) return null;
  try {
    const resultJson = callEngine(() => engine.computePlayerIssues(JSON.stringify({ rounds })));
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
  const result = callEngine(() => engine.createTournament(JSON.stringify(config), JSON.stringify(actor)));
  return JSON.parse(result);
}

/**
 * Build actor context from current user and tournament.
 */
export async function buildActorContext(
  user: User | null, tournament: Tournament, actionType?: string
): Promise<ActorContext> {
  if (!user) {
    return { uid: '', roles: [], is_organizer: false, can_organize_league_uids: [], now: new Date().toISOString() };
  }
  // This context feeds engine action validation, so the checks must be
  // authoritative — ensure WASM is loaded rather than fail-closed.
  await initEngine();
  const isIC = user.roles?.includes('IC');
  let canOrganize: string[] = [];
  // IC bypasses the per-league check in the engine, so it skips this filter
  // entirely (empty list signals "no restriction") — keep the !isIC guard.
  if (actionType === 'UpdateConfig' && !isIC) {
    const leagues = await getAllLeagues();
    canOrganize = leagues.filter(l => canLinkTournamentToLeague(user, l)).map(l => l.uid);
  }
  return {
    uid: user.uid,
    roles: user.roles || [],
    is_organizer: isOrganizer(user, tournament),
    can_organize_league_uids: canOrganize,
    now: new Date().toISOString(),
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
 * Returns null when validation is unavailable (cards not hydrated yet, engine
 * failure) — the scoreSeatingSync convention. [] means genuinely valid, so
 * callers must not read null as a pass.
 */
export async function validateDeck(
  deck: { cards: Record<string, number>; name?: string },
  format: string
): Promise<ValidationError[] | null> {
  const engine = await initEngine();
  try {
    // Get cards JSON from cards module
    const { getCardsJson } = await import('./cards');
    const cardsJson = await getCardsJson();
    if (!cardsJson) return null;

    const deckJson = JSON.stringify({ name: deck.name || '', cards: deck.cards });
    const resultJson = callEngine(() => engine.validateDeck(deckJson, cardsJson, format));
    return JSON.parse(resultJson);
  } catch {
    return null;
  }
}

