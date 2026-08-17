import type { Sanction, Tournament, TournamentState, TournamentRank } from "./types";
import type { BadgeTone } from "./components/Badge.svelte";
import { attestedPlayerCount, computeFinalStandings, computeRatingPoints, computeRatingVpGw, rankingEligibility } from "./engine";
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
  /** DQ'd: score forfeited (zeroed), sorted last, no competitive rank / RTP. */
  disqualified?: boolean;
  /** Proxy: a non-competing official stood in. Excluded from rank/RTP/finals and
   *  sorted last like DQ, but the score is NOT zeroed (the seat's VPs are real). */
  non_competing?: boolean;
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

export function top5HasTies(standings: StandingEntry[]): boolean {
  if (standings.length < 5) return false;
  for (let i = 0; i < 5; i++) {
    for (let j = i + 1; j < 5; j++) {
      const a = standings[i]!, b = standings[j]!;
      if (a.gw === b.gw && a.vp === b.vp && a.tp === b.tp && a.toss === b.toss) return true;
    }
  }
  const fifth = standings[4]!;
  for (let k = 5; k < standings.length; k++) {
    const s = standings[k]!;
    // DQ'd/proxy rows are parked last and never finals-eligible; they never tie for the cutoff.
    if (!s.disqualified && !s.non_competing && s.gw === fifth.gw && s.vp === fifth.vp && s.tp === fifth.tp && s.toss === fifth.toss) return true;
  }
  return false;
}

/** Check if top 5 has score ties (GW/VP/TP only, ignoring toss) — for showing toss UI */
export function top5HasScoreTies(standings: StandingEntry[]): boolean {
  if (standings.length < 5) return false;
  for (let i = 0; i < 5; i++) {
    for (let j = i + 1; j < 5; j++) {
      const a = standings[i]!, b = standings[j]!;
      if (a.gw === b.gw && a.vp === b.vp && a.tp === b.tp) return true;
    }
  }
  const fifth = standings[4]!;
  for (let k = 5; k < standings.length; k++) {
    const s = standings[k]!;
    if (!s.disqualified && !s.non_competing && s.gw === fifth.gw && s.vp === fifth.vp && s.tp === fifth.tp) return true;
  }
  return false;
}

/** Preliminary entries come from rounds (or synced/imported standings when there are no rounds); the
 * engine assigns final placement. Pure over `tournament` — callers must re-run when WASM finishes loading. */
