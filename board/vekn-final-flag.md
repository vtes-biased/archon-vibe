Doc-impact: `wiki/vekn.md`, `wiki/vekn-decommission.md`.

## Cause

`b541a36c` (2026-06-21) changed `push_tournament_event` from
`1 if tournament.finals or tournament.max_rounds > 0 else 0` to
`1 if tournament.finals else 0`. A planned event has no finals yet, so it is filed
`NR`, not `NR+F`. Open-rounds events, the reason given for the change, are never
pushed.

## Evidence, read 2026-11-01 through beta's VEKN client (`fetch_event`)

| Event | Calendar | Upload |
|---|---|---|
| 13597, 13606 | `3R+F`, `2R+F` | accepted |
| 13686, 13668, 13487 | `2R`, `3R`, `3R` | refused, provided = expected + 1 |
| 13692 (created by Archon 2026-10-31) | `2R` | not finished yet |
| 13565 | `2R+F` | refused 2 / 3: expected counts the final, provided does not |
| 13085 | `0R` | refused 4 / 0 |

13565 confirms vekn.net compares against `nrounds + final`, so the wiki's "every
event with a final disagrees by one" holds only for an entry without the flag.

## State on 2026-10-31

44 tournaments refused hourly on the round count: 37 at provided = expected + 1,
7 others (4/0, 4/2 twice, 2/3, 2/4, 4/5 twice) to check one by one. The fix does
not repair them: the API has no calendar update, so each entry is corrected on
vekn.net, after which the hourly batch retries unstamped rows by itself.

## Open

- Trade-off: an event filed with the flag that ends with no final is refused the
  other way. Rate unmeasured; beta holds too few recent events.

## Correction list for the VEKN admins (Ankha, giotto)

Read live on 2026-11-01. 37 finished need the final, 7 a round fix, 2 are on hold
(13552, 13565: vekn.net reports 2 provided, to check on our side) and 59 upcoming lack
`+F`. 13495 calendars as Ricsiszulinap where our record says Army of Rats: confirm
it is the same event. The deferred item takes its list from these groups:

- Add the final: 13450, 13487, 13488, 13495, 13517, 13524, 13534, 13544, 13546, 13555, 13560, 13561, 13567, 13574, 13576, 13577, 13587, 13599, 13610, 13612, 13615, 13617, 13618, 13620, 13622, 13626, 13634, 13635, 13644, 13645, 13646, 13648, 13652, 13662, 13668, 13675, 13686.
- Fix the rounds: 13085 0R→3R+F, 13110 4R+F→3R+F, 13359 4R+F→3R+F, 13367 4R+F→3R+F, 13449 2R→3R+F, 13455 2R→3R+F, 13572 2R+F→3R+F.
- Upcoming: 13452, 13624, 13628, 13674, 13690, 13470, 13654, 13673, 13682, 13692, 13621, 13676, 13680, 13685, 13619, 13661, 13665, 13669, 13670, 13679, 13681, 13613, 13623, 13656, 13647, 13659, 13671, 13545, 13687, 13650, 13598, 13636, 13651, 13677, 13600, 13601, 13614, 13625, 13642, 13678, 13683, 13691, 13518, 13519, 13640, 13688, 13520, 13657, 13689, 13663, 13547, 13649, 13629, 13630, 13631, 13632, 13633, 13643, 13548.
