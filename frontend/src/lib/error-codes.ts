/**
 * Engine error contract: typed errors carrying the engine's stable
 * `{ code, params }` so the UI can render localized messages.
 *
 * The Rust engine serializes rejections as `{"code","params","message"}` JSON:
 * thrown as a JS string over WASM, carried as top-level `code`/`params` next to
 * `detail` in the backend's 400 body. `ENGINE_MESSAGES` maps each public code to
 * its paraglide `err_*` key (code dots → underscores); the catalog lives in
 * engine/src/error.rs and messages/en.json mirrors its English byte-for-byte.
 *
 * Lookup is `ENGINE_MESSAGES[code]?.(params)` — a missing key (e.g. a future
 * code from a newer backend under version skew) falls through to the caller's
 * English fallback, never throws. `internal` maps to a generic localized
 * message: parse/invariant noise is logged, not shown.
 */
import * as m from './paraglide/messages.js';

/** A structured engine rejection, re-thrown from WASM calls and JS pre-checks. */
export class EngineError extends Error {
  constructor(
    public code: string,
    public params: Record<string, string> = {},
    message?: string
  ) {
    super(message || code);
    this.name = 'EngineError';
  }
}

/**
 * Parse a thrown value as the engine's wire JSON; returns null when it isn't
 * one (legacy free-text string throws keep the passthrough path).
 */
export function engineErrorFromThrown(e: unknown): EngineError | null {
  if (typeof e !== 'string' || !e.startsWith('{')) return null;
  try {
    const body = JSON.parse(e);
    if (typeof body?.code !== 'string') return null;
    return new EngineError(body.code, body.params ?? {}, body.message);
  } catch {
    return null;
  }
}

