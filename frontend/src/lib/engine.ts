import type { CommunityLinkType, DeckObject, LinkMedia, LinkPlacement, RafflePool, Sanction, SanctionCategory, SanctionLevel, SanctionSubcategory, Tournament, User } from './types';
import { getAllLeagues } from './db';
import { callEngine, getEngine, initEngine } from './engine-instance';

export function scoreSeatingSync(
  rounds: string[][][]
): { rules: number[]; minimums: number[]; mean_vps: number; mean_transfers: number } | null {
  const engine = getEngine();
  try {
    const resultJson = callEngine(() => engine.scoreSeating(JSON.stringify({ rounds })));
    return JSON.parse(resultJson);
  } catch {
    return null;
  }
}

// Keyed on tournament/sanctions object identity (both replaced wholesale each update), so repeated
// {@const} calls per rendered seat serialize the tournament once per table per update.
let previewCache: {
  tournament: Tournament;
  sanctions: Sanction[] | undefined;
  results: Map<string, { gw: number[]; tp: number[] } | null>;
} | null = null;

/** Computes GW/TP exactly as SetScore does, so the preview never drifts from persisted results.
 * `round === tournament.rounds.length` previews the finals table (`table` param ignored). */
export function previewScoresSync(
  tournament: Tournament,
  sanctions: Sanction[] | undefined,
  round: number,
  table: number,
  vps: number[],
): { gw: number[]; tp: number[] } | null {
  const engine = getEngine();
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
    | 'half_vp_mismatch';
  seats: number[];
};

/** Same check that decides a table's close-state server-side. Null means scorable. */
export function checkTableVpsSync(vps: number[]): VpIssue | null {
  return JSON.parse(callEngine(() => getEngine().checkTableVps(JSON.stringify({ vps }))));
}

/** Room-aware table label ("Main Hall 3"), or null when no room covers the index. */
export function tableLabel(
  tableRooms: { name: string; count: number }[] | undefined,
  tableIndex: number,
): string | null {
  return callEngine(() => getEngine().tableLabel(JSON.stringify(tableRooms ?? []), tableIndex)) ?? null;
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
  | 'UpdateConfig'
  | 'SetArchivalResults';

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
  label?: string;
  pool?: string;
  exclude_drawn?: boolean;
  count?: number;
  seed?: number;
  winner?: string; // SetArchivalResults
  players?: string[]; // SetArchivalResults: the known roster
  reported_player_count?: number; // SetArchivalResults
}

export interface ActorContext {
  uid: string;
  roles: string[];
  is_organizer: boolean;
  can_organize_league_uids: string[];
  now?: string; // request timestamp (ISO-8601 UTC); resolves suspension expiry in the engine
}

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

function buildDecksPayload(decks: DeckObject[]): string {
  return JSON.stringify(
    decks.map(d => ({
      user_uid: d.user_uid,
      round: d.round,
      uid: d.uid,
    }))
  );
}

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

/** Offline sanction management: the device-locked client mirrors the server's
 * PyEngine.update_standings — same shared Rust, fed from IDB sanctions instead of Postgres. */
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

export interface PermissionResult {
  allowed: boolean;
  reason: string | null;
}

// Judges-Guide penalty tables, owned by engine/src/sanctions.rs.
export interface SanctionReference {
  subcategoriesByCategory: Record<SanctionCategory, SanctionSubcategory[]>;
  baselinePenalties: Record<SanctionSubcategory, SanctionLevel>;
  escalationSequence: SanctionLevel[];
}

let sanctionReference: SanctionReference | null = null;

