# VEKN decommission — deferred work

Work that becomes possible only when the VEKN syncs retire, held here with the
evidence that cannot be reconstructed afterwards. The board holds no waiting
state: each item below is a real, completable ask parked on a named trigger — a
condition someone could observe firing. `/upkeep` re-checks the triggers each
pass; a fired trigger sends its item back through `/intake` as an ordinary board
line.

Both triggers are the retirement stages in [vekn](vekn.md#decommission), which is
where what retires and in what order is settled.

While the tournament and member syncs are upstreams, anything deleted or diverged
locally is re-created on their next run — that is what makes each of these
unfixable today.

## Trigger: stage 1 — the tournament calendar sync retires

### Duplicate tournament cleanup

**Deferred ask** — clean up the remaining all-live duplicate tournaments: one
real event entered twice on vekn.net with both vekn ids live. Soft-delete plus
vekn-id transplant is the recipe. Done when each group below has one live copy.

Data gathered 2026-08-08 from `dedup_tournaments.py --probe-vekn` on prod, plus
direct vekn.net reads for the PennyBridge pair, and re-confirmed by the
2026-08-28 run — same set, one addition.

**Why this is blocked.** These are pairs where one real event was entered twice
on vekn.net and **both** event ids are still live. The standard recipe
(soft-delete the loser copy, transplant its `external_ids.vekn` onto the
survivor) does not work while the VEKN tournament sync is an upstream: the
surviving id is fine, but the dead copy's id still exists on vekn.net, so the
next sync re-creates the copy we just deleted. That is why this class is
excluded from the dedup script's proposals — see the `--probe-vekn` docstring in
`backend/scripts/dedup_tournaments.py`.

Two exits, either one sufficient:

1. **Officials delete the duplicate event on vekn.net** — then the id is dead,
   the sync can no longer re-create it, and the pair drops into the ordinary
   resolvable class (`--probe-vekn` proposes it automatically on the next run).
   The list below is drafted for exactly this hand-off.
2. **The VEKN API is decommissioned** (archon becomes system of record) —
   nothing re-creates anything, and every pair below becomes locally fixable
   with the standard soft-delete + transplant, no officials in the loop.

**Prior art (already done, do not redo).** On 2026-08-08 an `--apply` run
resolved 7 groups where exactly one id was live — AMICI NOCTIS, Alexandre Koch,
Vozhd of Szczecin, François Villon, Draft that Was Promised (adopted vekn
13137), 8th Tragic Love Affair, Cearense 2026. That emptied the mixed-vekn class
(some but not all copies hold a vekn id), and the archive backfill refilled it
with a class of its own — see [archive reconstructions] below.

**A shape the audit cannot see.** Its scope is groups where *some but not all*
copies hold a vekn id, so two live copies sharing **one** id never surface. Beta
holds exactly that under `12642`: the event-code backfill gave one copy the code
`12642` and minted `SCHNJG` for the other, and short links survive it either way
because `get_tournament_by_event_code` falls back to a vekn external-id lookup.
Production was never checked for the shape and no dedup run will report it, so
it needs a direct query — group live tournaments by `external_ids.vekn` and keep
the counts above one. Locally fixable whenever found: soft-delete the loser and
the survivor keeps an id that is legitimately live, so no transplant and no
officials.

#### Strong candidates — one copy carries no results

Near-certain double-entries: the empty copy is the accidental second entry.

| Event | Date | Keep | Delete (empty) |
|---|---|---|---|
| Itaquaquecetubense 2026 | 2026-08-16 | **13478** (27 players, standings) | 13477 (0 players) |
| 5ª Jornada Liga Levante Norte | 2026-03-29 | **13151** (26 players, 3 rounds) | 13152 (0 players) |
| Sangrando por un sueño | 2026-01-25 | **12972** (5 players) | 12971 (0 players) |
| Primeiro campeonato online Inconnu do home office | 2026-01-18 | **12979** (12 players) | 12931 (0 players) |
| PennyBridge - Charisma III | 2026-05-22 / 05-23 | **13048** (12 players, results) | 13046 (0 players) |

Player counts for the middle three come from the earlier dedup pass's record.
Itaquaquecetubense was read off the corpus on 2026-08-28 — the empty copy carries
no country and no winner either. PennyBridge was verified directly (both ids
fetched live on vekn.net: same name, same venue Brickebacken/Örebro, same
"3 + Final" format, only 13048 carries results).

#### Needs judgement — per-copy results not yet pulled

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

#### Deliberately excluded

- **98 `Imported VTES Event` groups** (47 in 2004, 51 in 2005). That placeholder
  name covers hundreds of genuinely distinct legacy events, dozens per day. Pure
  noise; never send these to officials.
- **70 groups over 4 copies**, skipped by `PROBE_GROUP_CAP` — placeholder-shaped
  by the same logic.

98 + 11 named = the 109 "all ids live" lines the probe reported.

#### The day-boundary detection blind spot

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
correctly quiet); exactly one id dead → a resolvable pair we currently cannot
see at all. Cost is a handful of extra authenticated API reads. Worth doing
before the cleanup so it covers the day-straddling pairs too.

