# #567 — All-live duplicate tournaments: cleanup after the VEKN API is decommissioned

Data gathered 2026-08-08 from `dedup_tournaments.py --probe-vekn` on prod, plus
direct vekn.net reads for the PennyBridge pair.

## Why this is blocked, and what unblocks it

These are pairs where **one real event was entered twice on vekn.net and BOTH
event ids are still live**. The standard recipe (soft-delete the loser copy,
transplant its `external_ids.vekn` onto the survivor) does not work while the
VEKN tournament sync is an upstream: the surviving id is fine, but the *dead*
copy's id still exists on vekn.net, so the next sync re-creates the copy we just
deleted. That is the whole reason this class is excluded from the dedup script's
proposals — see the `--probe-vekn` docstring in
`backend/scripts/dedup_tournaments.py`.

Two exits, either one sufficient:

1. **Officials delete the duplicate event on vekn.net** — then the id is dead,
   the sync can no longer re-create it, and the pair drops into the ordinary
   resolvable class (`--probe-vekn` will propose it automatically on the next
   run). The list below is drafted for exactly this hand-off.
2. **The VEKN API is decommissioned** (archon becomes system of record) — nothing
   re-creates anything, and every pair below becomes locally fixable with the
   standard soft-delete + transplant, no officials in the loop.

**There is no VEKN-API-decommission epic or gate ticket on the board.** The only
decommission tracked is #42, which retires *legacy archon*, not the VEKN API.
If that epic is ever filed, reparent this ticket under it. #341's Q5 (does
vekn.net recompute rtp from positions, or store our pushed rtp verbatim) is the
nearest existing thing — it gates the system-of-record claim.

## Prior art in this area (already done, do not redo)

- 2026-08-08: `--apply` resolved **7** groups where exactly one id was live —
  AMICI NOCTIS, Alexandre Koch, Vozhd of Szczecin, François Villon, Draft that
  Was Promised (adopted vekn 13137), 8th Tragic Love Affair, Cearense 2026. See
  #521.
- The mixed-vekn class (#520 — some but not all copies hold a vekn id) reports
  **zero** groups on prod. That class is fully resolved.

## The list

### Strong candidates — one copy carries no results

Near-certain double-entries: the empty copy is the accidental second entry.

| Event | Date | Keep | Delete (empty) |
|---|---|---|---|
| 5ª Jornada Liga Levante Norte | 2026-03-29 | **13151** (26 players, 3 rounds) | 13152 (0 players) |
| Sangrando por un sueño | 2026-01-25 | **12972** (5 players) | 12971 (0 players) |
| Primeiro campeonato online Inconnu do home office | 2026-01-18 | **12979** (12 players) | 12931 (0 players) |
| PennyBridge - Charisma III | 2026-05-22 / 05-23 | **13048** (12 players, results) | 13046 (0 players) |

Player counts for the first three come from the #521 ticket body; PennyBridge was
verified directly (both ids fetched live on vekn.net: same name, same venue
Brickebacken/Örebro, same "3 + Final" format, only 13048 carries results).

### Needs judgement — per-copy results not yet pulled

| Event | Date | vekn ids | Signal |
|---|---|---|---|
| Forced March | 2024-03-17 | 11252, 11263 | both rated |
| Origins Constructed | 2019-06-13 | 9188, 9189 | consecutive ids, both rated |
| V:TES Constructed Tournament | 2018-06-14 | 8896, 8897 | consecutive ids, both rated; generic name — plausibly two real Origins events |
| Last Stand | 2010-09-19 | 5543, 5700 | — |
| Praxis Seizure: Barcelona | 2010-05-30 | 34, 1329 | ids far apart — smells like a legacy re-entry |
| Ropecon ECQ | 2009-07-31 | 5518, 6067 | — |
| Torneio Draft de Lords of the Night | 2007-11-10 | 2717, 3270 | — |

**"Both rated" argues AGAINST duplication.** Two distinct events both being
rating-eligible is correct, and a genuine double-entry usually leaves one copy
empty. Conventions routinely run several tournaments on one day under a generic
name. Treat the three both-rated rows as the *weakest* candidates, not the most
urgent — resolving them needs per-copy player/round counts, which nobody has
pulled yet.

### Deliberately excluded

- **98 `Imported VTES Event` groups** (47 in 2004, 51 in 2005). That placeholder
  name covers hundreds of genuinely distinct legacy events, dozens per day. Pure
  noise; never send these to officials.
- **70 groups over 4 copies**, skipped by `PROBE_GROUP_CAP` — placeholder-shaped
  by the same logic.

98 + 10 named = the 108 "all ids live" lines the probe reported.

## Sub-item: the day-boundary detection blind spot

`DUPLICATE_GROUPS_QUERY` and `BOTH_VEKN_GROUPS_QUERY` (`backend/src/db.py:1222`
and `:1257`) both group on `lower(name)` + **exact UTC start day**. A duplicate
pair whose copies straddle midnight is therefore invisible to both. PennyBridge
is the known member: `2026-05-22T00:00:10` vs `2026-05-23T00:00:10`.

Naively widening the grouping to ±1 day is wrong — it would flag genuine
consecutive-day convention events. A ±1-day scan over prod returned 9 pairs, and
several are clearly legitimate:

```
Bachanalia 2012              6870 2012-09-15  /  6871 2012-09-16
Blood Mill: Żarnowiec       12208 2025-08-15  / 12205 2025-08-16
Czech Championship 2007       863 2007-10-27  /  2582 2007-10-28
Fee Stake: Manaus           12340 2025-05-03  / 12342 2025-05-04
Left 4 Bleed: Palace Party  12808 2025-11-22  / 12807 2025-11-21
Origins 9am                   554 2006-06-29  /  4029 2006-06-30
PennyBridge - Charisma III  13048 2026-05-23  / 13046 2026-05-22
Praxis: Matias Barbosa      12608 2025-09-28  / 12557 2025-09-27
RUMO AO BR 2026 ETAPA 2     12699 2025-09-29  / 12689 2025-09-28
```

`Origins 9am` on two consecutive days and `Czech Championship 2007` day-1/day-2
are almost certainly real distinct events.

**Proposed fix:** widen only the *candidate* set to ±1 day and let the existing
VEKN API probe adjudicate. Both ids live → "no local action" (Origins 9am stays
correctly quiet); exactly one id dead → a resolvable pair we currently cannot see
at all. Cost is a handful of extra authenticated API reads. Worth doing before
this ticket's cleanup so the cleanup covers the day-straddling pairs too.

## Re-deriving this on prod

```sh
# the probe (read-only; needs VEKN creds, which the service env carries)
ssh ubuntu@46.226.104.123 "sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  /opt/archon/backend/.venv/bin/python /opt/archon/backend/scripts/dedup_tournaments.py --probe-vekn'"
```

Sourcing the whole env file trips bash on an unquoted value at line 14
(`zyve: command not found`) — harmless noise, but for anything that does not need
the VEKN creds prefer exporting just what you need:

```sh
export DATABASE_URL=$(grep -m1 ^DATABASE_URL= /etc/archon/archon-backend.env | cut -d= -f2-)
```

Ratings need no manual step after any cleanup here: `run_rating_recompute` is on
a 24h timer and also runs at the tail of the nightly VEKN sync
(`backend/src/main.py:198,411`). The admin route mentioned in the dedup script's
module docstring does not exist — that reference is stale.
