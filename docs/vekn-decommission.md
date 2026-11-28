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

The first two came to us through their vekn event id, so the disagreement is between the
vekn.net result and the winning deck the TWDA holds for the same event. The third
has no archive entry: its legacy vekn.net sheet is visibly mis-entered (a 1 GW 4 VP
player at `pos` 6 below a 1 GW 3.5 VP finalist) and the player it names as winner
disputes it. One side
is wrong and neither is ours to decide unilaterally. Once Stage 1 is deployed,
`SetArchivalResults` ([tournaments](tournaments.md#engine-event-catalog)) accepts
vekn-linked rows directly, so only the editorial call remains.

| uid | date | event | our winner | the archive's |
|---|---|---|---|---|
| `019f1a1a-1923-766f-bba2-ae0291673caa` | 2023-10-22 | `Matusalén,¿dónde está mi promo?` | Jose Maria Prieto Amengual | Gines Quinonero |
| `019f1a19-a603-773a-a922-d6dbe2146b47` | 2021-09-19 | `Roundhouse` | Joab Rogerio Barbosa Da Silva | Jose Roberio Barbosa Da Silva |
| `019f1a06-a7d1-711f-b9c6-4e6f4c6ee2c9` | 2008-02-24 | `Minion Tap Newark` | Karl Schaefer | none — Karl reports he did not win (gh-57); real winner unknown |

The Brazilian pair are two distinct live members whose names differ by four
letters, so that one is as likely a transcription slip upstream as a wrong result.

Two more disagreements of the same kind, reached from the archive side instead of
the Hall of Fame's, are recorded under [archive reconstructions] below; each
carries a reconstruction to delete as well as a winner to settle.

Found 2026-08-16 by the Hall of Fame winner-identity bootstrap, which reads each
TWDA entry's submitter against the resolved winner of the tournament it attached
to: 3 of 1156 names mapped to two members, and these are the two that are not
genuine homonyms. The third — two live members both named `Pedro Paulo`, in
Fortaleza and Campina Grande — is a real homonym and needs nothing.

### Archive reconstructions of an event we already hold

[archive reconstructions]: #archive-reconstructions-of-an-event-we-already-hold

**The archive backfill creates this class.** `reconcile_twda.py` reconstructs an
entry when no held copy answers for it, and a held copy whose standings yield no
winner name answers for nothing — so the backfill mints a `players=1, decks=1`
row beside the full vekn-linked copy of the same name and day. On prod
2026-08-28 the report found 30 such pairs; 22 were resolved the same day and the
8 here were not.

**What separates them is whether the survivor can receive the deck back.**
Applying a decision soft-deletes the reconstruction, and that cascades the
archive's winning decklist — the only one we hold for these events, every
survivor carrying `decks=0`. The transplanted key is what returns it:
`_tournaments_by_twda_id` then resolves the entry to the survivor and
`_import_decks` re-creates the deck there. But it writes that deck for the
**survivor's** `winner`, and skips the row entirely when there is none. So a pair
is safe to apply only where both copies name the same member, which is what the
22 had and none of these eight do.

#### The survivor names no winner

Deleting the reconstruction loses the decklist for good: `_import_decks` skips a
tournament whose `winner` is empty, and writing one onto a vekn-linked row is
what the section above unblocks. The archive's winner is in our roster, so these
are the same event and the correction is known — only the guard is in the way.

| Event | Date | Held (vekn) | Players | Archive entry | Archive winner |
|---|---|---|---|---|---|
| Shell Game | 2006-03-05 CA | `019f1a02-033a-72c2-a31e-6f587bb89e0f` (836) | 14 | `2k6sgquebec` | François Nadeau |
| Czestochowa by Night | 2009-03-21 PL | `019f1a06-f70c-75ca-8628-29f8b90883b1` (4026) | 23 | `2k9czestochowa` | Tomasz Pietkiewicz |

Reconstructions: `01a028a7-0c3a-707d-9ab7-958f44db7050`,
`01a028a7-60bd-7485-9760-1fe29744a65b`.

#### The two copies disagree about who won

Worse than losing the deck: applying would re-create the archive's decklist under
**our** winner's name, crediting a player with a TWDA deck and a Hall of Fame win
the archive gives to someone else. Both archive winners are in our roster, so one
of the two results is wrong rather than describing another event — the same
question as the two rows above, reached from the other direction.

| Event | Date | Held (vekn) | Our winner | The archive's | Archive entry |
|---|---|---|---|---|---|
| Mind of a Killer | 2006-07-30 CA | `019f1a05-db59-76dd-80c6-8c36656dc444` (1137) | Yan Blondin | Marc Desaulniers | `2k6moakquebec` |
| Buffet Contre les Vampires | 2007-08-04 FR | `019f1a06-f737-756e-a552-c37d657a2c55` (4028) | Arnaud Baigts | Reyda Seddiki | `2k7parisbclv` |

Reconstructions: `01a028a7-031b-72dd-92a4-a81b15c2e1eb`,
`01a028a7-2578-7494-a7b9-1c1c480a4af4`.

#### The archive's winner is not in our roster

Identity is unresolved, and two explanations fit the same evidence: a genuinely
distinct event sharing a name and a day, or a member we never linked — the retired
VEKN tournament sync dropped players whose VEKN id we do not hold, so our roster is not
proof of who played. `Urban Jungle: Vitoria` is the clearest warning against
reading these as distinct events: our winner is recorded under the nickname
`Mineirinho`, which is a member-identity gap, not a second tournament.

| Event | Date | Held (vekn) | Our winner | The archive's | Archive entry |
|---|---|---|---|---|---|
| Kindred Society Games | 2007-11-04 IT | `019f1a07-0bc3-7120-8066-5992a6da9027` (4307) | Miro Albertazzi | Mirko Anconitani | `2k7luccaitaly` |
| The Eldest Command Undeath | 2007-11-17 ZA | `019f1a06-6683-720d-a33d-4a7a65da3099` (2535) | Eric August | Daniel Boud | `2k7capetownnovember` |
| Urban Jungle: Vitoria | 2008-06-28 BR | `019f1a06-f00f-72ca-828c-7b63c1678f85` (3927) | Mineirinho | Leonardo Ribeiro | `2k8ujvitoria` |
| Catch the infernal | 2013-04-07 ES | `019f1a18-a438-7280-8e61-8cf4b9b177a6` (7106) | José Manuel Escobar | Sebastià Giralt | `2013ctims` |

Reconstructions: `01a028a7-1cf7-72e2-840c-fb514352ede1`,
`01a028a7-1459-7269-bfc6-bef3725ae9aa`,
`01a028a7-4f22-7589-8a2d-b5419892b1b3`,
`01a028a5-fafe-71c6-8df4-974e6545d144`.

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
