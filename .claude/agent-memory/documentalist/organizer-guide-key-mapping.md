---
name: organizer-guide-key-mapping
description: The organizer in-app guide is many og_* keys in frontend/messages/en.json rendered in a fixed order by OrganizerGuide.svelte — a topic's actual text often lives under a different key than the one a task description names.
metadata:
  type: feedback
---

When a task names a specific `og_*` key as "the organizer guide" section to update,
verify the key actually contains that content before editing — don't trust the name.

**Why**: asked to update TWDA-auto-submission copy in `og_reference`, that key turned
out to be only the Archon Import / Leagues / Seating-Rules-Reference appendix, plus a
bare `## FAQ` heading with no body (the FAQ Q&A itself renders from separate
`og_faq_q_*`/`og_faq_a_*` key pairs in `OrganizerGuide.svelte`, not from `og_reference`
markdown). The actual TWDA text lived in `og_finals_toss` ("Finishing the Tournament"
list) and `og_faq_a_vekn_push` (FAQ answer) — two unrelated-sounding keys.

**How to apply**: `frontend/src/lib/components/help/OrganizerGuide.svelte` lists every
`og_*` section key in render order (`{@html renderGuideSection(m.og_xxx())}` calls) plus
the `faqs` array mapping `og_faq_q_*`/`og_faq_a_*` pairs. To find where a topic is
actually documented, `grep -i <topic>` across `en.json` values directly (e.g. via a
small Python json.load) rather than assuming the key name given in a task description —
then cross-check against this file's render list to confirm which key renders where in
the page. Same caution likely applies to the parallel player-facing guide keys if one
exists (check for a `pg_*`/similar prefix before assuming `og_*` is the only guide).
