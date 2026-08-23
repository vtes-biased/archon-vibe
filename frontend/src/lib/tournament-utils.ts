import type { Sanction, Tournament, TournamentState, TournamentRank } from "./types";
import type { BadgeTone } from "./components/Badge.svelte";
import { attestedPlayerCount, computeRatingPoints, computeRatingVpGw, displayStandings, rankingEligibility } from "./engine";
import { formatScore } from "./utils";
import * as m from './paraglide/messages.js';

export interface StandingEntry {
  user_uid: string;
  gw: number;
  vp: number;
  tp: number;
  toss: number;
  rank: number;
  finals?: string;
  finalist?: boolean;
  /** The rating formula's finalist argument, stamped by the engine beside `rank`:
   *  1 winner, 2 other finalist, 0 neither. */
  finalist_position?: number;
  /** DQ'd: score forfeited (zeroed), sorted last, no competitive rank / RTP. */
  disqualified?: boolean;
  /** Proxy: a non-competing official stood in. Excluded from rank/RTP/finals and
   *  sorted last like DQ, but the score is NOT zeroed (the seat's VPs are real). */
  non_competing?: boolean;
  /** Holds no placement — DQ'd, proxy, or a no-show carrying an import's scoreless
   *  row. The rank cell reads "—"; the row and the name stay. */
  unplaced?: boolean;
}

/** Player display info keyed by user uid (built from User records + per-tournament display_name). */
export type PlayerInfoMap = Record<
  string,
  { name: string; nickname: string | null; vekn: string | null; display_name?: string | null }
>;

/** The state is the one STATUS badge in the header — the only chip allowed a meaning-bearing colour.
 * Tones only; chip chrome belongs to <Badge>, so this can never drift into raw utilities again. */
export function getStateTone(state: TournamentState): BadgeTone {
  switch (state) {
    case "Planned": return "neutral";      // not happening yet — quietest
    case "Registration": return "info";    // sign-ups open
    case "Waiting": return "pending";      // at the door / between rounds
    case "Playing": return "crimson";      // live, and crimson is the app's "now"
    case "Finished": return "slate";
    default: return "neutral";
  }
}

/** Privacy abbreviation: first word in full, then capitalised initials of the rest, no separators.
 * "Lionel Marie Panhaleux" -> "Lionel MP"; "John Smith" -> "John S"; "Cher" -> "Cher". */
export function abbreviateName(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const initials = words.slice(1).map(w => w[0]!.toUpperCase()).join("");
  return initials ? `${words[0]} ${initials}` : words[0]!;
}

/** Offline events show real name + vekn (never nickname); online events show nickname only, with the
 * abbreviated real name + vekn in parens — e.g. "Lio (Lionel MP · 1234567)". */
export function seatDisplay(uid: string, playerInfo: PlayerInfoMap, online = false): string {
  const { primary, detail } = seatDisplayParts(uid, playerInfo, online);
  return detail ? `${primary} (${detail})` : primary;
}

/** The same rule, split, for callers that style the parenthetical separately
 *  (the printed seating sheet greys it). Keeps one copy of a privacy rule. */
export function seatDisplayParts(
  uid: string,
  playerInfo: PlayerInfoMap,
  online = false,
): { primary: string; detail: string } {
  const info = playerInfo[uid];
  if (!info) return { primary: uid, detail: "" };
  if (online) {
    const nick = info.display_name || info.nickname;
    const abbrev = abbreviateName(info.name) || info.name;
    if (nick) return { primary: nick, detail: [abbrev, info.vekn].filter(Boolean).join(" · ") };
    return { primary: abbrev, detail: info.vekn ?? "" };
  }
  // Offline (IRL) events: real name + vekn only — the nickname is never shown.
  return { primary: info.name, detail: info.vekn ?? "" };
}

export function vpOptions(tableSize: number, allowImpossible: boolean): number[] {
  const opts: number[] = [];
  for (let v = 0; v <= tableSize; v += 0.5) {
    if (!allowImpossible && v === tableSize - 0.5) continue;
    opts.push(v);
  }
  return opts;
}

export function computeStandings(tournament: Tournament | null, sanctions: Sanction[]): StandingEntry[] {
  if (!tournament) return [];
  return displayStandings(tournament, sanctions).map(e => {
    const entry: StandingEntry = {
      user_uid: e.user_uid, gw: e.gw, vp: e.vp, tp: e.tp, toss: e.toss, rank: e.rank,
      finalist: e.finalist, finalist_position: e.finalist_position,
      disqualified: e.disqualified, non_competing: e.non_competing,
      unplaced: e.disqualified || e.non_competing || e.no_show,
    };
    if (e.finals) entry.finals = formatScore(e.finals.gw, e.finals.vp, e.finals.tp);
    return entry;
  });
}

/** Deliberately NOT initials: "NC"/"CC" invert across the languages we ship (Campeonato Nacional,
 * Championnat National), and full rank names made the header wrap — one word each is the middle. */
export function rankBadgeLabel(rank: TournamentRank): string {
  if (rank === 'National Championship') return m.promo_rank_national();
  if (rank === 'Continental Championship') return m.promo_rank_continental();
  return rank;
}

export function translateTournamentState(state: TournamentState): string {
  switch (state) {
    case "Planned": return m.state_planned();
    case "Registration": return m.state_registration();
    case "Waiting": return m.state_checkin();
    case "Playing": return m.state_playing();
    case "Finished": return m.state_finished();
    default: return state;
  }
}

