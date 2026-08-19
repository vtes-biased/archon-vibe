import type { Tournament, Deck, DeckObject, VtesCard } from "$lib/types";
import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
import { eventUrl, seatDisplay } from "$lib/tournament-utils";
import { formatScore } from "$lib/utils";
import { getCountry } from "$lib/geonames";
import { getCards } from "$lib/cards";
import { getLibraryTypeOrder } from "$lib/engine";
import { getDecksByTournamentGrouped } from "$lib/db";
import { getLocale } from "$lib/paraglide/runtime.js";
import * as m from "$lib/paraglide/messages.js";

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
    const entry = { name: card.unique_name, count, type: card.types[0] ?? "", capacity: card.capacity };
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

  if (library.length) {
    lines.push(`Library (${libTotal})`);
    const groups: Record<string, CardEntry[]> = {};
    for (const c of library) (groups[c.type] ??= []).push(c);
    const order = getLibraryTypeOrder();
    const sorted = Object.entries(groups).sort(([a], [b]) => {
      const ai = order.indexOf(a);
      const bi = order.indexOf(b);
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
  playerInfo: PlayerInfoMap,
  standings: StandingEntry[],
): Promise<string> {
  const lines: string[] = [];

  lines.push(`\u{1F3C6} ${tournament.name}`);

  const parts: string[] = [];
  if (tournament.start) {
    const d = new Date(tournament.start);
    parts.push(d.toLocaleDateString(getLocale(), { year: "numeric", month: "long", day: "numeric" }));
  }
  if (tournament.country) {
    const c = getCountry(tournament.country);
    if (c) parts.push(c.name);
  }
  if (parts.length) lines.push(`\u{1F4C5} ${parts.join(" \u00B7 ")}`);

  const typeParts: string[] = [];
  if (tournament.format) typeParts.push(tournament.format);
  if (tournament.rank) typeParts.push(tournament.rank);
  if (typeParts.length) lines.push(typeParts.join(" \u00B7 "));

  const playerCount = tournament.players?.length ?? 0;
  if (playerCount > 0) lines.push(m.players_count({ count: String(playerCount) }));

  lines.push("");

  if (tournament.winner) {
    const winnerName = seatDisplay(tournament.winner, playerInfo, tournament.online);
    const winnerEntry = standings.find((e) => e.user_uid === tournament.winner);
    const score = winnerEntry ? ` \u2014 ${formatScore(winnerEntry.gw, winnerEntry.vp, winnerEntry.tp)}` : "";
    lines.push(`\u{1F947} ${m.tournament_winner()}: ${winnerName}${score}`);
    lines.push("");
  }

  if (standings.length > 0) {
    lines.push(`${m.tournament_standings()}:`);
    for (const entry of standings) {
      const name = seatDisplay(entry.user_uid, playerInfo, tournament.online);
      const score = formatScore(entry.gw, entry.vp, entry.tp);
      const finals = entry.finals ? ` [${entry.finals}]` : "";
      lines.push(`#${entry.rank} ${name} \u2014 ${score}${finals}`);
    }
    lines.push("");
  }

  if (tournament.winner) {
    const decksByUser = await getDecksByTournamentGrouped(tournament.uid);
    const winnerDecks = decksByUser[tournament.winner];
    if (winnerDecks?.length) {
      const deck = winnerDecks[winnerDecks.length - 1]!;
      if (Object.keys(deck.cards).length > 0) {
        const cardsMap = await getCards();
        const winnerName = seatDisplay(tournament.winner, playerInfo, tournament.online);
        // The decklist itself stays in TWDA English convention (card names,
        // Crypt/Library headers) — only the prose heading is localized.
        lines.push(`\u{1F0CF} ${m.share_text_deck_heading({ name: winnerName })}`);
        lines.push(...formatDeckText(deck, cardsMap));
      }
    }
  }

  const baseUrl = typeof window !== "undefined" ? window.location.origin : "https://archon.vekn.net";
  lines.push(eventUrl(baseUrl, tournament));

  return lines.join("\n");
}
