import { renderDocument } from "$lib/markdown";

// Import markdown files as raw strings (bundled into JS, works offline)
import vtesRulesRaw from "../../../reference/vtes-rules.md?raw";
import tournamentRulesRaw from "../../../reference/tournament-rules.md?raw";
import judgesGuideRaw from "../../../reference/judges-guide-v2.md?raw";
import codeOfEthicsRaw from "../../../reference/code-of-ethics.md?raw";
import playerGuideRaw from "$lib/help-content/player-guide.md?raw";
import organizerGuideRaw from "$lib/help-content/organizer-guide.md?raw";

export interface TocEntry {
  id: string;
  text: string;
  depth: number;
}

export interface HelpDoc {
  title: string;
  description: string;
  icon: string;
  tocDepth: number;
  content: string; // rendered HTML (lazy)
  raw: string;
}

/** Extract table of contents entries from rendered HTML */
export function extractToc(html: string, maxDepth: number): TocEntry[] {
  const entries: TocEntry[] = [];
  const regex = /<h([1-4])\s+id="([^"]+)"[^>]*>([^<]*(?:<[^/][^>]*>[^<]*<\/[^>]+>)*[^<]*)/g;
  let match;
  while ((match = regex.exec(html)) !== null) {
    const depth = parseInt(match[1]!);
    if (depth > maxDepth) continue;
    const id = match[2]!;
    // Strip HTML tags and decode entities from the heading text, remove trailing # anchor
    let text = match[3]!.replace(/<[^>]*>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/\s*#\s*$/, "").trim();
    // Shorten "2.3. Procedural Error — Game Rule Violation" to "2.3. Game Rule Violation"
    text = text.replace(/^(\d[\d.]*\.\s+).+?\s—\s+/, "$1");
    if (text) entries.push({ id, text, depth });
  }
  return entries;
}

// Lazy-render cache
const renderCache = new Map<string, string>();
function getRendered(slug: string, raw: string): string {
  if (!renderCache.has(slug)) {
    renderCache.set(slug, renderDocument(raw));
  }
  return renderCache.get(slug)!;
}

export const helpDocs: Record<string, HelpDoc> = {
  rules: {
    title: "VTES Comprehensive Rules",
    description: "The complete official rules for Vampire: The Eternal Struggle.",
    icon: "book",
    tocDepth: 3,
    raw: vtesRulesRaw,
    get content() { return getRendered("rules", this.raw); },
  },
  "tournament-rules": {
    title: "Tournament Rules",
    description: "Official VEKN tournament rules and procedures.",
    icon: "trophy",
    tocDepth: 2,
    raw: tournamentRulesRaw,
    get content() { return getRendered("tournament-rules", this.raw); },
  },
  "judges-guide": {
    title: "Judges Guide",
    description: "Tournament conduct and infraction guide for judges.",
    icon: "scale",
    tocDepth: 3,
    raw: judgesGuideRaw,
    get content() { return getRendered("judges-guide", this.raw); },
  },
  "code-of-ethics": {
    title: "Code of Ethics",
    description: "VEKN Code of Ethics for players and organizers.",
    icon: "shield",
    tocDepth: 2,
    raw: codeOfEthicsRaw,
    get content() { return getRendered("code-of-ethics", this.raw); },
  },
  "player-guide": {
    title: "Player Guide",
    description: "How to find tournaments, register, check in, and upload decks.",
    icon: "user",
    tocDepth: 2,
    raw: playerGuideRaw,
    get content() { return getRendered("player-guide", this.raw); },
  },
  "organizer-guide": {
    title: "Organizer Guide",
    description: "How to create, configure, and run tournaments with Archon.",
    icon: "clipboard",
    tocDepth: 2,
    raw: organizerGuideRaw,
    get content() { return getRendered("organizer-guide", this.raw); },
  },
};

/** Ordered list of reference doc slugs */
export const referenceDocs = ["rules", "tournament-rules", "judges-guide", "code-of-ethics"];

/** Ordered list of user guide slugs */
export const userGuides = ["player-guide", "organizer-guide"];
