# VEKN decommission — evidence

The evidence for the work tied to retiring the VEKN syncs, kept because it cannot be
reconstructed afterwards. The asks themselves, their triggers and what each one owes
are in [`WATCH.md`](../WATCH.md).

The two stages are the retirement stages in [vekn](vekn.md#decommission), which is
where what retires and in what order is settled. Stage 1 (tournament calendar sync)
retired on 2026-11-24 and Stage 2 (member roster sync and push) retired on
2026-11-27; once deployed, the curation items below are locally actionable without
upstream re-creating deleted rows or overwriting corrections.

## Stage 1 — post-retirement tournament corpus curation

### Duplicate tournament cleanup

Resolved on prod **2026-11-28** after Stage 1 retired the tournament sync:

- **5 strong candidates soft-deleted** via `dedup_tournaments.py --apply` (no `vekn` id transplant — each survivor already held its real id + `twda_entry`/`archon`):
  `Itaquaquecetubense 2026` (kept `13478`, dropped `13477`), `5ª Jornada Liga Levante Norte` (kept `13151`, dropped `13152`), `Sangrando por un sueño` (kept `12972`, dropped `12971`), `Primeiro campeonato online Inconnu do home office` (kept `12979`, dropped `12931`), and `PennyBridge - Charisma III` (kept `13048`, dropped `13046`).
- **7 "Needs judgement" pairs confirmed distinct events** (both copies kept live):
  - Different cities or separate convention sessions with distinct TWDA entries: `Forced March` (`11252` Barberà del Vallès vs `11263` Madrid), `Origins Constructed` (`9188` 11:00 `2019oc1co` vs `9189` 16:00 `2019oc2co`), `V:TES Constructed Tournament` (`8896` 11:00 `2018ot1co` vs `8897` 16:00 `2018ot2co`), `Torneio Draft de Lords of the Night` (`2717` Rio de Janeiro vs `3270` Vitória).
  - Completely disjoint player rosters (`shared = 0` on prod): `Last Stand` (`5543` 7p vs `5700` 20p), `Praxis Seizure: Barcelona` (`1329` 21p vs `34` 35p), `Ropecon ECQ` (`5518` 35p vs `6067` 20p).
- **Shared `external_ids.vekn` blind spot:** verified **0** live tournaments share a `vekn` id on prod.
- **Deliberately excluded (unchanged):** 98 `Imported VTES Event` groups (2004–2005) and 70 groups over 4 copies (`PROBE_GROUP_CAP`) — placeholder-shaped distinct legacy events.

#### The day-boundary detection blind spot

`DUPLICATE_GROUPS_QUERY` (`backend/src/db.py`) groups on `lower(name)` + **exact
UTC start day**, so a duplicate pair straddling midnight (like `PennyBridge -
Charisma III`) is invisible to it. Widening to ±1 day is wrong because it flags
legitimate consecutive-day convention events (`Origins 9am`, `Czech Championship
2007`, etc.).

Ratings need no manual step after cleanup: `run_rating_recompute` runs daily.

### IC record curation — events to delete

Resolved on prod **2026-11-28** (all 4 listed rows deleted; `Arraial da Vampirada` was already gone and the 3 placeholder `Finished` rows `TEST` / `vekn=9955`, `delete me` / `vekn=12797`, and `ND` / `vekn=13235` were deleted by IC).

- **Kept intentionally:** `ebcfaea6-babb-4725-8fb4-4cc755bbfd9e` (`Test`, 2020-09-01 HR, 1p), `4218a3a4-0a2e-434a-be14-2d7135d10688` (`Test`, 2025-09-13 PT, 8p), and the five terse legacy names (`LoB`, `QCF` x2, `NA`, `Tournament`) which carry real rosters.

### IC record curation — rows that disagree with the archive about who won

Resolved on prod **2026-11-28**:

- `Matusalén,¿dónde está mi promo?` (`019f1a1a-1923-766f-bba2-ae0291673caa`, 2023-10-22): already matched archive (`Ginés Quiñonero`).
- `Roundhouse` (`019f1a19-a603-773a-a922-d6dbe2146b47`, 2021-09-19): both `Joab Rogerio Barbosa da Silva` (2 GW 9 VP) and `José Roberio Barbosa da Silva` (1 GW 4 VP) were finalists; switched winner to `José Roberio Barbosa da Silva` (TWDA `9888`) and re-imported the winning deck under him.
- `Minion Tap Newark` (`019f1a06-a7d1-711f-b9c6-4e6f4c6ee2c9`, 2008-02-24, gh-57): cleared `winner` to empty (`Karl Schaefer` disputed winning; real winner unknown).

### Archive reconstructions of an event we already hold

Resolved on prod **2026-11-28** — all 8 pairs settled by updating each held survivor's `winner` via `db.save_tournament`, soft-deleting the reconstruction via `dedup_tournaments.py --apply` (transplanting `external_ids.twda_entry`), and re-importing every winning deck + recomputing Hall of Fame wins via `backfill_twda.py --apply`:

- **2 no-winner survivors:** `Shell Game` (`2k6sgquebec` → `François Nadeau`), `Czestochowa by Night` (`2k9czestochowa` → `Tomasz Pietkiewicz`).
- **2 winner disagreements** (both players were finalists in each event): `Mind of a Killer` (`2k6moakquebec` → `Marc Desaulniers`, reconstruction was already gone; old deck under `Yan Blondin` replaced), `Buffet Contre les Vampires` (`2k7parisbclv` → `Reyda Seddiki`).
- **4 archive winners missing from tournament roster** (all 4 confirmed as live VEKN members in matching countries; added to `players` and set as `winner`): `Kindred Society Games` (`2k7luccaitaly` → `Mirko Anconitani`), `The Eldest Command Undeath` (`2k7capetownnovember` → `Daniel Boud`), `Urban Jungle: Vitoria` (`2k8ujvitoria` → `Leonardo Ribeiro`), `Catch the infernal` (`2013ctims` → `Sebastià Giralt`).

## Stage 2 — post-retirement officials review

### Prince / NC divergence — legacy archon vs the app

Resolved **2026-11-28** — Archon is the system of record for Prince and NC appointments; no blind union was run (restoring a stepped-down Prince republishes their contact details in the public officials directory).

Of the 29 legacy-only officials captured on **2026-08-09**:
- **11 already settled in the app:** 7 already hold `Prince` (`2020047`, `3540058`, `3540078`, `3540099`, `6960007`, `3830065`, `8930109`), 2 hold `NC` (`3670001` Jesper Bøje, `8230009` James Freimuller), and 2 superseded legacy NCs hold `Prince` (`1000224` Wes Weston, `2120044` Mark Loughman).
- **18 remaining legacy Princes handed to Ginés and the NCs** to re-grant in the app if still active (Brazil: 9, United Kingdom: 3, Czech Republic / Hungary / Italy / Slovakia / Sweden / United States: 1 each).
- The 36 app-only officials were appointed after legacy froze and stay as-is.
