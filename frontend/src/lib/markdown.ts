import { marked, type Tokens } from "marked";
import DOMPurify from "dompurify";

export function renderMarkdown(src: string): string {
  const renderer = new marked.Renderer();
  renderer.link = ({ href, text }: Tokens.Link) =>
    `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  const raw = marked.parse(src, { renderer, async: false }) as string;
  return DOMPurify.sanitize(raw, { ADD_ATTR: ["target", "rel"] });
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/<[^>]*>/g, "")
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

function preprocessDocument(src: string): string {
  let cleaned = src.replace(/^(#{1,6}\s+.*?)\s*\{#[^}]+\}\s*$/gm, "$1");

  // Promotes standalone bold-paragraph titles to h5 so they get anchor IDs.
  cleaned = cleaned.replace(/^(\*\*[^*]+\*\*)\s*$/gm, "##### $1");

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

  cleaned = cleaned.replace(/^#{1,6}\s*$/gm, "");

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
    const hMatch = line.match(/^#{1,6}\s+\**(.+?)\**\s*$/);
    if (hMatch) { indexTitle(hMatch[1]!); continue; }
    const bMatch = line.match(/^\*\*([^*]+)\*\*\s*$/);
    if (bMatch) { indexTitle(bMatch[1]!); }
  }
  // Replace (see Title)/(véase Title) cross-references with linked versions. Both languages prefix the
  // title with a section word that must come off before the lookup but stay in the visible link text.
  cleaned = cleaned.replace(
    /\((see|véase) ((?:(?:el|la)\s+)?(?:section|secci[óo]n|apartado)\s+)?([^)[\]]+?)(?:,\s*p\.\s*\d+)?\)/gi,
    (_full, verb: string, prefix: string | undefined, ref: string) => {
      const lead = `${verb} ${prefix ?? ""}`;
      const text = ref.trim();
      const refLower = text.replace(/\*\*/g, "").toLowerCase();
      const slug = headingIndex.get(refLower);
      if (slug) {
        return `(${lead}[${text}](#${slug}))`;
      }
      const parts = text.split(",").map(p => p.trim());
      if (parts.length > 1) {
        const linked = parts.map(part => {
          const partSlug = headingIndex.get(part.replace(/\*\*/g, "").toLowerCase());
          return partSlug ? `[${part}](#${partSlug})` : part;
        });
        return `(${lead}${linked.join(", ")})`;
      }
      return _full;
    }
  );

  return cleaned;
}

