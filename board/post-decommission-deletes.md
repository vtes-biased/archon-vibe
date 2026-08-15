> Elaborated context for a line in `BOARD.md`. Deleted with the line.

# Events to delete once IC record curation exists

Running list of tournaments that **should not be in the record**, waiting on the
IC cleanup capability. Distinct from its two sibling lists:

- `board/duplicate-tournaments.md` — *duplicates*, one real event entered twice
  upstream.
- the vekn.net reconciliation line's deliverable — events we hold that **no longer
  exist upstream**, established by a targeted `fetch_event` probe while the API is
  still live.

This file is for the third population: events that are simply **wrong** —
created by mistake, mistyped, or never real — regardless of what vekn.net says.
That is `#574`'s own origin case (gh-6, a Prince asking how to remove an event
created by mistake).

**Check before assuming any row must wait.** Deletion is refused today only when
a tournament carries `external_ids['vekn']` or `vekn_pushed_at`
(`backend/src/routes/tournaments.py:1115-1119`). A row with neither can be
deleted **now** by its organizer and does not belong on this list at all. The
public projection does not currently expose `external_ids`, so this has to be
checked against the DB, not the snapshot.

---

## 1. `Arraial da Vampirada` — mistyped year, stuck in Registration

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
current + upcoming events (wiki/sync.md), so it sits at the bottom of the
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
rows share it — if so that is its own ticket, not a per-row fix.

**Cheaper interim than waiting**: `start`, `finish` and `timezone` are all in the
`UpdateConfig` allowlist (`engine/src/tournament/mod.rs:2646-2649`), so the
organizer or an IC can correct the date in-app today with no code change and no
deletion — which sidesteps the VEKN-footprint gate entirely. Deleting is the
owner's call; correcting is available immediately if the row turns out to be
blocked.

Found 2026-08-15 while measuring the tournament corpus for the Hall of Fame
rebuild (`#581`) — a year histogram of all 8466 live tournaments put exactly one
row in 2034.
