import { renderDocument } from "$lib/markdown";
import * as m from "$lib/paraglide/messages.js";
import { getLocale } from "$lib/paraglide/runtime.js";

// Import markdown files as raw strings (bundled into JS, works offline)
import vtesRulesRaw from "$lib/help-content/vtes-rules.md?raw";
import tournamentRulesRaw from "$lib/help-content/tournament-rules.md?raw";
import judgesGuideRaw from "$lib/help-content/judges-guide.md?raw";
import judgesGuideEsRaw from "$lib/help-content/judges-guide.es.md?raw";
import codeOfEthicsRaw from "$lib/help-content/code-of-ethics.md?raw";

// Translated reference docs, by slug then locale. A static import (not a dynamic
// one) on purpose: the service worker precaches every built chunk at install, so
// splitting these out would still download them — it would only add machinery.
const translations: Record<string, Record<string, string>> = {
  "judges-guide": { es: judgesGuideEsRaw },
};

function localized(slug: string, fallback: string): string {
  return translations[slug]?.[getLocale()] ?? fallback;
}

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
  const key = `${slug}:${getLocale()}`;
  if (!renderCache.has(key)) {
    renderCache.set(key, renderDocument(raw));
  }
  return renderCache.get(key)!;
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
    get raw() { return localized("judges-guide", judgesGuideRaw); },
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
