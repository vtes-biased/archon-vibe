import type { Tournament, TournamentState } from "./types";
import { computeFinalStandings, computeRatingPoints } from "./engine";
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

export function getStateBadgeClass(state: TournamentState): string {
  switch (state) {
    case "Planned": return "bg-surface-hover text-ink";
    case "Registration": return "badge-success";
    case "Waiting": return "badge-pending";
    case "Playing": return "bg-accent-soft/60 text-link-soft";
    case "Finished": return "bg-surface-active text-ink-muted";
    default: return "bg-surface-hover text-ink";
  }
}

/** Privacy abbreviation for a real name: first whitespace word in full, then the
 *  capitalised initials of the remaining words, no dots/spaces between them.
 *  "Lionel Marie Panhaleux" -> "Lionel MP"; "John Smith" -> "John S"; "Cher" -> "Cher". */
export function abbreviateName(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return "";
  const initials = words.slice(1).map(w => w[0]!.toUpperCase()).join("");
  return initials ? `${words[0]} ${initials}` : words[0]!;
}

/**
 * Render a player's name for display.
 *
 * Offline (IRL) events: real name + vekn only — the nickname is never shown.
 * Online events (privacy): show ONLY the nickname; the real name is never spelled
 * out — instead its abbreviation (abbreviateName) sits with the vekn id inside the
 * parens, e.g. "Lio (Lionel MP · 1234567)". With no nickname the abbreviation becomes
 * the primary, e.g. "Lionel MP (1234567)". Derived purely from whatever the viewer's
 * own access projection already put in playerInfo — nothing is precomputed server-side.
 */
export function seatDisplay(uid: string, playerInfo: PlayerInfoMap, online = false): string {
  const info = playerInfo[uid];
  if (!info) return uid;
  if (online) {
    const nick = info.display_name || info.nickname;
    const abbrev = abbreviateName(info.name) || info.name;
    if (nick) {
      const inside = [abbrev, info.vekn].filter(Boolean).join(" · ");
      return inside ? `${nick} (${inside})` : nick;
    }
    return info.vekn ? `${abbrev} (${info.vekn})` : abbrev;
  }
  // Offline (IRL) events: real name + vekn only — the nickname is never shown.
  return info.vekn ? `${info.name} (${info.vekn})` : info.name;
}

export function vpOptions(tableSize: number, allowImpossible: boolean): number[] {
  const opts: number[] = [];
  for (let v = 0; v <= tableSize; v += 0.5) {
    if (!allowImpossible && v === tableSize - 0.5) continue;
    opts.push(v);
  }
  return opts;
}

export function computeGwLocal(vps: number[]): number[] {
  if (vps.length === 0) return [];
  const max = Math.max(...vps);
  const maxCount = vps.filter(v => v === max).length;
  return vps.map(v => (v >= 2 && v === max && maxCount === 1 ? 1 : 0));
}

/** Finals GW: always awards 1 GW to the winner (highest VP, tiebroken by seed order). */
export function computeGwFinals(vps: number[], seedOrder: string[], seatingUids: string[]): number[] {
  if (vps.length === 0) return [];
  let bestIdx = 0;
  let bestVp = vps[0]!;
  let bestSeed = seedOrder.indexOf(seatingUids[0]!);
  if (bestSeed < 0) bestSeed = Infinity;
  for (let i = 1; i < vps.length; i++) {
    const vp = vps[i]!;
    let seed = seedOrder.indexOf(seatingUids[i]!);
    if (seed < 0) seed = Infinity;
    if (vp > bestVp || (vp === bestVp && seed < bestSeed)) {
      bestVp = vp;
      bestIdx = i;
      bestSeed = seed;
    }
  }
  const gws = new Array(vps.length).fill(0);
  gws[bestIdx] = 1;
  return gws;
}

