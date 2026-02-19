import type { TournamentState } from "./types";
import * as m from './paraglide/messages.js';

export interface StandingEntry {
  user_uid: string;
  gw: number;
  vp: number;
  tp: number;
  toss: number;
  rank: number;
  finals?: string;
}

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

export function seatDisplay(
  uid: string,
  playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>,
): string {
  const info = playerInfo[uid];
  if (!info) return uid;
  const display = info.nickname || info.name;
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

/** Strip leading markdown title if it matches the tournament name */
export function stripLeadingTitle(description: string, name: string): string {
  const lines = description.split('\n');
  if (lines.length === 0) return description;
  const first = lines[0]!.trim();
  // Match "# Title" where Title matches the tournament name (case-insensitive)
  if (first.startsWith('#')) {
    const titleText = first.replace(/^#+\s*/, '').trim();
    if (titleText.toLowerCase() === name.toLowerCase()) {
      const rest = lines.slice(1).join('\n').trimStart();
      return rest || description;
    }
  }
  return description;
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