export function renderDocument(src: string): string {
  const preprocessed = preprocessDocument(src);
  const renderer = new marked.Renderer();

  const idSet = new Set<string>();
  const aliasMap = new Map<string, string>(); // broken slug → actual id

  renderer.heading = ({ tokens, depth }: Tokens.Heading) => {
    const text = tokens.map(t => ('text' in t ? (t as any).text : t.raw)).join("");
    const id = slugify(text);
    idSet.add(id);
    const stripped = id.replace(/^\d+-/, "");
    if (stripped !== id) aliasMap.set(stripped, id);
    const inner = marked.parser([{ type: "heading", depth, raw: "", text: "", tokens }] as any, { async: false }) as string;
    const match = inner.match(/<h\d[^>]*>([\s\S]*?)<\/h\d>/);
    const content = match ? match[1] : text;
    return `<h${depth} id="${id}" class="heading-anchor">` +
      `${content} <a href="#${id}" class="anchor-link" aria-label="Link to this section">#</a>` +
      `</h${depth}>\n`;
  };

  renderer.blockquote = ({ tokens }: Tokens.Blockquote) => {
    const html = marked.parser(tokens as any, { async: false }) as string;
    const calloutMatch = html.match(/^<p>\s*<strong>([A-Z][A-Z\s&:,\-]+)<\/strong>/);
    if (calloutMatch) {
      let title = calloutMatch[1]!.trim();
      let body = html.replace(calloutMatch[0], "<p>");
      // Strip leading <br> tags from body (from > \ blank lines in source)
      body = body.replace(/^(<p>)\s*(?:<br\s*\/?>[\s\n]*)*/i, "$1");
      const subMatch = body.match(/^<p>\s*<strong>([^<]+)<\/strong>/);
      if (subMatch) {
        title += ` — ${subMatch[1]!.trim()}`;
        body = body.replace(subMatch[0], "<p>");
        body = body.replace(/^(<p>)\s*(?:<br\s*\/?>[\s\n]*)*/i, "$1");
      }
      const calloutId = slugify(title);
      idSet.add(calloutId);
      // The subtitle was folded into the callout title, so its own slug now matches no element — but
      // that's the name cross-references use ("(see Sequencing)"), so keep it reachable.
      if (subMatch) aliasMap.set(slugify(subMatch[1]!.trim()), calloutId);
      return `<div class="callout" id="${calloutId}"><div class="callout-title">${title} <a href="#${calloutId}" class="anchor-link" aria-label="Link to this section">#</a></div>${body}</div>\n`;
    }
    return `<blockquote>${html}</blockquote>\n`;
  };

  renderer.image = ({ href, title, text }: Tokens.Image) => {
    const titleAttr = title ? ` title="${title}"` : "";
    return `<img src="${href}" alt="${text}" class="doc-img"${titleAttr} />`;
  };

  let html = marked.parse(preprocessed, { renderer, async: false }) as string;

  // Adds anchor IDs to bold <strong>Term</strong> definitions that cross-reference links target but
  // have no heading of their own.
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

/** Lighter than renderDocument: heading anchors + callouts, no preprocessing. */
export function renderGuideSection(src: string): string {
  const renderer = new marked.Renderer();
  renderer.heading = ({ tokens, depth }: Tokens.Heading) => {
    const text = tokens.map(t => ('text' in t ? (t as any).text : t.raw)).join("");
    // A translated heading slugifies to a translated id, so every locale would need
    // its own spelling of every `](#anchor)`. `{#id}` pins one id across all of them.
    const pinned = text.match(/\s*\{#([\w-]+)\}\s*$/);
    const title = pinned ? text.slice(0, pinned.index) : text;
    const id = pinned ? pinned[1]! : slugify(title);
    const inner = marked.parser(
      [{ type: "heading", depth, raw: "", text: "", tokens }] as any,
      { async: false }
    ) as string;
    const match = inner.match(/<h\d[^>]*>([\s\S]*?)<\/h\d>/);
    const content = (match ? match[1]! : title).replace(/\s*\{#[\w-]+\}\s*$/, "");
    return `<h${depth} id="${id}" class="heading-anchor">${content} <a href="#${id}" class="anchor-link" aria-label="Link to this section">#</a></h${depth}>\n`;
  };
  renderer.blockquote = ({ tokens }: Tokens.Blockquote) => {
    const html = marked.parser(tokens as any, { async: false }) as string;
    const calloutMatch = html.match(/^<p>\s*<strong>([A-Z][A-Z\s&:,\-]+)<\/strong>/);
    if (calloutMatch) {
      const title = calloutMatch[1]!.trim();
      const body = html.replace(calloutMatch[0], "<p>");
      return `<div class="callout"><div class="callout-title">${title}</div>${body}</div>\n`;
    }
    return `<blockquote>${html}</blockquote>\n`;
  };
  renderer.link = ({ href, text }: Tokens.Link) =>
    href.startsWith("/") || href.startsWith("#")
      ? `<a href="${href}">${text}</a>`
      : `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`;
  return marked.parse(src.trim(), { renderer, async: false }) as string;
}

/** Strip a leading markdown title (`# Title`) when it matches `name` (case-insensitive). */
export function stripLeadingTitle(description: string, name: string): string {
  const lines = description.split('\n');
  if (lines.length === 0) return description;
  const first = lines[0]!.trim();
  if (first.startsWith('#')) {
    const titleText = first.replace(/^#+\s*/, '').trim();
    if (titleText.toLowerCase() === name.toLowerCase()) {
      const rest = lines.slice(1).join('\n').trimStart();
      return rest || description;
    }
  }
  return description;
}

/** Plain-text teaser for a markdown description, derived from the source (rendered HTML breaks
 * -webkit-line-clamp, which needs inline content). Skips a leading heading; `truncated` is true only if something was actually hidden. */
export function descriptionExcerpt(md: string, maxChars = 140): { text: string; truncated: boolean } {
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  let i = 0;
  let heading = '';
  while (i < lines.length && lines[i]!.trim() === '') i++;
  if (i < lines.length && /^#{1,6}\s/.test(lines[i]!.trim())) {
    heading = lines[i]!.trim().replace(/^#+\s*/, '');
    i++;
    while (i < lines.length && lines[i]!.trim() === '') i++;
  }
  const para: string[] = [];
  while (i < lines.length && lines[i]!.trim() !== '') para.push(lines[i++]!.trim());
  if (!para.length && heading) para.push(heading); // heading-only description
  const hasMore = lines.slice(i).some(l => l.trim() !== '');
  let text = para.join(' ')
    .replace(/^#{1,6}\s+/, '')                // stray heading marks
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')     // images: drop
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')  // links: keep label
    .replace(/[*_`~]/g, '')                   // emphasis/code marks
    .replace(/\s+/g, ' ')
    .trim();
  let truncated = hasMore;
  if (text.length > maxChars) {
    const cut = text.slice(0, maxChars);
    const sp = cut.lastIndexOf(' ');
    text = (sp > 0 ? cut.slice(0, sp) : cut).trimEnd();
    truncated = true;
  }
  return { text, truncated };
}