const ENGINE_MESSAGES: Record<string, (p: Record<string, string>) => string> = {
  'tournament.not_organizer': () => m.err_tournament_not_organizer(),
  'tournament.create_forbidden': () => m.err_tournament_create_forbidden(),
  'tournament.unregister_only_self': () => m.err_tournament_unregister_only_self(),
  'tournament.drop_out_forbidden': () => m.err_tournament_drop_out_forbidden(),
  'tournament.check_in_forbidden': () => m.err_tournament_check_in_forbidden(),
  'tournament.deck_upload_forbidden': () => m.err_tournament_deck_upload_forbidden(),
  'tournament.deck_delete_forbidden': () => m.err_tournament_deck_delete_forbidden(),
  'tournament.score_forbidden': () => m.err_tournament_score_forbidden(),
  'tournament.score_locked': () => m.err_tournament_score_locked(),
  'tournament.score_set_by_organizer': () => m.err_tournament_score_set_by_organizer(),
  'tournament.league_link_forbidden': () => m.err_tournament_league_link_forbidden(),
  'tournament.vekn_id_required': () => m.err_tournament_vekn_id_required(),
  'tournament.already_registered': () => m.err_tournament_already_registered(),
  'tournament.not_registered': () => m.err_tournament_not_registered(),
  'tournament.player_disqualified': () => m.err_tournament_player_disqualified(),
  'tournament.player_suspended': () => m.err_tournament_player_suspended(),
  'tournament.player_not_found': () => m.err_tournament_player_not_found(),
  'tournament.player_not_checked_in': () => m.err_tournament_player_not_checked_in(),
  'tournament.player_already_finished': () => m.err_tournament_player_already_finished(),
  'tournament.player_wrong_state': (p) => m.err_tournament_player_wrong_state({ current: p.current ?? '' }),
  'tournament.wrong_state': (p) => m.err_tournament_wrong_state({ expected: p.expected ?? '', current: p.current ?? '' }),
  'tournament.cannot_add_players': () => m.err_tournament_cannot_add_players(),
  'tournament.cannot_remove_players': () => m.err_tournament_cannot_remove_players(),
  'tournament.use_drop_out': () => m.err_tournament_use_drop_out(),
  'tournament.cannot_drop_out': () => m.err_tournament_cannot_drop_out(),
  'tournament.cannot_finish': () => m.err_tournament_cannot_finish(),
  'tournament.cannot_alter_seating': () => m.err_tournament_cannot_alter_seating(),
  'tournament.no_round_in_progress': () => m.err_tournament_no_round_in_progress(),
  'tournament.no_round_to_finish': () => m.err_tournament_no_round_to_finish(),
  'tournament.no_round_to_cancel': () => m.err_tournament_no_round_to_cancel(),
  'tournament.only_last_round_cancellable': () => m.err_tournament_only_last_round_cancellable(),
  'tournament.tables_not_finished': (p) => m.err_tournament_tables_not_finished({ tables: p.tables ?? '' }),
  'tournament.prelim_after_finals': () => m.err_tournament_prelim_after_finals(),
  'tournament.player_reached_max_rounds': () => m.err_tournament_player_reached_max_rounds(),
  'tournament.not_enough_players': () => m.err_tournament_not_enough_players(),
  'tournament.invalid_table_size': (p) => m.err_tournament_invalid_table_size({ size: p.size ?? '' }),
  'tournament.player_not_in_subset': (p) => m.err_tournament_player_not_in_subset({ player: p.player ?? '' }),
  'tournament.duplicate_player': () => m.err_tournament_duplicate_player(),
  'tournament.seating_incomplete': () => m.err_tournament_seating_incomplete(),
  'tournament.invalid_round': () => m.err_tournament_invalid_round(),
  'tournament.invalid_table': () => m.err_tournament_invalid_table(),
  'tournament.invalid_seat': () => m.err_tournament_invalid_seat(),
  'tournament.finals_one_table': () => m.err_tournament_finals_one_table(),
  'tournament.finals_player_count': () => m.err_tournament_finals_player_count(),
  'tournament.finals_player_set': () => m.err_tournament_finals_player_set(),
  'tournament.table_count_mismatch': () => m.err_tournament_table_count_mismatch(),
  'tournament.player_count_mismatch': () => m.err_tournament_player_count_mismatch(),
  'tournament.seating_violates_r1': () => m.err_tournament_seating_violates_r1(),
  'tournament.player_not_in_round': (p) => m.err_tournament_player_not_in_round({ player: p.player ?? '' }),
  'tournament.table_full': () => m.err_tournament_table_full(),
  'tournament.table_not_empty': () => m.err_tournament_table_not_empty(),
  'tournament.invalid_score': () => m.err_tournament_invalid_score(),
  'tournament.finals_min_rounds': () => m.err_tournament_finals_min_rounds(),
  'tournament.finals_already_started': () => m.err_tournament_finals_already_started(),
  'tournament.finals_not_enough_players': () => m.err_tournament_finals_not_enough_players(),
  'tournament.finals_unresolved_ties': () => m.err_tournament_finals_unresolved_ties(),
  'tournament.no_finals_in_progress': () => m.err_tournament_no_finals_in_progress(),
  'tournament.finals_table_unfinished': () => m.err_tournament_finals_table_unfinished(),
  'tournament.toss_min_rounds': () => m.err_tournament_toss_min_rounds(),
  'tournament.deck_locked_finished': () => m.err_tournament_deck_locked_finished(),
  'tournament.deck_locked_playing': () => m.err_tournament_deck_locked_playing(),
  'tournament.deck_locked_round': () => m.err_tournament_deck_locked_round(),
  'tournament.raffle_count_min': () => m.err_tournament_raffle_count_min(),
  'tournament.raffle_no_players': () => m.err_tournament_raffle_no_players(),
  'tournament.raffle_no_draws': () => m.err_tournament_raffle_no_draws(),
  'tournament.raffle_none_played': () => m.err_tournament_raffle_none_played(),
  'tournament.raffle_wrong_state': () => m.err_tournament_raffle_wrong_state(),
  'tournament.name_required': () => m.err_tournament_name_required(),
  'tournament.max_rounds_below_completed': (p) => m.err_tournament_max_rounds_below_completed({ max: p.max ?? '', completed: p.completed ?? '' }),
  'deck.no_cards': () => m.err_deck_no_cards(),
  'seating.min_players': () => m.err_seating_min_players(),
  'seating.min_rounds': () => m.err_seating_min_rounds(),
  'internal': () => m.err_internal(),
};

/** Localized message for an engine error code, or undefined for unknown codes. */
export function errorCodeToMessage(
  code: string,
  params: Record<string, string> = {}
): string | undefined {
  return ENGINE_MESSAGES[code]?.(params);
}
