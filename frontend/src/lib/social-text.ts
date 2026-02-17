/**
 * Plain text generation for sharing tournament results via clipboard.
 */
import type { Tournament, Deck, VtesCard } from "$lib/types";
import type { StandingEntry } from "$lib/tournament-utils";
import { seatDisplay } from "$lib/tournament-utils";
import { formatScore } from "$lib/utils";
import { getCountry } from "$lib/geonames";
import { getCards } from "$lib/cards";

// Standard TWDA library type ordering (from krcg config, matches DeckDisplay.svelte)
const LIBRARY_TYPE_ORDER = [
  "Master", "Conviction", "Action", "Action/Combat", "Action/Reaction",
  "Ally", "Equipment", "Political Action", "Retainer", "Power",
  "Action Modifier", "Action Modifier/Combat", "Action Modifier/Reaction",
  "Reaction", "Combat", "Combat/Reaction", "Event",
];

interface CardEntry { name: string; count: number; type: string; capacity: number }

function formatDeckText(deck: Deck, cardsMap: Map<number, VtesCard>): string[] {
  const lines: string[] = [];
  if (deck.name) lines.push(deck.name);
  if (deck.author) lines.push(`by ${deck.author}`);
  if (lines.length) lines.push("");

  const crypt: CardEntry[] = [];
  const library: CardEntry[] = [];

  for (const [idStr, count] of Object.entries(deck.cards)) {
    const card = cardsMap.get(parseInt(idStr));
    if (!card) continue;
    const entry = { name: card.name, count, type: card.types[0] ?? "", capacity: card.capacity };
    if (card.kind === "crypt") crypt.push(entry);
    else library.push(entry);
  }

  crypt.sort((a, b) => b.capacity - a.capacity || a.name.localeCompare(b.name));

  const cryptTotal = crypt.reduce((s, c) => s + c.count, 0);
  const libTotal = library.reduce((s, c) => s + c.count, 0);

  if (crypt.length) {
    lines.push(`Crypt (${cryptTotal})`);
    for (const c of crypt) lines.push(`${c.count}x ${c.name}`);
    lines.push("");
  }

  // Group library by type in TWDA order
  if (library.length) {
    lines.push(`Library (${libTotal})`);
    const groups: Record<string, CardEntry[]> = {};
    for (const c of library) (groups[c.type] ??= []).push(c);
    const sorted = Object.entries(groups).sort(([a], [b]) => {
      const ai = LIBRARY_TYPE_ORDER.indexOf(a);
      const bi = LIBRARY_TYPE_ORDER.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
    for (const [type, cards] of sorted) {
      const typeTotal = cards.reduce((s, c) => s + c.count, 0);
      cards.sort((a, b) => a.name.localeCompare(b.name));
      lines.push(`-- ${type} (${typeTotal})`);
      for (const c of cards) lines.push(`${c.count}x ${c.name}`);
    }
    lines.push("");
  }

  return lines;
}

export async function generateResultsText(
  tournament: Tournament,
  playerInfo: Record<string, { name: string; nickname: string | null; vekn: string | null }>,
  standings: StandingEntry[],
): Promise<string> {
  const lines: string[] = [];

  lines.push(`\u{1F3C6} ${tournament.name}`);

  // Date + location
  const parts: string[] = [];
  if (tournament.start) {
    const d = new Date(tournament.start);
    parts.push(d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }));
  }
  if (tournament.country) {
    const c = getCountry(tournament.country);
    if (c) parts.push(c.name);
  }
  if (parts.length) lines.push(`\u{1F4C5} ${parts.join(" \u00B7 ")}`);

  // Format / rank
  const typeParts: string[] = [];
  if (tournament.format) typeParts.push(tournament.format);
  if (tournament.rank) typeParts.push(tournament.rank);
  if (typeParts.length) lines.push(typeParts.join(" \u00B7 "));

  const playerCount = tournament.players?.length ?? 0;
  if (playerCount > 0) lines.push(`${playerCount} players`);

  lines.push("");

  // Winner
  if (tournament.winner) {
    const winnerName = seatDisplay(tournament.winner, playerInfo);
    const winnerEntry = standings.find((e) => e.user_uid === tournament.winner);
    const score = winnerEntry ? ` \u2014 ${formatScore(winnerEntry.gw, winnerEntry.vp, winnerEntry.tp)}` : "";
    lines.push(`\u{1F947} Winner: ${winnerName}${score}`);
    lines.push("");
  }

  // All standings
  if (standings.length > 0) {
    lines.push("Standings:");
    for (const entry of standings) {
      const name = seatDisplay(entry.user_uid, playerInfo);
      const score = formatScore(entry.gw, entry.vp, entry.tp);
      const finals = entry.finals ? ` [${entry.finals}]` : "";
      lines.push(`#${entry.rank} ${name} \u2014 ${score}${finals}`);
    }
    lines.push("");
  }

  // Winner's decklist
  if (tournament.winner && tournament.decks) {
    const winnerDecks = tournament.decks[tournament.winner];
    if (winnerDecks?.length) {
      const deck = winnerDecks[winnerDecks.length - 1]!;
      if (Object.keys(deck.cards).length > 0) {
        const cardsMap = await getCards();
        const winnerName = seatDisplay(tournament.winner, playerInfo);
        lines.push(`\u{1F0CF} ${winnerName}'s deck:`);
        lines.push(...formatDeckText(deck, cardsMap));
      }
    }
  }

  // Event link
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "https://archon.vekn.net";
  lines.push(`${baseUrl}/tournaments/${tournament.uid}`);

  return lines.join("\n");
}
