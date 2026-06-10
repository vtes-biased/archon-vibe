---
name: no-lineclamp-on-markdown
description: Never clamp rendered-markdown HTML with line-clamp-N; derive a plain-text excerpt from the markdown source instead
metadata:
  type: feedback
---

Do not wrap `{@html renderMarkdown(...)}` in Tailwind `line-clamp-N` (or raw `-webkit-line-clamp`) to make a collapsed/teaser preview. For a folded preview, derive a **plain-text excerpt from the markdown source** and render that.

**Why:** `-webkit-line-clamp` only clamps a single inline formatting context. `renderMarkdown` emits block-level siblings (`<p>`, `<h2>`, `<ul>`, `<blockquote>`), so the clamp applies to the block container, not the lines — result is a hard `overflow:hidden` cut mid-element, no ellipsis, and full-size headings rendered inside what should be a 2-3 line teaser. Reported on the tournament description card.

**How to apply:** Excerpt heuristic that works for event-description-shaped text (often opens with a heading, then venue/schedule): skip leading blank+heading lines → take the first paragraph (stop at first blank line) → strip inline markdown (`[t](u)`→`t`, drop images, strip `*_\`~`) → cap ~140 chars on a word boundary. Return a `truncated` flag and only show the `…`/expand affordance when actually truncated. Keep the helper in `tournament-utils.ts` next to `stripLeadingTitle` (locality). The expanded state keeps full `renderMarkdown`. While touching a disclosure button, also add `aria-expanded` and `aria-hidden="true"` on decorative chevrons. `line-clamp-N` on genuinely **plain** text is fine; it's only markdown HTML that breaks. See [[no-impossible-state-tests]] only loosely related — this is a UI-rendering trap, not a test one.