export function getSanctionReference(): SanctionReference {
  if (sanctionReference) return sanctionReference;
  const raw = JSON.parse(callEngine(() => getEngine().sanctionReference()));
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

export interface CommunityLinkReference {
  types: CommunityLinkType[];
  mediaKinds: LinkMedia[];
  placement: Record<CommunityLinkType, LinkPlacement>;
  media: Record<CommunityLinkType, LinkMedia | null>;
}

let communityLinkReference: CommunityLinkReference | null = null;

export function getCommunityLinkReference(): CommunityLinkReference {
  if (communityLinkReference) return communityLinkReference;
  const raw = JSON.parse(callEngine(() => getEngine().communityLinkReference()));
  communityLinkReference = {
    types: raw.types.map((t: any) => t.type),
    mediaKinds: raw.media_kinds,
    placement: Object.fromEntries(
      raw.types.map((t: any) => [t.type, t.placement])
    ) as Record<CommunityLinkType, LinkPlacement>,
    media: Object.fromEntries(raw.types.map((t: any) => [t.type, t.media])) as Record<
      CommunityLinkType,
      LinkMedia | null
    >,
  };
  return communityLinkReference;
}

let libraryTypeOrder: string[] | null = null;

export function getLibraryTypeOrder(): string[] {
  if (libraryTypeOrder) return libraryTypeOrder;
  libraryTypeOrder = JSON.parse(callEngine(() => getEngine().libraryTypeOrder()));
  return libraryTypeOrder!;
}

type UserContext = { uid: string; roles?: string[] | null; country?: string | null; vekn_id?: string | null };
type Resource = { country?: string | null; organizers_uids?: string[] };

/** Single authorization entry point: every capability check below is one call of this, naming a
 * capability from engine/src/permissions.rs. Fill only what the capability reads. */
function checkPermission(
  capability: string,
  actor: UserContext | null,
  context: { target?: UserContext; targetCountry?: string | null; resource?: Resource } = {}
): PermissionResult {
  if (!actor) return { allowed: false, reason: null };

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
  return JSON.parse(callEngine(() => getEngine().checkPermission(capability, JSON.stringify(request))));
}

export function canChangeRole(
  actor: UserContext,
  target: UserContext,
  role: string,
  // The NDA fact is not on User (never projected) — callers that can see it
  // pass it in; absent means false, which only bites when granting PT.
  targetHasNda = false
): PermissionResult {
  const actorJson = JSON.stringify({ roles: actor.roles ?? [], country: actor.country });
  const targetJson = JSON.stringify({
    roles: target.roles ?? [],
    country: target.country,
    vekn_id: target.vekn_id ?? null,
    has_nda: targetHasNda,
  });

  const resultJson = callEngine(() => getEngine().canChangeRole(actorJson, targetJson, role));
  return JSON.parse(resultJson);
}

/** For an official target this takes the authority that could change their highest official role. */
export function canChangeCountry(actor: UserContext, target: UserContext): PermissionResult {
  const actorJson = JSON.stringify({ roles: actor.roles ?? [], country: actor.country });
  const targetJson = JSON.stringify({
    roles: target.roles ?? [],
    country: target.country,
    vekn_id: target.vekn_id ?? null,
  });

  const resultJson = callEngine(() => getEngine().canChangeCountry(actorJson, targetJson));
  return JSON.parse(resultJson);
}

/** Identity, not authority — badges, quotas and warnings only. Never gate on this: ask for the
 * capability the control actually needs. */
export function isOfficial(user: UserContext | null): boolean {
  if (!user) return false;
  return callEngine(() => getEngine().isOfficial(JSON.stringify({ roles: user.roles ?? [] })));
}

/** Mints a member record or issues a VEKN ID to an existing account — one authority for both,
 * which also stamps `coopted_by`. Deliberately cross-country. */
export function canSponsorMember(actor: UserContext | null): PermissionResult {
  return checkPermission('sponsor_member', actor);
}

export function canEditUser(actor: UserContext | null, target: UserContext): PermissionResult {
  return checkPermission('edit_member_profile', actor, { target });
}

export function canManageVekn(actor: UserContext | null, target: UserContext): PermissionResult {
  return checkPermission('manage_vekn', actor, { target });
}

export function canMergeAccounts(actor: UserContext | null): PermissionResult {
  return checkPermission('merge_accounts', actor);
}

export function canMarkDeceased(
  actor: UserContext | null,
  targetCountry: string | null
): PermissionResult {
  return checkPermission('mark_deceased', actor, { targetCountry });
}

/** The target-must-be-VEKN-less rule is enforced by the route, not here. */
export function canDeleteMember(actor: UserContext | null): PermissionResult {
  return checkPermission('delete_member', actor);
}

/** Scoped to the country the link serves, which need not be its owner's. */
export function canModerateLink(
  actor: UserContext | null,
  linkCountry: string | null
): PermissionResult {
  return checkPermission('moderate_link', actor, { targetCountry: linkCountry });
}

export function canPromoteLinkNational(
  actor: UserContext | null,
  linkCountry: string | null
): PermissionResult {
  return checkPermission('promote_link_national', actor, { targetCountry: linkCountry });
}

export function canPromoteLinkGlobal(actor: UserContext | null): PermissionResult {
  return checkPermission('promote_link_global', actor);
}

export function canCreateTournament(actor: UserContext | null): PermissionResult {
  return checkPermission('create_tournament', actor);
}

export function canManageLeagues(actor: UserContext | null): PermissionResult {
  return checkPermission('manage_leagues', actor);
}

/** Governs both going offline and force-taking the lock: the event action AND the
 * member-creation power the lock carries share one capability check. */
export function canTakeTournamentOffline(
  user: UserContext | null,
  tournament: Resource
): boolean {
  if (!user) return false;
  const actorJson = JSON.stringify({ roles: user.roles ?? [], country: user.country ?? null });
  const tournamentJson = JSON.stringify({
    country: tournament.country ?? null,
    organizers_uids: tournament.organizers_uids ?? [],
  });
  return JSON.parse(
    callEngine(() => getEngine().canTakeTournamentOffline(actorJson, user.uid, tournamentJson))
  ).allowed;
}

export function canForceUnlockTournament(actor: UserContext | null): PermissionResult {
  return checkPermission('force_unlock_tournament', actor);
}

export function canManagePromos(actor: UserContext | null): PermissionResult {
  return checkPermission('manage_promos', actor);
}

export function canViewFullPromoLedger(actor: UserContext | null): PermissionResult {
  return checkPermission('view_full_promo_ledger', actor);
}

export function canManageOauthClients(actor: UserContext | null): PermissionResult {
  return checkPermission('manage_oauth_clients', actor);
}

export function canRunAdminSync(actor: UserContext | null): PermissionResult {
  return checkPermission('run_admin_sync', actor);
}

export function canIssueTournamentSanction(
  actor: UserContext | null,
  tournament: Resource
): PermissionResult {
  return checkPermission('issue_tournament_sanction', actor, { resource: tournament });
}

export function canIssueRestrictedSanction(actor: UserContext | null): PermissionResult {
  return checkPermission('issue_restricted_sanction', actor);
}

export function isOrganizer(
  user: UserContext | null,
  tournament: Resource
): boolean {
  return checkPermission('organize_tournament', user, { resource: tournament }).allowed;
}

export function canSetArchivalResults(user: UserContext | null): PermissionResult {
  return checkPermission('set_archival_results', user);
}

export function canManageNda(user: UserContext | null): PermissionResult {
  return checkPermission('manage_nda', user);
}

export function canEditLeague(
  user: UserContext | null,
  league: Resource
): boolean {
  return checkPermission('edit_league', user, { resource: league }).allowed;
}

/** League editors, or a same-country Prince when the league is `open_to_country_princes`. */
export function canLinkTournamentToLeague(
  user: { uid: string; roles?: string[]; country?: string | null } | null,
  league: { country?: string | null; organizers_uids?: string[]; open_to_country_princes?: boolean }
): boolean {
  if (!user) return false;
  const actorJson = JSON.stringify({ uid: user.uid, roles: user.roles ?? [], country: user.country });
  const leagueJson = JSON.stringify({
    country: league.country ?? null,
    organizers_uids: league.organizers_uids ?? [],
    open_to_country_princes: league.open_to_country_princes ?? false,
  });
  return JSON.parse(callEngine(() => getEngine().canLinkTournamentToLeague(actorJson, user.uid, leagueJson))).allowed;
}

export function computeRatingPoints(
  vp: number,
  gw: number,
  finalistPosition: number,
  playerCount: number,
  rank: string
): number {
  return getEngine().computeRatingPoints(vp, gw, finalistPosition, playerCount, rank);
}

/** A player's SA-adjusted (vp, gw), finals included — the same aggregation backend
 * ratings.py stores. */
export function computeRatingVpGw(
  tournamentJson: string,
  sanctionsJson: string,
  userUid: string
): [vp: number, gw: number] | null {
  // Null rather than a fabricated 0 the caller would render as a real score.
  const [vp, gw] = getEngine().computeRatingVpGw(tournamentJson, sanctionsJson, userUid);
  return vp === undefined || gw === undefined ? null : [vp, gw];
}

/** VEKN rules 3.1/3.1.6 ranking-eligibility gate, single-sourced with backend
 * ratings.py's inclusion filter. */
export function rankingEligibility(tournament: unknown): string | null {
  return getEngine().rankingEligibility(JSON.stringify(tournament));
}

/** How big the field was, for the coefficient and the win floors — distinct from
 * the played-player set the caller enumerates for membership. */
export function attestedPlayerCount(tournament: unknown): number {
  return getEngine().attestedPlayerCount(JSON.stringify(tournament));
}

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

/** `sanctions` must be this tournament's own: a DQ from another event is not one here,
 * and the payload carries no `tournament_uid` for the engine to filter on. */
export function displayStandings(
  tournament: Tournament,
  sanctions: Sanction[]
): Array<{ user_uid: string; gw: number; vp: number; tp: number; toss: number; rank: number; finalist: boolean; finalist_position: number; disqualified: boolean; non_competing: boolean; no_show: boolean; finals?: { gw: number; vp: number; tp: number } }> {
  const config = JSON.stringify({ tournament, sanctions: JSON.parse(buildSanctionsPayload(sanctions)) });
  return JSON.parse(callEngine(() => getEngine().displayStandings(config)));
}

/** Takes pre-serialized JSON: the picker asks once per pool and the tournament is
 * serialized once for all of them. */
export function rafflePool(
  tournamentJson: string,
  sanctionsJson: string,
  pool: RafflePool,
  excludeDrawn: boolean
): string[] {
  return JSON.parse(
    callEngine(() => getEngine().rafflePool(tournamentJson, sanctionsJson, pool, excludeDrawn))
  );
}

export function finalsQualification(
  tournament: Tournament | null,
  standings: Array<{ user_uid: string; gw: number; vp: number; tp: number; toss?: number; disqualified?: boolean; non_competing?: boolean }>
): { enough_rounds: boolean; possible: boolean; has_ties: boolean; tied_uids: string[] } {
  if (!tournament) return { enough_rounds: false, possible: false, has_ties: false, tied_uids: [] };
  const resultJson = callEngine(() => getEngine().finalsQualification(JSON.stringify({ tournament, standings })));
  return JSON.parse(resultJson);
}

export function computePlayerIssuesSync(
  rounds: string[][][]
): { rule: number; players: string[] }[] | null {
  try {
    const resultJson = callEngine(() => getEngine().computePlayerIssues(JSON.stringify({ rounds })));
    return JSON.parse(resultJson);
  } catch (e) {
    console.error('computePlayerIssues failed:', e);
    return null;
  }
}

export async function createTournamentWithEngine(
  config: Record<string, unknown>,
  actor: { uid: string; roles: string[]; is_organizer: boolean; can_organize_league_uids: string[] }
): Promise<Record<string, unknown>> {
  const engine = await initEngine();
  const result = callEngine(() => engine.createTournament(JSON.stringify(config), JSON.stringify(actor)));
  return JSON.parse(result);
}

export async function buildActorContext(
  user: User | null, tournament: Tournament, actionType?: string
): Promise<ActorContext> {
  if (!user) {
    return { uid: '', roles: [], is_organizer: false, can_organize_league_uids: [], now: new Date().toISOString() };
  }
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

export interface ValidationError {
  severity: 'error' | 'warning';
  message: string;
}

/** Null means validation is unavailable (cards not hydrated, engine failure) — the scoreSeatingSync
 * convention. `[]` means genuinely valid; callers must not read null as a pass. */
export async function validateDeck(
  deck: { cards: Record<string, number>; name?: string },
  format: string
): Promise<ValidationError[] | null> {
  const engine = await initEngine();
  try {
    const { loadEngineCards } = await import('./cards');
    await loadEngineCards();

    const deckJson = JSON.stringify({ name: deck.name || '', cards: deck.cards });
    const resultJson = callEngine(() => engine.validateDeck(deckJson, format));
    return JSON.parse(resultJson);
  } catch {
    return null;
  }
}

