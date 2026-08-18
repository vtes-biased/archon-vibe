import changelogRaw from "../../../CHANGELOG.md?raw";

const SEEN_KEY = "changelog-seen";

export interface ChangelogEntry {
  version: string;
  date: string;
  body: string;
}

// `just release` stamps `## Unreleased` into exactly this shape; it verifies its own
// write against the same pattern.
const ENTRY_HEADING = /^## v(\d+\.\d+\.\d+) — (\d{4}-\d{2}-\d{2})\s*$/gm;

function compareVersions(a: string, b: string): number {
  const left = a.split(".").map(Number);
  const right = b.split(".").map(Number);
  for (let i = 0; i < 3; i++) {
    const diff = (left[i] ?? 0) - (right[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function parse(raw: string): ChangelogEntry[] {
  const headings = [...raw.matchAll(ENTRY_HEADING)];
  return headings
    .map((heading, i) => ({
      version: heading[1]!,
      date: heading[2]!,
      body: raw.slice(heading.index + heading[0].length, headings[i + 1]?.index ?? raw.length).trim(),
    }))
    .sort((a, b) => compareVersions(b.version, a.version));
}

const entries = parse(changelogRaw);

function readSeen(): string | null {
  try {
    return localStorage.getItem(SEEN_KEY);
  } catch {
    return null;
  }
}

export function unseenEntries(): ChangelogEntry[] {
  const seen = readSeen();
  if (seen === null) {
    markSeen();
    return [];
  }
  return entries.filter((entry) => compareVersions(entry.version, seen) > 0);
}

export function markSeen(): void {
  const newest = entries[0]?.version;
  if (!newest) return;
  try {
    localStorage.setItem(SEEN_KEY, newest);
  } catch {
    /* storage unavailable — reads then look like a first visit, so nothing ever shows */
  }
}
