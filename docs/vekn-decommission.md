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

Captured on production **2026-08-09**, while the legacy `archondb` was still
live on the box. Recorded here deliberately: the final archive dump retires that
database, and after that this comparison cannot be reproduced.

**This is a review queue, not a backfill plan.** Prince and NC are app-managed —
archon is the system of record for them. Legacy archon mirrored vekn.net's
`princeid`/`coordinatorid`; appointments have moved on since, and the app has
been managing them since the cutover. So a name below may mean "we lost this at
migration" *or* "this person stepped down and the app is right". Only someone
who knows the appointments can tell those apart.

Why it was excluded from the judge-rank backfill: a union can only ADD.
Restoring a superseded Prince republishes their contact details in the
**public** officials directory (`access_levels.py:102` puts Prince/NC there),
and the two NC candidates are in countries that already have a different,
current NC — a blind union would seat two national coordinators. The judge ranks
were safe precisely because they diverged in only one direction and confer no
access.

Counts: Prince legacy=465 app=472; NC 42/42.

#### In legacy archon, absent in the app (candidates to review)

| VEKN | Name | Country (legacy) | Legacy role | App roles today |
|------|------|------------------|-------------|-----------------|
| 1002955 | Danilo Fernandes | Brazil | **Prince** | — |
| 1003089 | Bruno Peixoto Moreira | Brazil | **Prince** | — |
| 4590035 | Bruno Paramo Meleiro | Brazil | **Prince** | — |
| 5830013 | Guilherme "Griffo" | Brazil | **Prince** | — |
| 6020112 | Daniel Anão | Brazil | **Prince** | — |
| 6130052 | Hércules Peres | Brazil | **Prince** | — |
| 6130079 | Schwarzenneger Erick | Brazil | **Prince** | — |
| 7300093 | Raylson Oliveira | Brazil | **Prince** | — |
| 7790009 | Vinicius Costalonga | Brazil | **Prince** | — |
| 1000224 | Wes Weston | Canada | **NC** | Prince |
| 3090032 | Maros Chomjak | Czech Republic | **Prince** | — |
| 3670001 | Jesper Bøje | Denmark | **Prince** | NC |
| 1006339 | Dr Alkonyi Csaba | Hungary | **Prince** | — |
| 2020047 | Feco Ferenc Borbely | Hungary | **Prince** | — |
| 3540058 | Zsolt Cziraki | Hungary | **Prince** | — |
| 3540078 | Gabor Endler | Hungary | **Prince** | — |
| 3540099 | Sandor Kadar | Hungary | **Prince** | — |
| 3412312 | Massimo Vaccari | Italy | **Prince** | — |
| 6960007 | Stanisław Szczepaniak | Poland | **Prince** | — |
| 3030054 | Radovan Vitek | Slovakia | **Prince** | — |
| 3830065 | Antonio Calvario M | Spain | **Prince** | — |
| 8930109 | Javier Flores Álvarez | Spain | **Prince** | — |
| 8090044 | Zack Holmgren | Sweden | **Prince** | — |
| 1000595 | John Barclay | United Kingdom | **Prince** | — |
| 1000757 | Sam Marsh | United Kingdom | **Prince** | — |
| 1006550 | Steven Burnside | United Kingdom | **Prince** | — |
| 8230009 | James Freimuller | United Kingdom | **Prince** | NC |
| 2050008 | Matthew Hirsch | United States | **Prince** | — |
| 2120044 | Mark Loughman | United States | **NC** | Prince |

_29 members._

#### In the app, absent in legacy archon (granted since, or appointed after legacy froze)

| VEKN | Name | App role not in legacy | App roles today |
|------|------|------------------------|-----------------|
| 8840000 | Alexandre Bustros | **NC** | NC |
| 2050001 | Ben Peal | **NC** | IC, NC |
| 4420000 | Csaba Pál | **Prince** | Prince |
| 5501907 | Daniel Lopes Padilha | **Prince** | Prince |
| 6580003 | David Fisher | **Prince** | Prince |
| 3830090 | David López-Pozuelo Rivas | **Prince** | Prince |
| 8740009 | Dennis Crowch | **Prince** | Prince |
| 4260004 | Felipe Salvador Medina Rodríguez | **Prince** | Prince |
| 7060126 | Fernando Fiorin | **Prince** | Prince |
| 7060097 | Gabriel Ivory | **Prince** | Prince |
| 5500002 | Gabriel Rodrigues de Marqui | **Prince** | Prince |
| 6130009 | Guilherme Machado | **Prince** | Prince |
| 5740004 | Guillaume Pulyk | **Prince** | Prince |
| 7400073 | Gustavo Alfonso González Ortiz | **Prince** | Prince |
| 3510120 | Jiří Stibor | **Prince** | Prince |
| 3970021 | Joakim Rapp | **Prince** | Prince |
| 8090038 | Johan Adamsson | **Prince** | Prince |
| 3540189 | Krisztián Tivadari | **Prince** | Prince |
| 6130070 | Leonardo Zimmern | **Prince** | Prince |
| 5720014 | Maarten Rijnbeek | **Prince** | Prince |
| 3260015 | Magnus Söder | **Prince** | Prince |
| 5490086 | Marcelo Cordoville Farias | **Prince** | Prince |
| 8710006 | Marcin Borowski | **Prince** | Prince |
| 8090025 | Marcus Berg | **Prince** | Prince |
| 8580010 | Marvin Lange | **Prince** | Prince |
| 6980013 | Mateusz Jarota | **Prince** | Prince |
| 3491403 | Maxime Biebaut | **Prince** | Prince |
| 7060155 | Morgana Gomes | **Prince** | Prince |
| 8365498 | Nathan Alves Bruno | **Prince** | Prince |
| 8090049 | Patrik Spjut | **Prince** | Prince |
| 3540150 | Péter Korsós | **Prince** | Prince |
| 3600016 | Robin Vossen | **Prince** | Prince |
| 1000632 | Scott Gomes | **Prince** | Prince |
| 9100001 | Simon George | **Prince** | Prince |
| 6360007 | Stefano Orlandini | **Prince** | Prince |
| 3090014 | Zsolt Varga | **Prince** | Prince |

_36 members._
