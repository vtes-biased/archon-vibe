import { renderDocument } from "$lib/markdown";
import * as m from "$lib/paraglide/messages.js";

// Import markdown files as raw strings (bundled into JS, works offline)
import vtesRulesRaw from "$lib/help-content/vtes-rules.md?raw";
import tournamentRulesRaw from "$lib/help-content/tournament-rules.md?raw";
import judgesGuideRaw from "$lib/help-content/judges-guide.md?raw";
import codeOfEthicsRaw from "$lib/help-content/code-of-ethics.md?raw";

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
  content: string; // rendered HTML (lazy, empty for component docs)
  raw: string; // raw markdown (empty for component docs)
  isComponent?: boolean; // true if rendered by a Svelte component
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
    get title() { return m.help_player_guide_title(); },
    get description() { return m.help_player_guide_description(); },
    icon: "user",
    tocDepth: 2,
    isComponent: true,
    raw: "",
    get content() { return ""; },
  },
  "organizer-guide": {
    get title() { return m.help_organizer_guide_title(); },
    get description() { return m.help_organizer_guide_description(); },
    icon: "clipboard",
    tocDepth: 2,
    isComponent: true,
    raw: "",
    get content() { return ""; },
  },
};

/** Ordered list of reference doc slugs */
export const referenceDocs = ["rules", "tournament-rules", "judges-guide", "code-of-ethics"];

/** Ordered list of user guide slugs */
export const userGuides = ["player-guide", "organizer-guide"];
