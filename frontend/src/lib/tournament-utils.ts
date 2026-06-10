import type { Tournament, TournamentState } from "./types";
import { computeFinalStandings } from "./engine";
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
}

/** Player display info keyed by user uid (built from User records + per-tournament display_name). */
export type PlayerInfoMap = Record<
  string,
  { name: string; nickname: string | null; vekn: string | null; display_name?: string | null }
>;

export function getStateBadgeClass(state: TournamentState): string {
  switch (state) {
    case "Planned": return "bg-ash-800 text-ash-300";
    case "Registration": return "badge-emerald";
    case "Waiting": return "badge-amber";
    case "Playing": return "bg-crimson-900/60 text-crimson-300";
    case "Finished": return "bg-ash-700 text-ash-400";
    default: return "bg-ash-800 text-ash-300";
  }
}

export function seatDisplay(uid: string, playerInfo: PlayerInfoMap): string {
  const info = playerInfo[uid];
  if (!info) return uid;
  const display = info.display_name || info.nickname || info.name;
  return info.vekn ? `${display} (${info.vekn})` : display;
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
    if (s.gw === fifth.gw && s.vp === fifth.vp && s.tp === fifth.tp && s.toss === fifth.toss) return true;
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
    if (s.gw === fifth.gw && s.vp === fifth.vp && s.tp === fifth.tp) return true;
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
    // Aggregate the preliminary rounds.
    const map = new Map<string, { gw: number; vp: number; tp: number }>();
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

  // The engine assumes input pre-sorted descending by preliminary score.
  prelim.sort((a, b) => b.gw - a.gw || b.vp - a.vp || b.tp - a.tp || b.toss - a.toss || a.user_uid.localeCompare(b.user_uid));
  const ranked = computeFinalStandings(prelim, winnerUid);
  if (!ranked.length) {
    // Engine not ready (load() awaits initEngine, so this is a safety net):
    // degrade to preliminary order so the table is never blank.
    return prelim.map((e, i) => ({ ...e, rank: i + 1 }));
  }
  return ranked.map(e => {
    const entry: StandingEntry = {
      user_uid: e.user_uid, gw: e.gw, vp: e.vp, tp: e.tp, toss: e.toss, rank: e.rank, finalist: e.finalist,
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
    case "Finished": return m.state_finished();
    default: return state;
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
    default: return state;
  }
}