export function translatePlayerState(state: string): string {
  switch (state) {
    case "Registered": return m.player_state_registered();
    case "Checked-in": return m.player_state_checked_in();
    case "Playing": return m.state_playing();
    case "Completed": return m.player_state_completed();
    case "Finished": return m.state_finished();
    case "Disqualified": return m.player_state_disqualified();
    default: return state;
  }
}

/** Number of rounds in which a player is seated — the per-player count for open-rounds caps.
 *  Mirrors the engine's count_player_rounds_played (seating is the single source of truth). */
export function roundsPlayed(tournament: Tournament, uid: string): number {
  return (tournament.rounds ?? []).filter(
    (round) => round.some((table) => table.seating?.some((seat) => seat.player_uid === uid)),
  ).length;
}

/** Distinct players in ≥1 preliminary round (finals folded in), or — for a rounds-less import —
 * standings rows carrying any score. A twin of backend ratings.py's player-count function; keep them in sync. */
export function playedPlayerUids(tournament: Tournament): Set<string> {
  const rounds = tournament.rounds ?? [];
  if (rounds.length) {
    const played = new Set<string>();
    for (const round of rounds)
      for (const table of round)
        for (const seat of table.seating ?? [])
          if (seat.player_uid) played.add(seat.player_uid);
    for (const seat of tournament.finals?.seating ?? [])
      if (seat.player_uid) played.add(seat.player_uid);
    return played;
  }
  return new Set(
    (tournament.standings ?? []).filter((s) => s.gw || s.vp || s.tp).map((s) => s.user_uid),
  );
}

/** Wins that make a Hall of Fame member. The list itself is server-computed
 * (`user.wins`, member-level) — only the cutoff is applied here. */
export const HOF_MIN_WINS = 5;

/** Outward-facing link to an event. The uid form stays valid forever, so it is
 * the fallback for the window before the code is stamped — never a wait. */
export function eventUrl(baseUrl: string, t: { uid: string; event_code?: string }): string {
  return t.event_code ? `${baseUrl}/t/${t.event_code}` : `${baseUrl}/tournaments/${t.uid}`;
}

export type RankedStatus =
  | { ranked: true }
  | { ranked: false; reason: "few_players" | "no_final" | "open_rounds" | "no_results" }
  | null;

/** VEKN rules 3.1/3.1.6: ranked needs ≥8 players AND a played final, decided by the engine's
 * ranking_eligibility (same predicate backend ratings.py inclusion-filters on). null = indeterminate. */
export function rankedStatus(t: Tournament): RankedStatus {
  if (t.open_rounds || t.self_organized_rounds) return { ranked: false, reason: "open_rounds" };
  if (t.state === "Finished") {
    // Length, not presence: imported rows often carry empty arrays.
    if (!t.rounds?.length && !t.standings?.length) return null;
    const verdict = rankingEligibility(t);
    if (verdict === null) return null;
    if (verdict === "eligible") return { ranked: true };
    return { ranked: false, reason: verdict as "few_players" | "no_final" | "open_rounds" | "no_results" };
  }
  if (t.state === "Waiting" || t.state === "Playing") {
    if (!t.players) return null;
    const checkedIn = t.players.filter((p) => p.state !== "Registered").length;
    return checkedIn >= 8 ? { ranked: true } : { ranked: false, reason: "few_players" };
  }
  return null; // Planned/Registration: too early to call
}

/** Per-tournament RtP inputs, built once per render: the engine aggregation takes
 *  the whole tournament plus its sanctions, not standings-row fields. */
export interface RatingContext {
  played: Set<string>;
  fieldSize: number;
  tournamentJson: string;
  sanctionsJson: string;
  eligible: boolean;
}

export function ratingContext(tournament: Tournament, sanctions: Sanction[] | undefined): RatingContext {
  const played = playedPlayerUids(tournament);
  return {
    played,
    fieldSize: attestedPlayerCount(tournament),
    tournamentJson: JSON.stringify(tournament),
    sanctionsJson: JSON.stringify(sanctions ?? []),
    eligible: rankingEligibility(tournament) === "eligible",
  };
}

/** Null where the backend stores no entry — never played, DQ'd, proxy, ranking-ineligible (null renders
 * blank). Same engine call backend ratings.py uses; standings rows are prelim-only, no SA applied. */
export function getRatingPts(
  entry: StandingEntry,
  tournament: Tournament,
  ctx: RatingContext,
): number | null {
  if (tournament.state !== "Finished" || entry.unplaced) return null;
  if (!ctx.eligible || !ctx.played.has(entry.user_uid)) return null;
  const vpGw = computeRatingVpGw(ctx.tournamentJson, ctx.sanctionsJson, entry.user_uid);
  if (!vpGw) return null;
  // Engine returns gw as f64; the backend stores int(gw) before scoring it.
  return computeRatingPoints(vpGw[0], Math.trunc(vpGw[1]), entry.finalist_position ?? 0, ctx.fieldSize, tournament.rank);
}

export function translateStandingsMode(mode: string | undefined): string {
  switch (mode) {
    case "Private": return m.tournament_standings_private();
    case "Cutoff": return m.tournament_standings_cutoff();
    case "Top 10": return m.tournament_standings_top10();
    case "Public": return m.tournament_standings_public();
    default: return mode ?? "";
  }
}

export function translateTableState(state: string): string {
  switch (state) {
    case "In Progress": return m.table_state_in_progress();
    case "Finished": return m.state_finished();
    case "Invalid": return m.table_state_invalid();
    case "Cancelled": return m.table_state_cancelled();
    default: return state;
  }
}
