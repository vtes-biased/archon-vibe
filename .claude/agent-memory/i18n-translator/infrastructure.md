---
name: infrastructure
description: Translation file locations, key ordering, key naming conventions, and the bulk-translation workflow/commands
metadata:
  type: project
---

## Translation Infrastructure
- Files: `frontend/messages/{en,fr,es,pt,it}.json` — flat JSON, one key per string. No plurals/interpolation system; English copy must hand-pluralize (`{count} round(s)`).
- Key order in every locale follows `en.json` (source of truth): insert a new key immediately after the same preceding key as in en.json.
- `en.json` exceeds the 25k-token read limit — extract keys via `python3` or read with offset+limit.

## Key Naming Conventions
- `nav_*` nav · `profile_*` profile · `help_*` help/docs · `common_*` shared · `offline_*` offline mode · `checkin_qr_*` QR check-in
- `tournament_*`/`tournaments_*` + sub-sections `rounds_*`, `finals_*`, `decks_*`, `players_*`
- `sanction_*`/`sanction_mgr_*` sanctions
- Help guides: `pg_*` Player Guide · `og_*` Organizer Guide (`og_cfg_*` config-tab, `og_faq_q_*`/`og_faq_a_*` FAQ) · `help_player_guide_*`/`help_organizer_guide_*` index entries
- Verified help strings: `help_toc_title` (fr Sommaire/es Contenido/pt Sumário/it Indice); `help_back_to_list` (fr Retour à l'aide/es Volver a la ayuda/pt Voltar à ajuda/it Torna alla guida); `nav_help` (fr Aide/es Ayuda/pt Ajuda/it Guida)

## Bulk Translation Workflow
1. Missing keys: `python3 -c "import json; en=json.load(open('en.json')); xx=json.load(open('xx.json')); print([k for k in en if k not in xx])"`
2. Build translations dict, `xx.update(translations)`, write with `json.dump(..., ensure_ascii=False, indent=2)` + trailing `'\n'`
3. Validate: `python3 -c "import json; json.load(open('xx.json')); print('ok')"`
4. Compile + check: `npx @inlang/paraglide-js compile --project project.inlang --outdir src/lib/paraglide` then `npm run check`
5. To edit one paragraph inside a long markdown string safely (e.g. `og_finals_toss`, `og_force_takeover`): `txt.split('\n\n')` gives numbered segments (headings and paragraphs are separated by blank lines) — print them, find the target index, replace `segs[i]`, rejoin with `'\n\n'`. The segment split is stable across en/fr/es/pt/it since structure (heading/paragraph/list count) mirrors the source even when wording differs — safer than manual multi-line string matching for markdown bodies. Checked 2026-07-12 on a 4-locale `og_finals_toss` edit (15 segments each).
6. **Inserting a new key cluster: do NOT rebuild the whole file in en.json's key order.** Some locale files have a small pre-existing key-order drift vs en.json in unrelated spots (found 2026-07-17: `tournament_registered_players`/`tournament_winner` and `overview_reopen_registration`/`overview_finals_manage` sit in a different relative order than en.json, identically in all 4 locale files — a pre-existing gap, not something to silently fix). A full `for k in en: rebuilt[k] = ...` rebuild "fixes" that drift as an unwanted side effect and produces a diff that touches unrelated lines, violating a "don't touch other keys" instruction. Instead: iterate the locale file's own existing dict, copy every key through unchanged, and splice the new cluster in right after the anchor key (the key that immediately precedes the new cluster in en.json — confirm first that this anchor key is adjacent to the following pre-existing key in the *locale* file too, e.g. via `keys.index(anchor)+1 == keys.index(next_key)`). This yields a purely-additive diff (only `+` lines). Verify with `git diff --stat` showing 0 deletions before compiling.

See also: [[tone_register]], [[glossary]], [[glossary_conventions]].
