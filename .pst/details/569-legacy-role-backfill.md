# Legacy role backfill — evidence, scope decision, and the restored list

Script: `backend/scripts/backfill_roles_from_archon.py` (report by default, `--apply` writes).
Measured on production 2026-08-09, legacy `archondb` still live on the box.

## What was lost

The ETL seeds `roles` only on its INSERT path (`migrate_from_archon.build_user`); merge
mode deliberately never writes them. So for every member the VEKN member sync had
already created before the ETL ran, the legacy role list was discarded and the account
kept only what `vekn_sync._derive_role_seeds` could reconstruct — Prince from
`princeid`, NC from `coordinatorid`, IC from the hardcoded ADMINS set, and at most one
judge rank from the ~44-entry `JUDGES` dict in `backend/src/data/vekn_roster.py`.

## Census (matched on VEKN id)

| role | legacy | new | only-legacy | only-new |
|------|-------:|----:|------------:|---------:|
| IC | 6 | 6 | 0 | 0 |
| NC | 42 | 42 | 2 | 2 |
| Prince | 465 | 472 | 27 | 34 |
| Ethics | 1 | 7 | 0 | 6 |
| Rulemonger | 5 | 5 | 0 | 0 |
| Judge | 35 | 20 | 15 | 0 |
| Judgekin | 70 | 21 | 49 | 0 |

## Scope: Judge + Judgekin only

The ticket assumed "Prince and NC are the ONLY roles safe, by re-derivation". **Both
halves of that are wrong** and the correct reasoning is different:

- No sync ever re-derives roles. `vekn_sync.py`:578-582 is explicit — roles are seeded
  on first import and app-managed thereafter; only `vekn_prefix` is refreshed. The new
  DB's Prince/NC state is itself a per-account creation-time snapshot.
- 27 Princes and 2 NCs *are* missing, so "safe" was never true.

Two rules decide the scope instead:

- **Directionality.** Judge/Judgekin have `only-new = 0` — the new DB is a strict subset
  of legacy, the signature of pure migration loss. Prince/NC/Ethics diverge in *both*
  directions: two snapshots of a moving target plus real in-app management (Ethics 1→7
  is entirely post-cutover grants). A union can only ADD, so backfilling a
  bidirectionally divergent role monotonically inflates the officials list with people
  VEKN has since replaced.
- **Access.** Restore only roles conferring no data-access projection. Judge/Judgekin
  appear in no branch of `access_levels.py` and are absent from `routes/users.py`'s
  `access_roles = {NC, IC}`. Prince and NC both hit `access_levels.py`:102, which puts
  them in the PUBLIC officials directory with contact fields — restoring 27 stale
  Princes would publish 27 people's contact details for an office they no longer hold.
  NC also carries FULL country-scoped access and implicit organizer rights in-country,
  and the two candidates are in Canada and the US, which already have a different,
  current NC (Alexandre Bustros, Ben Peal).

Legacy archon was never authoritative here: Princes are appointed by their NC (or IC)
and NCs by the IC (PRODUCT.md:39); vekn.net's `princeid`/`coordinatorid` is the register
of those appointments and legacy held a mirror. A mirror never outranks the register.

## "DECIDE BEFORE APPLYING" — resolved

The ticket asked whether an audit trail exists to exclude roles deliberately REVOKED in
the new app since cutover. **It does:** `routes/users.py` stamps `"roles"` into
`local_modifications` on every in-app role write. Exactly **12** users in all of
production carry that marker, and **none of them intersect the backfill set** — so the
union is provably safe here, not merely accepted-and-documented. The script skips marked
users anyway, so a future re-run stays safe.

The backfill deliberately does NOT stamp the marker on the users it writes: no sync
writes roles, so it would confer no protection, and keeping the marker to mean "a human
changed this in the app" is what makes it a trustworthy exclusion signal later.

## Rulemonger review queue

Judge rank carries an activity requirement (`reference/judges-guide.md`:579-580 — Judges
yearly, Judgekins six-monthly), reviewed by the ranks rather than lapsing on a
computable date, and the app has no attendance record spanning the legacy era. Some of
the ranks below will be stale. Pruning them is a Rulemonger pass over this list, not a
reason to withhold a member's rank now — the error costs are asymmetric: a missing rank
is silently wrong and user-visible (it is what gh-3 reported), a stale rank confers no
access and is revocable in one click.

