# ES judges guide — how the markdown was produced

Source: `ES - VEKN TOURNAMENT CONDUCT AND INFRACTION GUIDE.rtf`, the VEKN-supplied
Spanish translation (a Google Docs export). Left untracked — it is 7.5 MB of RTF
and only an input. Ask the owner for it before attempting a refresh.

The RTF carries no heading semantics, so the English file's outline is the
structural template: its 64 headings minus the H1 map 1:1, in order, onto the 63
entries of the Spanish document's own table of contents. That correspondence is
what makes the conversion mechanical rather than a judgement call, and it is
worth re-checking first on any refresh — if the counts diverge, the two documents
are no longer the same revision.

Pipeline (scripts were throwaway; they lived in the session scratch dir):

1. `pandoc -f rtf -t markdown --wrap=none` — clean prose, no headings.
2. Parse the TOC link-fragment lines into an ordered list of Spanish titles;
   assert the count matches the English outline; walk the body promoting each
   matched bold line to the English heading's level.
3. Normalise to house style: `---` → `—`, pandoc `- ` bullets → `* ` (4-space
   nesting), lettered/roman example lists → bullets, standalone `N.  **Label**`
   → bold labels (the RTF restarted their numbering anyway), and the appendix
   simple-table → a GFM pipe table.

## Defects fixed against the supplied translation

Flagged rather than silently absorbed, because the RTF is the source of truth:

- §1.1 heading was still English ("Definition of Penalties").
- §1.4.2's fifth principle had an untranslated English body paragraph.
- §3.7's two severity bullets were untranslated English.
- `V:EKN` → `VEKN` (the English file normalised this).
- Two cross-references named "1.2.4. Directrices para la concesión de
  ampliaciones de tiempo"; the section is titled "1.2.4. Directrices para
  prorrogar partidas".
- "prorroga" → "prórroga" inside a quoted announcement.

## Rendering notes

`preprocessDocument` auto-promotes standalone `**Bold**` lines to h5, so the
escalation sequence line had to lose its bold to stay a paragraph (as in the
English file). `(véase ...)` now auto-links alongside `(see ...)`; 5 of the 8
Spanish cross-references resolve, the rest name no exact heading.

Slugs drop accents (`slugify` strips non-`\w`), so §1.3 anchors as
`#13-aleatorizacin-de-la-biblioteca`. Ugly but self-consistent — the TOC is built
from the rendered ids — so links work. Verified in a production build: 248
anchors, none broken.
