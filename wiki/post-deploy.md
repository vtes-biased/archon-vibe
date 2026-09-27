# Post-deploy — what a production deploy unlocks

Actions that only become safe once a specific commit is live on production. The
board holds no waiting state and a subsystem page is no place for a runbook, so
they park here: one `##` section per item, **completion is deletion**, and an
empty page is the normal state.

`/post-deploy` runs them, ahead of the feedback issues it closes. Unlike the work
deferred in [vekn-decommission](vekn-decommission.md), a fired trigger here does
**not** go back through `/intake`: that trigger fires every release, and an item
reaches this page only after passing egress review, so the one decision left is
the owner's go/no-go.

**An item belongs here only if `/post-deploy` could execute it with nothing but
that go/no-go.** Work carrying judgment — reviewing a dedup's output, diffing Hall
of Fame membership either side of a backfill — stays a board line that happens to
have a production step. Without that boundary this page becomes a second board.

A section whose first line is **Migration** followed by a slug is the standing
proof of an entry in `backend/src/migrations.py`
([architecture](architecture.md#stored-value-migrations)). It has nothing to
run — the entry rewrote the rows before the process served — but its queries are
the only record that the rewrite reached a given database, so it is deleted only
once **every** long-lived one answers 0, and the entry it names dies in the same
commit. `just migration-pairing` fails on either half outliving the other.

**Every item names the commit that gates it**, so `git tag --contains <sha>`
answers whether a given deploy has made it actionable — the same check
`/post-deploy` already runs against a feedback issue's fix. An item states what
gates it and why, what to run, what proves it worked, and what it owes afterwards:
people to tell, and the wiki text that dies with it.

## Check the per-client API throttle on beta

Gated by `17a036ac`, which moves the public API's stream and lookup budgets from
nginx's per-address zones into the API process, keyed on the token's `client_id`
([public-api](public-api.md#deployment)). Before that deploy beta still throttles
per address, so the counts below prove nothing. Run on `https://api.archon.krcg.org`
after `just deploy-beta`, with two `api:read` clients registered there (A, B), each
minting a daemon token through `/oauth/token` into `$TOKEN_A` / `$TOKEN_B`:

```sh
burst() { for i in $(seq 1 15); do curl -s -o /dev/null -w '%{http_code} ' \
  -H "Authorization: Bearer $1" https://api.archon.krcg.org/v1/leagues; done; echo; }
burst "$TOKEN_A"                       # from here: 11 × 200, then 429
```

It worked when, after a minute's rest each time: A's 11 requests split across
this machine and the beta box itself (`ssh deploy@57.129.110.107` with the same
loop) 429 on the twelfth overall, exactly as from one address; and A then B, both
from one address, each get their own 11 × 200. Nothing is owed after.

## Check the `profile:email` grant on beta

Gated by `4ca6cdf6`, which adds the scope ([access](access.md#oauth2-provider)).
Before `just deploy-beta` carries it, beta refuses the scope as invalid. On
`https://archon.krcg.org`, register the vekn-forum client from Developer with
`profile:read` and `profile:email` checked, its purpose stated, and the forum's
callback as redirect URI. Then sign in through it three times, asking for
`profile:email`, for `profile:read`, and for `profile:email` as a member whose
only address is the one on their profile, and read `/oauth/userinfo` with each
access token.

It worked when the first consent page shows the purpose under `profile:email`
and its `userinfo` carries `sub`, `roles`, `vekn_id`, `capabilities` and the
member's verified `email`; the other two carry no `email`. Nothing is owed after:
vekn-forum's `wiki/archon.md` already describes the scope, and a failure goes back
through `/intake` here.

## Resubmit the TWDA entries sent with the roster count

Gated by `c30f107b`, which makes the TWDA header publish `attested_player_count`
instead of the registered roster, and `93ce3934`, the last of the commits that keep
the maintainer's header lines on an update, turn the old ISO dates into the US
form and hold what the script cannot compare. Run before both, the resubmission
would publish the same wrong count again, or revert every city the maintainer
added. Tell the TWDA admin a batch of `Update TWD` pull requests is coming: they
keep the name and place lines the maintainer wrote, and turn a date still in the
old ISO form into the US one ([vekn](vekn.md#outbound)). Then list:

```sh
sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  /opt/archon/backend/.venv/bin/python \
  /opt/archon/backend/scripts/resubmit_twda_counts.py'
```

The listing reads each submission's count from GitHub — the open pull request's
branch, else the archive's file — since the maintainer corrects counts by hand, and
lists it where that differs from `attested_player_count`; it also lists events the
old seats-only floor skipped that now clear it. Five kinds are held out of
`--apply` for the TWDA admin: `below floor`, an archived event whose field was
under 10, where a resubmission would only record a skip; `not in the archive`, an
entry the maintainer removed or refused, which a resubmission would add back;
`hand-corrected`, an archived count that differs from the one our branch last
sent, so the maintainer set it; `no branch to compare`, where our branch is gone
and a hand correction cannot be ruled out; and `no count line`, a file whose
header carries none. Rerun with
`--apply`: every other listed event opens or moves a pull request on the archive
repo. It worked when a second report-only run lists only held rows. Delete this
section and
`backend/scripts/resubmit_twda_counts.py` together.

## Fill the city of existing tournaments

Gated by `da7d0cc3`, which adds the tournament city and makes it required for an
in-person event ([tournaments](tournaments.md#configuration)), and `dd87e9f9`, which
ships the resolved mapping. Before them the rows have no field to hold the city.
List:

```sh
sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \
  /opt/archon/backend/.venv/bin/python \
  /opt/archon/backend/scripts/backfill_tournament_cities.py'
```

The cities are `backend/scripts/tournament_cities.json`, resolved offline from a
production export of September 2026. The TWDA entry's place comes first, then the
address, then the TWDA city of the venue's other events, then vekn.net's venue
record — its city, else its coordinates, unless they contradict its own events. A
town too small for the city list is taken to the nearest listed city within 60 km;
a bare state or region is never read as a city. A missing country comes from the
archive, else the event's name, and 9 events whose archive country contradicts
vekn.net's are left out for vekn.net to correct. It covers 8,909 of the 9,345
in-person events; 127 stay without a city and 300 without a country, 236 of those
from 2004–2010. The listing prints each city it would write with its source and
method, names every mapped row it would not — `gone`, `online now`, `country
differs` — and lists the in-person events the mapping leaves without a city, those
created since the export included. Rerun with `--apply`. It worked when a second
report-only run counts no `write`. Delete this section, the script and its mapping
together.
