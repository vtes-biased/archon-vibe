import type { TournamentState } from "./types";

export function getStateBadgeClass(state: TournamentState): string {
  switch (state) {
    case "Planned": return "bg-ash-800 text-ash-300";
    case "Registration": return "bg-emerald-900/60 text-emerald-300";
    case "Waiting": return "bg-amber-900/60 text-amber-300";
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