#### Re-deriving this on prod

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

### IC record curation — events to delete

**Deferred ask** — give ICs a cleanup capability that can delete or withdraw a
tournament that **still exists** on vekn.net. Origin gh-6, a Prince asking how to
remove an event created by mistake; the half of that question about an event
vekn.net no longer has is answered — the organizer deletes it on the scan's
absence flag ([vekn](vekn.md#the-event-veknnet-no-longer-has)), which is why
organizers need no further deletion right here. **Do not re-derive the rejected
probe-at-delete approach** — it was fully built and reverted. Done when an IC
can remove a mistaken event, every entry below is gone, and the frontend no
longer offers Delete on an offline-locked tournament, which the API refuses
today.

Running list of tournaments that **should not be in the record**, waiting on the
IC cleanup capability. Distinct from its two sibling populations:

- the duplicate groups above — one real event entered twice upstream;
- events we hold that **no longer exist upstream** — the calendar scan confirms
  these itself, every run, and flags them
  ([vekn](vekn.md#the-event-veknnet-no-longer-has)); their organizer can already
  delete them, so none of them wait here.

This list is the third population: events that are simply **wrong** — created by
mistake, mistyped, or never real — regardless of what vekn.net says.

**Check before assuming any row must wait.** Deletion is refused today only when
a tournament carries `external_ids['vekn']` or `vekn_pushed_at` and the scan has
not flagged it absent. A row carrying neither footprint can be deleted **now** by
its organizer and does not belong on this list at all. The
public projection does not currently expose `external_ids`, so this has to be
checked against the DB, not the snapshot.

#### 1. `Arraial da Vampirada` — mistyped year, stuck in Registration

| | |
|---|---|
| uid | `03af3db6-f5fe-480b-949c-bf778fac2193` |
| start / finish | **2034-12-16** 10:00 → 17:30 |
| state | `Registration` |
| where | Loja Homo Ludicus, Avenida Governador Gayoso e Almendra 443, São João, Teresina (Piauí), Brazil |
| format | Standard, not online, no league |
| vekn id | **unknown — check first** (see above) |

Owner call 2026-08-15: delete it.

A real recurring Brazilian event whose year was fat-fingered. The genuine
edition is `93232a61-8a8b-4d96-a893-34ee120035a3`, *same name, same country,
2025-06-29, Finished*. The 2034 row is almost certainly meant to be
**2024-12-16** (single-digit slip), which also explains the stuck `Registration`
state — the date never arrived, so it was never run or finished. Its `modified`
stamp of 2026-08-07 is not evidence of recent editing; a projection re-save
sweep bumps that corpus-wide.

**Why it is not harmless while it waits.** It is publicly visible, not merely
present: the tournament page returns 200 anonymously, logged-out visitors see
current + upcoming events ([sync](sync.md)), so it sits at the bottom of the
upcoming list for the next eight years — and it is exported as a real VEVENT in
the anonymous `.ics` feed, street address included:

```
DTSTART:20341216T100000Z
SUMMARY:Arraial da Vampirada
LOCATION:Loja Homo Ludicus\, Avenida Governador Gayoso e Almendra\, 443\, São João\, Teresina
```

Anyone subscribed to the calendar feed is carrying it.

**Second, independent defect on the same row**: `timezone` is `"UTC"` while the
venue is in Teresina (UTC−3), so the wall-clock 10:00 is anchored to UTC and the
feed advertises 07:00 local. `timezone` is left at its model default
(`models.py:397`) rather than set from the venue. Worth checking whether other
rows share it — if so that is its own ask, not a per-row fix.

**Cheaper interim than waiting**: `start`, `finish` and `timezone` are all in
the engine's `CONFIG_FIELDS` allowlist, so the
organizer or an IC can correct the date in-app today with no code change and no
deletion — which sidesteps the VEKN-footprint gate entirely. Deleting is the
owner's call; correcting is available immediately if the row turns out to be
blocked.

Found 2026-08-15 while measuring the tournament corpus for the Hall of Fame
rebuild — a year histogram of all 8466 live tournaments put exactly one row in
2034.

#### 2. Placeholder-named rows carrying a VEKN id

Three live `Finished` tournaments with **zero players and zero rounds**, whose
names say outright that they were never events:

| uid | date | vekn id | country | name |
|---|---|---|---|---|
| `f880a4c5-e8cc-4c75-b8e1-9168caf04842` | 2025-11-09 | `9955` | — | `TEST` |
| `abd7e330-8005-49d5-97ce-c650bc6edb68` | 2025-11-15 | `12797` | Portugal | `delete me` |
| `dde82ba8-6936-4ec4-94fc-130523c02cf7` | 2026-01-01 | `13235` | Brazil | `ND` |

All three carry `external_ids['vekn']`, so deletion is refused today and the
calendar sync would re-create them anyway — they wait on this section's trigger,
not on an organizer.

`delete me` is the costly one: a TWDA entry submitted under event `12797` points
at it while the real event, `Bloodshed in VdC`, holds `12794`. That is the single
`vekn id contested` row in the Hall of Fame reconciliation, and it is the reason
the reconciler must treat a vekn event id as evidence rather than proof
([vekn](vekn.md)). Deleting the husk retires that special case for good.

**Two further rows named `Test` are probably not this population** —
`ebcfaea6-babb-4725-8fb4-4cc755bbfd9e` (2020-09-01, Croatia, 1 player) and
`4218a3a4-0a2e-434a-be14-2d7135d10688` (2025-09-13, Portugal, **8 players**).
Neither carries a vekn id, so per the check above both may already be deletable
by their organizer and belong nowhere near this list. The 8-player one should not
be deleted on the strength of its name alone — that is a plausible real roster.
`vekn_pushed_at` is unread for both; check it before acting.

**Five more placeholder-looking names are real events, not junk** — `LoB`
(2006, US, 12 players), `QCF` twice (2006, 29 and 6 players), `NA` (2006, FR, 23
players) and `Tournament` (2007, CZ, 16 players). All are pre-2014 legacy archon
imports with real rosters and vekn ids; the names are terse or generic, not
wrong. They need the *display* treatment the Hall of Fame plan already carries — a
name synthesized from place and date — and must never be deleted.

Found 2026-08-16 while deciding the Hall of Fame reconciliation queue.

### Lift the vekn-linked refusal on archival correction

**Deferred ask** — delete the `ArchivalResultsVeknLinked` guard in
`engine/src/tournament/`. Done when an IC can correct a rounds-less row carrying
`external_ids['vekn']` and the correction survives a full sync run.

The guard exists only because `vekn_tournament_sync.py`'s full-rebuild branch fires
whenever `not existing.rounds and tournament.players`, so a correction to such a
row is wiped on the next nightly run — silently, and permanently. It is one refusal
in one match arm, and it is what keeps the two disagreeing rows below parked. The
alternative considered and rejected: a `results_corrected_at` marker the sync
respects, which is a second persisted field for a capability that expires with this
trigger.

### IC record curation — rows that disagree with the archive about who won

**Deferred ask** — settle the winner on the two rows below and correct whichever
side is wrong. Done when each row's `winner` matches the record the IC accepts.

Both came to us through their vekn event id, so the disagreement is between the
vekn.net result and the winning deck the TWDA holds for the same event. One side
is wrong and neither is ours to decide unilaterally. They wait on this section's
trigger because the correction path — the `SetArchivalResults` engine event
([tournaments](tournaments.md#engine-event-catalog)) — deliberately refuses any row
carrying `external_ids['vekn']` while the calendar sync is live: the sync's
full-rebuild branch would wipe the correction on its next run.

| uid | date | event | our winner | the archive's |
|---|---|---|---|---|
| `019f1a1a-1923-766f-bba2-ae0291673caa` | 2023-10-22 | `Matusalén,¿dónde está mi promo?` | Jose Maria Prieto Amengual | Gines Quinonero |
| `019f1a19-a603-773a-a922-d6dbe2146b47` | 2021-09-19 | `Roundhouse` | Joab Rogerio Barbosa Da Silva | Jose Roberio Barbosa Da Silva |

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

**Deferred ask** — settle the eight pairs below: where the reconstruction is the
same event, soft-delete it and transplant its archive key onto the survivor as
`external_ids.twda_entry`; where it is a distinct event, leave both live and
record which. Done when no pair below is ambiguous and the mixed-vekn class of
`dedup_tournaments.py` reports only pairs it can propose.

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
distinct event sharing a name and a day, or a member we never linked — the VEKN
tournament sync drops players whose VEKN id we do not hold, so our roster is not
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

## Trigger: stage 2 — the member roster sync retires

### Prince / NC divergence — legacy archon vs the app

**Deferred ask** — review the divergence and record the outcome: each divergent
name below gets a verdict from someone who knows the appointments, and the roles
match it. A blind union would republish superseded officials' contact details
publicly and seat two coordinators in two countries.

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