export function computeTpLocal(tableSize: number, vps: number[]): number[] {
  const base: Record<number, number[]> = {
    5: [60, 48, 36, 24, 12],
    4: [60, 48, 24, 12],
    3: [60, 36, 12],
  };
  const b = base[tableSize];
  if (!b) return vps.map(() => 0);
  const indices = vps.map((_, i) => i).sort((a, c) => (vps[c] ?? 0) - (vps[a] ?? 0));
  const result = new Array(vps.length).fill(0);
  let i = 0;
  while (i < indices.length) {
    let j = i + 1;
    while (j < indices.length && vps[indices[j]!] === vps[indices[i]!]) j++;
    let sum = 0;
    for (let k = i; k < j; k++) sum += b[k] ?? 0;
    const avg = sum / (j - i);
    for (let k = i; k < j; k++) result[indices[k]!] = avg;
    i = j;
  }
  return result;
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

/**
 * Build the ranked standings table for a tournament.
 *
 * Constructs preliminary entries (from rounds, or from synced/imported standings
 * when no rounds exist), then lets the engine assign final placement + ranks
 * (winner 1st, other finalists tied for 2nd, non-finalists 6+). The engine is the
 * single source of truth for placement — see compute_final_standings.
 *
 * Pure over `tournament`; callers that need to recompute when WASM finishes loading
 * should read the engine-ready signal in their reactive wrapper.
 */
export function computeStandings(tournament: Tournament | null): StandingEntry[] {
  if (!tournament || !tournament.players) return [];

  let prelim: Array<{ user_uid: string; gw: number; vp: number; tp: number; toss: number; finalist: boolean }>;
  let winnerUid = tournament.winner ?? "";
  let finalsResults: Map<string, { gw: number; vp: number; tp: number }> | null = null;

  if (!tournament.rounds || tournament.rounds.length < 1) {
    // VEKN-synced / imported: standings already carry totals + finalist flags.
    const finalistUids = new Set(
      tournament.players.filter(p => p.finalist && p.user_uid).map(p => p.user_uid!)
    );
    prelim = tournament.standings?.length
      ? tournament.standings.map(s => ({
          user_uid: s.user_uid, gw: s.gw ?? 0, vp: s.vp ?? 0, tp: s.tp ?? 0,
          toss: s.toss ?? 0, finalist: s.finalist ?? finalistUids.has(s.user_uid),
        }))
      : tournament.players
          .filter(p => p.user_uid && p.result && (p.result.gw || p.result.vp || p.result.tp))
          .map(p => ({
            user_uid: p.user_uid!, gw: p.result.gw ?? 0, vp: p.result.vp ?? 0, tp: p.result.tp ?? 0,
            toss: p.toss ?? 0, finalist: finalistUids.has(p.user_uid!),
          }));
  } else {
    // Preliminary totals come from the engine-computed standings, which apply the
    // standings_adjustment (SA) penalty to VP and re-decide GW/TP per table. Do NOT
    // re-sum raw seat results here: the SA penalty lives only on the standings total
    // (the per-seat result.vp stays raw so the game state stays valid), so summing
    // seats would silently drop every SA. Fall back to raw aggregation only if the
    // engine hasn't populated standings yet (e.g. before the first score).
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
    for (const p of tournament.players) {
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

  // DQ'd players forfeit their own score (zeroed) and sort last; the engine
  // mirrors this on the stored standings, but we re-derive here so the seat-sum
  // fallback path is consistent too. Opponents' scores are untouched.
  // DQ from live player state OR the engine-persisted standings flag (the latter
  // covers VEKN-synced/imported tournaments that carry no live player.state).
  const dqUids = new Set<string>(
    tournament.players.filter(p => p.state === "Disqualified" && p.user_uid).map(p => p.user_uid!)
  );
  for (const s of tournament.standings ?? []) {
    if (s.disqualified) dqUids.add(s.user_uid);
  }
  // Proxy (non-competing): excluded from rank like DQ, but the score is NOT zeroed
  // (the seat's VPs are real). Same dual source as DQ: live player flag OR the
  // engine-persisted standings flag (covers synced/imported tournaments).
  const ncUids = new Set<string>(
    tournament.players.filter(p => p.non_competing && p.user_uid).map(p => p.user_uid!)
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

/** Distinct players seated in ≥1 preliminary round (finals seats folded in), or —
 *  for a rounds-less VEKN import — standings rows carrying any score. Mirrors backend
 *  ratings.py `_players_with_rounds`/`_player_count` so league RTP shares the exact
 *  field size that feeds every profile-rating coefficient (t.players.length would
 *  over-count no-shows). Stays inclusive of DQ'd players: their head-count still lifts
 *  everyone else's finalist coefficient. */
export function seatedPlayerCount(tournament: Tournament): number {
  const rounds = tournament.rounds ?? [];
  if (rounds.length) {
    const played = new Set<string>();
    for (const round of rounds)
      for (const table of round)
        for (const seat of table.seating ?? [])
          if (seat.player_uid) played.add(seat.player_uid);
    for (const seat of tournament.finals?.seating ?? [])
      if (seat.player_uid) played.add(seat.player_uid);
    return played.size;
  }
  return (tournament.standings ?? []).filter((s) => s.gw || s.vp || s.tp).length;
}

/** Rating points a Finished tournament awards a standings entry — the single copy.
 *  DQ'd/proxy players earn none (not even the base); the winner gains the +1 GW and
 *  finalist position 1. `playedCount` is seatedPlayerCount(tournament) — the field
 *  size backend ratings.py uses — NOT standings.length (over-counts no-shows). */
export function getRatingPts(entry: StandingEntry, tournament: Tournament, playedCount: number): number {
  if (tournament.state !== "Finished" || entry.disqualified || entry.non_competing) return 0;
  const isWinner = entry.user_uid === tournament.winner;
  const finalistPos = isWinner ? 1
    : (tournament.finals?.seating.some((s) => s.player_uid === entry.user_uid) ? 2 : 0);
  const gw = isWinner ? entry.gw + 1 : entry.gw;
  return computeRatingPoints(entry.vp, gw, finalistPos, playedCount, tournament.rank);
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
