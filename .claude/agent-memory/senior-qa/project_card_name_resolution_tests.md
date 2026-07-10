---
name: card-name-resolution-tests
description: Where card-name resolution logic is tested (fold/disambiguation), the inline-fixture pattern, and the untested fold branch (non-NFD-decomposing letters).
metadata:
  type: project
---

Card-name resolution (offline text importer + frontend, shared `engine/data/cards.json`)
lives in the Rust engine, tested with **inline JSON fixtures** (never the real
`cards.json` — it is a daily-CI build artifact, so pinning to a specific card id/name
would drift). Post-krcg three-name schema (commit 9fe99d6): each card carries
`printed_name` / `unique_name` / `full_name`; the name index folds+normalizes all three
plus `name_variants`.

**Why:** future card-DB QA (epic #476 has more children — #478 pending) keeps landing
in these two files; knowing the topology avoids re-deriving it.

**How to apply:**
- Accent folding: `cards.rs::normalize_name` → `fold_ascii`. Two mechanisms: (a) NFD
  decompose + drop combining marks, (b) a hand-written arm-per-letter map for letters
  that DON'T decompose under NFD (ł, ø, đ/ð, ħ, ı, ŧ, æ→ae, œ→oe, þ→th, ß→ss). Test
  `test_accent_folding` only exercises (a) via "François". The (b) branch guards **12
  real cards** (ł×6 e.g. "Bolesław Gutowski", ø×3 e.g. "Clara Hjortshøj", œ×3 e.g.
  "Sacré-Cœur Cathedral") yet is **untested** — a "simplify to just NFD/unidecode"
  refactor would silently break accent-free import of those cards (the exact failure
  this epic exists to fix; measured 73→0 fold misses). Mutation-confirmed: dropping the
  `'ł'` arm makes `by_name("Boleslaw Gutowski")` miss. Recommended fix: one added
  assertion in `test_accent_folding` for a ł-bearing card — not per-letter tests.
- ADV/group disambiguation: `cards.rs::name_pref` (bare name → non-adv lowest-id) is
  covered by `test_ambiguous_bare_name_prefers_nonadv_first_release` (Theo Bell
  G2/G2ADV/G6); crypt-tail group hint (`by_name_in_group`, "Clan:N" tail) by
  `deck.rs::test_crypt_tail_group_disambiguates_multigroup_vampire` (Annabelle G3/G6).
  Both exercise the unique_name/full_name qualified keys — three-name resolution is
  covered; no new test warranted there.
- Count parser (leading `x2`/`xx2`, X-named crypt cards): `deck.rs::try_count_first`,
  covered by `test_count_marker_keeps_x_name` + the X-name test. Green.
