import { marked, type Tokens } from "marked";
import DOMPurify from "dompurify";

export function renderMarkdown(src: string): string {
  const raw = marked.parse(src, { async: false }) as string;
  return DOMPurify.sanitize(raw);
}

/** Slugify a heading text into a URL-friendly id */
function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]*>/g, "")
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

/**
 * Pre-process markdown source to clean up patterns from upstream documents:
 * - Strip {#anchor-id} suffixes from headings (Pandoc-style anchors)
 * - Strip leading TOC sections (blocks of [text](#anchor) lines)
 */
function preprocessDocument(src: string): string {
  // Strip {#anchor-id} from headings
  let cleaned = src.replace(/^(#{1,6}\s+.*?)\s*\{#[^}]+\}\s*$/gm, "$1");

  // Promote standalone bold-paragraph titles to h5 headings so they get anchor IDs
  // e.g. **Play Area** (alone on a line) → ##### **Play Area**
  cleaned = cleaned.replace(/^(\*\*[^*]+\*\*)\s*$/gm, "##### $1");

  // Strip leading TOC: detect a block of lines that are all [text](#anchor)
  // preceded by a "Table of Contents" header
  const lines = cleaned.split("\n");
  let tocStart = -1;
  let tocEnd = -1;
  for (let i = 0; i < Math.min(lines.length, 10); i++) {
    if (/table of contents/i.test(lines[i]!)) {
      tocStart = i;
      break;
    }
  }
  if (tocStart >= 0) {
    // Find the end of the TOC block: consecutive lines that are blank or [text](#...)
    for (let i = tocStart + 1; i < lines.length; i++) {
      const line = lines[i]!.trim();
      if (line === "" || /^\[.*\]\(#/.test(line)) {
        tocEnd = i;
      } else {
        break;
      }
    }
    if (tocEnd > tocStart) {
      lines.splice(tocStart, tocEnd - tocStart + 1);
      cleaned = lines.join("\n");
    }
  }

  // Strip empty headings (e.g. bare "# " lines)
  cleaned = cleaned.replace(/^#{1,6}\s*$/gm, "");

  // Auto-link plain-text cross-references like (see Section Name)
  // Build index: heading text → slug (from markdown headings and bold-paragraph titles)
  const headingIndex = new Map<string, string>();
  function indexTitle(raw: string) {
    const title = raw.replace(/\*\*/g, "").replace(/\\/g, "").trim();
    const slug = slugify(title);
    headingIndex.set(title.toLowerCase(), slug);
    // Also index without leading number prefix: "4. Detailed Turn Sequence" → "detailed turn sequence"
    const stripped = title.replace(/^\d+\.\s*/, "");
    if (stripped !== title) {
      headingIndex.set(stripped.toLowerCase(), slug);
    }
  }
  for (const line of cleaned.split("\n")) {
    // Markdown headings: # **Title** or ## Title
    const hMatch = line.match(/^#{1,6}\s+\**(.+?)\**\s*$/);
    if (hMatch) { indexTitle(hMatch[1]!); continue; }
    // Bold paragraph titles: **Title** (alone on a line, not part of a sentence)
    const bMatch = line.match(/^\*\*([^*]+)\*\*\s*$/);
    if (bMatch) { indexTitle(bMatch[1]!); }
  }
  // Replace (see Title) and (see Title, p. N) with linked versions
  cleaned = cleaned.replace(
    /\(see ([^)[\]]+?)(?:,\s*p\.\s*\d+)?\)/g,
    (_full, ref: string) => {
      // ref may be a comma-separated list: "Game Setup, Drawing cards and Influence Phase"
      // Try the full ref first, then individual parts
      const refLower = ref.trim().toLowerCase();
      const slug = headingIndex.get(refLower);
      if (slug) {
        return `(see [${ref.trim()}](#${slug}))`;
      }
      // Try splitting on comma and linking each part
      const parts = ref.split(",").map(p => p.trim());
      if (parts.length > 1) {
        const linked = parts.map(part => {
          const partSlug = headingIndex.get(part.toLowerCase());
          return partSlug ? `[${part}](#${partSlug})` : part;
        });
        return `(see ${linked.join(", ")})`;
      }
      return _full; // no match, leave as-is
    }
  );

  return cleaned;
}

/**
 * Render a long-form document with heading anchors, callout blockquotes,
 * and constrained images. Used for help/documentation pages.
 */
export function renderDocument(src: string): string {
  const preprocessed = preprocessDocument(src);
  const renderer = new marked.Renderer();

  // Collect all generated heading IDs + aliases for post-processing broken links
  const idSet = new Set<string>();
  const aliasMap = new Map<string, string>(); // broken slug → actual id

  // Heading anchors: generate id and anchor link
  renderer.heading = ({ tokens, depth }: Tokens.Heading) => {
    const text = tokens.map(t => ('text' in t ? (t as any).text : t.raw)).join("");
    const id = slugify(text);
    idSet.add(id);
    // Register aliases: strip number prefix ("2-master-phase" → "master-phase")
    const stripped = id.replace(/^\d+-/, "");
    if (stripped !== id) aliasMap.set(stripped, id);
    // Also alias lowercase normalization for ALL CAPS headings with word differences
    const inner = marked.parser([{ type: "heading", depth, raw: "", text: "", tokens }] as any, { async: false }) as string;
    // Extract inner HTML from the default heading tag
    const match = inner.match(/<h\d[^>]*>([\s\S]*?)<\/h\d>/);
    const content = match ? match[1] : text;
    return `<h${depth} id="${id}" class="heading-anchor">` +
      `${content} <a href="#${id}" class="anchor-link" aria-label="Link to this section">#</a>` +
      `</h${depth}>\n`;
  };

  // Callout blockquotes: detect blockquotes starting with **ALL CAPS TITLE**
  renderer.blockquote = ({ tokens }: Tokens.Blockquote) => {
    const html = marked.parser(tokens as any, { async: false }) as string;
    // Check if content starts with a bold ALL CAPS phrase
    const calloutMatch = html.match(/^<p>\s*<strong>([A-Z][A-Z\s&:,\-]+)<\/strong>/);
    if (calloutMatch) {
      let title = calloutMatch[1]!.trim();
      let body = html.replace(calloutMatch[0], "<p>");
      // Strip leading <br> tags from body (from > \ blank lines in source)
      body = body.replace(/^(<p>)\s*(?:<br\s*\/?>[\s\n]*)*/i, "$1");
      // Merge subtitle: if body starts with <strong>Subtitle</strong>, append to title
      const subMatch = body.match(/^<p>\s*<strong>([^<]+)<\/strong>/);
      if (subMatch) {
        title += ` — ${subMatch[1]!.trim()}`;
        body = body.replace(subMatch[0], "<p>");
        // Strip <br> again after subtitle extraction
        body = body.replace(/^(<p>)\s*(?:<br\s*\/?>[\s\n]*)*/i, "$1");
      }
      return `<div class="callout"><div class="callout-title">${title}</div>${body}</div>\n`;
    }
    return `<blockquote>${html}</blockquote>\n`;
  };

  // Image sizing: add doc-img class
  renderer.image = ({ href, title, text }: Tokens.Image) => {
    const titleAttr = title ? ` title="${title}"` : "";
    return `<img src="${href}" alt="${text}" class="doc-img"${titleAttr} />`;
  };

  let html = marked.parse(preprocessed, { renderer, async: false }) as string;

  // Post-process: add anchor IDs to bold definitions (<strong>Term</strong> or
  // <strong>Term:</strong>) that are targets of cross-reference links but have no heading
  html = html.replace(
    /<strong>([^<]+?)(:|\\)?<\/strong>/g,
    (_m, term: string, suffix: string) => {
      const termSlug = slugify(term);
      if (!idSet.has(termSlug)) {
        idSet.add(termSlug);
        return `<strong id="${termSlug}">${term}${suffix || ""}</strong>`;
      }
      return _m;
    }
  );

  // Post-process: fix broken internal links by remapping to alias targets or fuzzy match
  html = html.replace(
    /href="#([a-zA-Z][a-zA-Z0-9-]*)"/g,
    (_m, target: string) => {
      const lower = target.toLowerCase();
      if (idSet.has(lower)) return _m;
      const alias = aliasMap.get(lower);
      if (alias) return `href="#${alias}"`;
      // Fuzzy: find an ID that contains all the target's words (handles "of" vs "in" etc.)
      const words = lower.split("-").filter(Boolean);
      for (const id of idSet) {
        const idWords = id.split("-");
        if (words.length >= 2 && words.every(w => idWords.includes(w))) {
          return `href="#${id}"`;
        }
      }
      return _m;
    }
  );

  return DOMPurify.sanitize(html, {
    ADD_ATTR: ["id", "class", "aria-label"],
  });
}
