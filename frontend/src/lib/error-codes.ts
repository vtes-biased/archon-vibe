// ENGINE_MESSAGES maps each engine/src/error.rs code (dots → underscores) to a paraglide err_* key;
// messages/en.json mirrors the Rust Display byte-for-byte. A missing key falls through to the caller's English fallback, never throws.
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

/** Parses a thrown value as the engine's wire JSON; returns null when it isn't one (legacy
 * free-text string throws keep the passthrough path). */
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
  'tournament.external_registration': (p) => m.err_tournament_external_registration({ url: p.url ?? '' }),
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
  'tournament.cannot_set_non_competing': () => m.err_tournament_cannot_set_non_competing(),
  'tournament.cannot_waitlist_player': () => m.err_tournament_cannot_waitlist_player(),
  'tournament.player_waitlisted': () => m.err_tournament_player_waitlisted(),
  'tournament.use_drop_out': () => m.err_tournament_use_drop_out(),
  'tournament.cannot_drop_out': () => m.err_tournament_cannot_drop_out(),
  'tournament.cannot_finish': () => m.err_tournament_cannot_finish(),
  'tournament.cannot_alter_seating': () => m.err_tournament_cannot_alter_seating(),
  'tournament.no_round_in_progress': () => m.err_tournament_no_round_in_progress(),
  'tournament.no_round_to_finish': () => m.err_tournament_no_round_to_finish(),
  'tournament.no_round_to_cancel': () => m.err_tournament_no_round_to_cancel(),
  'tournament.round_not_cancelled': () => m.err_tournament_round_not_cancelled(),
  'tournament.cannot_restore_round': () => m.err_tournament_cannot_restore_round(),
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
  'tournament.empty_round': () => m.err_tournament_empty_round(),
  'tournament.seating_violates_r1': () => m.err_tournament_seating_violates_r1(),
  'tournament.player_not_in_round': (p) => m.err_tournament_player_not_in_round({ player: p.player ?? '' }),
  'tournament.table_full': () => m.err_tournament_table_full(),
  'tournament.round_not_live': () => m.err_tournament_round_not_live(),
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
  'tournament.raffle_wrong_state': () => m.err_tournament_raffle_wrong_state(),
  'tournament.name_required': () => m.err_tournament_name_required(),
  'tournament.finish_before_start': () => m.err_tournament_finish_before_start(),
  'tournament.max_rounds_below_completed': (p) => m.err_tournament_max_rounds_below_completed({ max: p.max ?? '', completed: p.completed ?? '' }),
  'tournament.rank_forbids_proxies': () => m.err_tournament_rank_forbids_proxies(),
  'tournament.format_forbids_rank': () => m.err_tournament_format_forbids_rank(),
  'tournament.format_forbids_decks': () => m.err_tournament_format_forbids_decks(),
  'tournament.rank_forbids_multideck': () => m.err_tournament_rank_forbids_multideck(),
  'tournament.vekn_frozen_field': (p) => m.err_tournament_vekn_frozen_field({ field: p.field ?? '' }),
  'tournament.self_organize_disabled': () => m.err_tournament_self_organize_disabled(),
  'tournament.self_organize_not_open_rounds': () => m.err_tournament_self_organize_not_open_rounds(),
  'tournament.self_organize_not_seated': () => m.err_tournament_self_organize_not_seated(),
  'tournament.self_organize_ineligible': (p) => m.err_tournament_self_organize_ineligible({ player: p.player ?? '' }),
  'tournament.archival_results_forbidden': () => m.err_tournament_archival_results_forbidden(),
  'tournament.archival_results_has_play': () => m.err_tournament_archival_results_has_play(),
  'tournament.archival_results_vekn_linked': () => m.err_tournament_archival_results_vekn_linked(),
  'tournament.archival_results_winner_not_listed': () => m.err_tournament_archival_results_winner_not_listed(),
  'tournament.archival_results_count_below_roster': (p) => m.err_tournament_archival_results_count_below_roster({ reported: p.reported ?? '', listed: p.listed ?? '' }),
  // Backend-origin (not an engine/error.rs code): create_user's dup-email 409.
  'user.email_exists': () => m.err_user_email_exists(),
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