export function computeStandings(tournament: Tournament | null): StandingEntry[] {
  if (!tournament) return [];
  // Imported records can carry standings without a roster.
  const players = tournament.players ?? [];

  let prelim: Array<{ user_uid: string; gw: number; vp: number; tp: number; toss: number; finalist: boolean }>;
  let winnerUid = tournament.winner ?? "";
  let finalsResults: Map<string, { gw: number; vp: number; tp: number }> | null = null;

  if (!tournament.rounds || tournament.rounds.length < 1) {
    // VEKN-synced / imported: standings already carry totals + finalist flags.
    const finalistUids = new Set(
      players.filter(p => p.finalist && p.user_uid).map(p => p.user_uid!)
    );
    prelim = tournament.standings?.length
      ? tournament.standings.map(s => ({
          user_uid: s.user_uid, gw: s.gw ?? 0, vp: s.vp ?? 0, tp: s.tp ?? 0,
          toss: s.toss ?? 0, finalist: s.finalist ?? finalistUids.has(s.user_uid),
        }))
      : players
          .filter(p => p.user_uid && p.result && (p.result.gw || p.result.vp || p.result.tp))
          .map(p => ({
            user_uid: p.user_uid!, gw: p.result.gw ?? 0, vp: p.result.vp ?? 0, tp: p.result.tp ?? 0,
            toss: p.toss ?? 0, finalist: finalistUids.has(p.user_uid!),
          }));
  } else {
    // Preliminary totals come from engine-computed standings (SA penalty applied to VP, GW/TP re-decided
    // per table). Do NOT re-sum raw seat results — SA lives only on the standings total, not per-seat.
    const map = new Map<string, { gw: number; vp: number; tp: number }>();
    if (tournament.standings?.length) {
      for (const s of tournament.standings) {
        map.set(s.user_uid, { gw: s.gw ?? 0, vp: s.vp ?? 0, tp: s.tp ?? 0 });
      }
    } else {
      for (const round of tournament.rounds) {
        for (const table of round) {
          for (const seat of table.seating) {
            if (!seat.player_uid) continue;
            const e = map.get(seat.player_uid) ?? { gw: 0, vp: 0, tp: 0 };
            e.gw += seat.result.gw ?? 0;
            e.vp += seat.result.vp ?? 0;
            e.tp += seat.result.tp ?? 0;
            map.set(seat.player_uid, e);
          }
        }
      }
    }
    const tossMap = new Map<string, number>();
    for (const p of players) {
      if (p.user_uid) tossMap.set(p.user_uid, p.toss ?? 0);
    }
    // Finals count only once finished; otherwise show live preliminary ranking.
    let finalistUids = new Set<string>();
    if (tournament.state === "Finished" && tournament.finals) {
      finalistUids = new Set(tournament.finals.seating.map(s => s.player_uid));
      finalsResults = new Map(tournament.finals.seating.map(s => [s.player_uid, s.result]));
      if (!winnerUid) {
        const sorted = [...tournament.finals.seating].sort((a, b) => (b.result.gw - a.result.gw) || (b.result.vp - a.result.vp));
        winnerUid = sorted[0]?.player_uid ?? "";
      }
    } else {
      winnerUid = ""; // finals not done yet → preliminary ranking only
    }
    prelim = [...map.entries()].map(([uid, s]) => ({
      user_uid: uid, ...s, toss: tossMap.get(uid) ?? 0, finalist: finalistUids.has(uid),
    }));
  }

  // DQ'd players forfeit their own score (zeroed) and sort last; re-derived here so the seat-sum fallback
  // stays consistent with the engine. DQ signal is live player.state OR the persisted standings flag.
  const dqUids = new Set<string>(
    players.filter(p => p.state === "Disqualified" && p.user_uid).map(p => p.user_uid!)
  );
  for (const s of tournament.standings ?? []) {
    if (s.disqualified) dqUids.add(s.user_uid);
  }
  // Proxy (non-competing): excluded from rank like DQ, but the score is NOT zeroed. Same dual source as
  // DQ: live player flag OR the persisted standings flag (covers synced/imported tournaments).
  const ncUids = new Set<string>(
    players.filter(p => p.non_competing && p.user_uid).map(p => p.user_uid!)
  );
  for (const s of tournament.standings ?? []) {
    if (s.non_competing) ncUids.add(s.user_uid);
  }
  const prelimDq = prelim.map(e => {
    const disqualified = dqUids.has(e.user_uid);
    const non_competing = ncUids.has(e.user_uid);
    return disqualified
      ? { ...e, gw: 0, vp: 0, tp: 0, disqualified, non_competing }
      : { ...e, disqualified, non_competing };
  });

  // The engine assumes input pre-sorted descending by preliminary score, with the
  // non-ranked (DQ'd or proxy) parked last.
  prelimDq.sort((a, b) => {
    const aEx = a.disqualified || a.non_competing;
    const bEx = b.disqualified || b.non_competing;
    return (aEx === bEx ? 0 : aEx ? 1 : -1)
      || b.gw - a.gw || b.vp - a.vp || b.tp - a.tp || b.toss - a.toss || a.user_uid.localeCompare(b.user_uid);
  });
  const ranked = computeFinalStandings(prelimDq, winnerUid);
  if (!ranked.length) {
    // Engine not ready (load() awaits initEngine, so this is a safety net):
    // degrade to preliminary order so the table is never blank.
    return prelimDq.map((e, i) => ({ ...e, rank: i + 1 }));
  }
  return ranked.map(e => {
    const entry: StandingEntry = {
      user_uid: e.user_uid, gw: e.gw, vp: e.vp, tp: e.tp, toss: e.toss, rank: e.rank, finalist: e.finalist, disqualified: e.disqualified, non_competing: e.non_competing,
    };
    const fr = finalsResults?.get(e.user_uid);
    if (fr) entry.finals = formatScore(fr.gw, fr.vp, fr.tp);
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
  if (tournament.state !== "Finished" || entry.disqualified || entry.non_competing) return null;
  if (!ctx.eligible || !ctx.played.has(entry.user_uid)) return null;
  const vpGw = computeRatingVpGw(ctx.tournamentJson, ctx.sanctionsJson, entry.user_uid);
  if (!vpGw) return null;
  const finalistPos = entry.user_uid === tournament.winner ? 1
    : (tournament.finals?.seating.some((s) => s.player_uid === entry.user_uid) ? 2 : 0);
  // Engine returns gw as f64; the backend stores int(gw) before scoring it.
  return computeRatingPoints(vpGw[0], Math.trunc(vpGw[1]), finalistPos, ctx.fieldSize, tournament.rank);
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

export function resolveTableLabel(
  tableRooms: { name: string; count: number }[] | undefined,
  tableIndex: number,
): string | null {
  if (!tableRooms?.length) return null;
  let offset = 0;
  for (const room of tableRooms) {
    if (tableIndex < offset + room.count) {
      const localIndex = tableIndex - offset + 1;
      return room.count === 1 ? room.name : `${room.name} ${localIndex}`;
    }
    offset += room.count;
  }
  return null;
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