| # | VEKN | Name | Country | Restored | Already had |
|---|------|------|---------|----------|-------------|
| 1 | 8060001 | Jake Hill | Australia | **Judgekin** | — |
| 2 | 3340152 | Paul Direktor | Austria | **Judge** | Judgekin |
| 3 | 1930004 | Leonardo Vidigal | Brazil | **Judgekin** | — |
| 4 | 4522213 | Giuseppe "Kela" Sciortino | Brazil | **Judgekin** | — |
| 5 | 5350023 | Eduardo "Ahrimane" Simões | Brazil | **Judgekin** | Prince |
| 6 | 5490002 | Thiago Sousa | Brazil | **Judgekin** | — |
| 7 | 5490007 | Felipe Góes | Brazil | **Judgekin** | — |
| 8 | 6010147 | Roberto Mautone Junior | Brazil | **Judgekin** | — |
| 9 | 6040022 | Tiago Honorato de Castro Ramos | Brazil | **Judgekin** | Prince |
| 10 | 6040038 | André Afonso | Brazil | **Judge** | — |
| 11 | 6050012 | Márcio Pinheiro | Brazil | **Judgekin** | NC, Prince |
| 12 | 6230002 | Alanmut Bastos | Brazil | **Judgekin** | Prince |
| 13 | 6230004 | Aylton Cianni | Brazil | **Judgekin** | Prince |
| 14 | 7060085 | Estel Matiazi | Brazil | **Judgekin** | Prince |
| 15 | 7060087 | Alex Demian | Brazil | **Judgekin** | — |
| 16 | 7790007 | Erik Procopio | Brazil | **Judgekin** | — |
| 17 | 7790020 | Victor Pessotti | Brazil | **Judgekin** | — |
| 18 | 1002238 | Hernán Rodríguez | Chile | **Judgekin** | — |
| 19 | 1800011 | Sergio Miguel Herrera | Chile | **Judgekin** | — |
| 20 | 1800012 | Gonzalo Andrés Herrera | Chile | **Judgekin** | — |
| 21 | 5390020 | Karel Vaigl | Czech Republic | **Judgekin** | NC |
| 22 | 1004319 | Peitsa Suominen | Finland | **Judge** | — |
| 23 | 3070129 | Antti Penttilä | Finland | **Judgekin** | Prince |
| 24 | 8580027 | Nicolas Brun-Verhille | France | **Judgekin** | Prince |
| 25 | 1000008 | Peter Talmacsi | Hungary | **Judgekin** | NC |
| 26 | 1006172 | Máté Vaka | Hungary | **Judge** | — |
| 27 | 3540026 | Jozsef Gal | Hungary | **Judgekin** | — |
| 28 | 3540150 | Péter Korsós | Hungary | **Judge** | Prince |
| 29 | 3540445 | Ádám Attila Bódis | Hungary | **Judgekin** | — |
| 30 | 3540446 | Gábor Hagymási | Hungary | **Judgekin** | — |
| 31 | 3660001 | Ádám Péter | Hungary | **Judgekin** | — |
| 32 | 3020062 | Danilo Fruttaldo | Italy | **Judgekin** | Prince |
| 33 | 3020106 | Filippo Mengoli | Italy | **Judge** | — |
| 34 | 3020124 | Diego Di Nicolantonio | Italy | **Judge** | — |
| 35 | 4740000 | Alessandro Donati | Italy | **Judgekin** | Prince |
| 36 | 4740014 | Leonardo Bensi | Italy | **Judgekin** | Prince |
| 37 | 4740044 | Andrea Casaccia | Italy | **Judgekin** | — |
| 38 | 3600003 | Jeroen van Oort | Netherlands | **Judge** | NC |
| 39 | 3600016 | Robin Vossen | Netherlands | **Judgekin** | Prince |
| 40 | 1003197 | Andrew Stott | New Zealand | **Judgekin** | — |
| 41 | 1001192 | Dante Gagelonia | Philippines | **Judgekin** | — |
| 42 | 1004419 | Maciej Kozłowski | Poland | **Judge** | Prince |
| 43 | 6980010 | Marcin Zakrzewski | Poland | **Judgekin** | — |
| 44 | 3120011 | Eduardo Carona | Portugal | **Judgekin** | — |
| 45 | 3260056 | Hugo Coelho | Portugal | **Judgekin** | — |
| 46 | 3260082 | Tiago Souto | Portugal | **Judgekin** | — |
| 47 | 7350009 | Srdjan Milojevic | Serbia | **Judgekin** | Prince |
| 48 | 3030078 | Martin Dudik | Slovakia | **Judge** | NC |
| 49 | 3770037 | Davor Himmelreich | Slovenia | **Judgekin** | — |
| 50 | 1003983 | Tomàs López Jiménez | Spain | **Judge** | Prince |
| 51 | 1004014 | Alberto Padilla Capitán | Spain | **Judgekin** | Prince |
| 52 | 1004328 | Joaquim Miquel Cuesta | Spain | **Judgekin** | — |
| 53 | 1940012 | Iñigo Orbegozo | Spain | **Judgekin** | Prince |
| 54 | 3830074 | Mariano Carbonero Román | Spain | **Judgekin** | — |
| 55 | 3930029 | Alejandro Rodríguez | Spain | **Judgekin** | — |
| 56 | 4090008 | Francisco Javier Valle | Spain | **Judgekin** | Prince |
| 57 | 4200008 | Miquel Jorge Tortajada | Spain | **Judge** | — |
| 58 | 4530001 | Roberto Guerrero Acedo | Spain | **Judgekin** | — |
| 59 | 8110027 | Iñaki Jiménez Alonso | Spain | **Judge** | Prince |
| 60 | 8280016 | Javier Centella | Spain | **Judgekin** | — |
| 61 | 8940121 | Luis Alejandro Fuentes Toledo | Spain | **Judgekin** | — |
| 62 | 3810007 | Antonio Cobo Cuenca | United Kingdom | **Judge** | Prince |
| 63 | 5040009 | Kelly Schultz | United States | **Judgekin** | — |
| 64 | 9710002 | Artemis Frey | United States | **Judge** | — |

(64 users, 64 grants: 15 Judge, 49 Judgekin. Zero skipped — no soft-deleted accounts, no
curated-roles accounts, no unmatched VEKN ids.)

Reporter verification: gh-3 named VEKN 3260056 (Hugo Coelho), plus Eduardo Carona
(3120011) and Tiago Souto (3260082) — all three Portuguese, all three restored to
**Judgekin** (not Judge, as the report phrased it).
