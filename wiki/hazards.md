# Hazards

Non-local traps: behavior not evident from reading the code where it lives. These
are what [KISS](dogmas.md#code) means here — read this before touching the
subsystems named.

Hazards that belong to one subsystem are stated where that subsystem is
documented; this page carries the cross-cutting ones and indexes the rest.

## Fields silently dropped

**A hand-rebuilt `User` or `Sanction` drops every field its author did not
enumerate** — prefer `msgspec.structs.replace`. Five sites carry a field list of
their own: go-online's server-wins re-pull, the detach split's two clear-lists,
the member projection denylist, `/action`'s copy into `event_data` and the
tournament config set. Each derives what it can from the model it mirrors and
asserts the judgement that remains exhaustive against the struct, so a new field
fails a test instead of leaking — [testing](testing.md#traps) names the guards.

**`vekn_id` is deliberately absent from `TournamentActionRequest`.** `/action`
derives `event_data` from that model, so a key reaches the Rust `TournamentEvent`
exactly when it is declared there — Pydantic's `extra="ignore"` drops anything
else a client sends, with no error. The server injects `vekn_id` from the
resolved user *after* the copy; declaring it would reopen the fabricated-id hole.

**A projection change only affects rows written afterwards**, and neither the
access-version handshake nor any test can catch the missing backfill — see
[sync](sync.md#access-levels) for the re-save script and
[testing](testing.md#traps) for why no test covers it.

**Our country rows are ISO codes; the corpora we compare them against are names.**
Every write path normalises through `geonames.stored_country`, so a stored value is
a two-letter code, vekn.net's `XX` unknown-venue placeholder, or nothing. The
legacy dumps, vekn.net and the TWDA archive all quote country *names*, so a
cross-corpus comparison goes through **`geonames.country_key`**, never through
`normalize_country` directly: the resolver returns `None` for a spelling it does
not know (`Czechia`, `South Korea`, `UK`), and treating that as "no country
declared" makes every unknown value equal to every other and **disables the
caller's guard**. `country_key` compares such values as themselves, so an
unrecognised spelling narrows the candidates instead. `normalize_country` is for
resolving a code out of a name, where `None` legitimately means "says nothing" —
the TWDA's `Online`. Which function a caller wants turns on whether it is a
**guard** or a **tie-break**: `find_same_event_tournaments` stamps a vekn id onto
its single survivor, so an unknown spelling must narrow; `reconcile_twda.py` only
ever breaks ties and discards a filter that would empty the candidate set, so there
`XX` and `Online` must both stay open, and switching it to `country_key` would
silently drop the `XX` rows' true matches.

**The TWDA export publishes the country as a name**, expanded back out of the
stored code in `routes/tournaments.py`. The archive's `place` line is permanent and
its convention is `City, Country` spelled out, so exporting the raw field would
regress the published corpus with no way to take it back.

**Dropping NFD combining marks is not an ASCII fold.** ł, ø, æ, ß and friends
decompose to themselves, so a mark-dropping pass leaves a non-ASCII letter
behind — `Paweł` normalizes to `pawe` where an alphanumeric filter eats it, and
to `paweł` where one does not. Either way the accent-free `Pawel` never matches.
The one map that fixes it is `engine/src/cards.rs` `fold_ascii`, pinned by a CI
guard asserting every shipped card name normalizes to pure ASCII, and exported
both ways — `foldAscii` to WASM, `PyEngine.fold_ascii` to Python. Fold through it,
never a hand-written NFD loop: a hand-rolled one in `reconcile_twda.py` was
silently reconstructing six Polish events as duplicates. It lowercases the letters
it maps (`Ł` → `l`) while leaving decomposed ones cased (`É` → `E`), so callers
comparing folded strings must lowercase after it, not rely on it.

## Two implementations of one gate

**A new engine create gate rejects offline tournaments already created under the
old rule.** `create_tournament` is the sole producer on every path
([architecture](architecture.md#event-system)), and the offline-created insert
runs it at `go-online`/`sync-offline` — long after the device minted the row. A
gate added today therefore wedges an event created yesterday: the organizer must
edit the offending field offline before the sync is accepted. Gate on what a
config edit can still fix.

**Authorization runs at two layers** — the REST endpoint and the engine — with the
decision single-sourced in Rust. Frontend wrappers are UX-only and fail closed
([access](access.md)).

**A frontend figure the backend also computes must call the same Rust binding with
the same inputs**, and must match the backend's *inclusion filter* as well as its
formula ([dogmas](dogmas.md#product)).

**The bot's round-timer reminders duplicate the frontend countdown formula** —
the schedule computation and `TimerDisplay.svelte` must stay in lockstep
([discord](discord.md#the-sse-listener)).

**`preview_scores_json` deliberately duplicates the `SetScore` GW/TP cascade** —
the preview runs on not-yet-persisted scores, so the two paths cannot share state.
A cascade change must land on both sides; the single equality test
`test_preview_scores_match_setscore_including_sa_cascade` pins them together, and
one is enough — don't add a second.

## Renames and references

**Lazy imports hide references.** Function-level imports are used across the
tournament routes, the VEKN push and the archon import to break cycles. Renaming a
symbol can therefore break a caller invisibly — invisible to module load, invisible
to a green test suite, and swallowed by the try/except blocks around post-effects.
**Grep all references including in-function imports.**

**Reassigning object references** — sanctions, decks, cooptation on merge or detach
— **must return `BroadcastData` and broadcast**, or other clients stay stale until
their next snapshot resync. Preserve that in any new merge-like flow.

**`finals.seed_order` holds player user_uids**, easily missed in a per-player UID
remap. The offline remap itself uses a naive JSON string replace, whose
substring-collision risk is mitigated only by UUID v7 length.

**Svelte 5 `$props()`**: props must be listed in the destructure, not merely in the
type annotation.

## Consumers that must move together

**The DQ signal is two signals** — `player.state == "Disqualified"` **or** an active
disqualification sanction. Audit every consumer for the combined signal, and make
any DQ create, lift or delete recompute standings.

**Proxy players are excluded-but-not-zeroed**, the inverse of DQ. Consumers
iterating standings unfiltered — league scoring and the VEKN push among them —
leak proxy scores. Filter on `disqualified || non_competing`.

**Standings count by table, not by round.** A finished table scores while its round
is still running — the raffle pools depend on it, reading
`compute_preliminary_standings` live rather than `tournament.standings` so a
mid-round draw sees the tables already done. Anything that gates scoring on the
round finishing breaks them.

**A VP sheet is judged by enumeration, not by walking the ring.** The ring walk
cannot close behind a player who withdrew, so it refuses legal withdrawal endings;
`check_table_vps` decides on the enumerated set of reachable results and keeps the
walk only to name the offending seat. Anything that "simplifies" the check back to
the walk silently blocks real score entry.

**A table's state is decided on change, never re-judged on recompute.** That is
deliberate, not an oversight: `backend/scripts/migrate_from_archon.py` copies legacy
per-seat VPs without validating them (only the file-import path in
`archon_import.py` validates), so a recompute that re-ran `check_table_vps` over
stored history would silently drop every table our checker happens to reject out of
the standings and the rating. Anything that starts re-deriving state centrally
inherits that, and the corpus has never been surveyed.

**Scoring reads `Finished`; "who played" reads seats.** `compute_preliminary_standings`
and `compute_rating_vp_gw` both skip a table that is not `Finished`, but
`players_with_rounds` counts every seat in every table — a player who sat at a
table that never finished did play, even though nothing they did scores. The two
answer different questions and diverge on purpose; a force-finished tournament with
an abandoned round is where you see it.

**The SA −1 VP has three consumers**: preliminary standings, the rating path, and
`SetScore`. All must share the one effective-round resolver or VP, GW and TP
silently diverge. The resolver anchors only on a **finished** table — the ones the
standings score, so a cancelled or still-live seat cannot hold an SA — and its
redirect can land later than the stored round.

**League RTP and global RTP use different bases.** League points use prelim-only
standings VP/GW; the global rating uses totals including finals. Verify the
`points` field, not just the displayed GW/VP.

**"How many players" is two questions, and the wrong one is easy to reach for.**
`players_with_rounds` answers *who played*; `attested_player_count` answers *how
big the field was*. Both live in `engine/src/ratings.rs` and are exported over
PyO3 and WASM — every count now comes from there, so a rule change lands once.
What still has hand-written twins is the played-player **set**
(`ratings.py` `_players_with_rounds`, `tournament-utils.ts` `playedPlayerUids`),
because callers need the uids, not a number. Those are enumeration; the rule is
not in them. Two readings in `backend/src/routes/tournaments.py` stay divergent:
`_played_player_count`, gating the TWDA floor, is seats only with no standings
fallback — so 0 for a rounds-less import — and it *subtracts* non-competing
proxies; and `_winner_deck_twda` sends `len(tournament.players)`, the registered
roster including no-shows, onto the published TWDA header line. Neither is the
rule. `TWDA_MIN_PLAYERS` lives in `db.py` and is shared by both floors that use
it; the *function* is not — the Hall of Fame reads `attested_player_count`,
because `_played_player_count` would score every rounds-less import and every
reconstruction at 0 and empty the page.

That 0 is now load-bearing in a second, unobvious place: it is the only thing
keeping a reconstructed row out of the TWDA submitter. Such a row's event code
*is* the archive's own file key on 1118 of them, so a submission would open a pull
request overwriting the very archive file it was reconstructed from. Giving
`_played_player_count` a standings fallback would make that reachable —
[vekn](vekn.md#outbound).

**The Hall of Fame predicate and `ranking_eligibility` disagree on purpose.** 10
players and the winner's deck on record, against 8 players and a played final:
they are different questions and a unification "fixing" the inconsistency
silently rewrites who is in the Hall of Fame. `user.wins` is likewise no longer a
by-product of the rating recompute — that coupling is what made membership turn
on the unrelated coincidence of having played a rated event, so a historic winner
was invisible. `recompute_wins` enumerates from the tournaments; its optional
user set narrows the rewrite, never the rule. Any new path that finishes,
un-finishes or deletes a tournament has to call it alongside the rating recompute,
or a fresh win waits for the nightly pass — **and so does any path that writes a
deck**, which is the trap, because every deck action sits on
`_RATING_IRRELEVANT_ACTIONS` and skips that block entirely. Rating-irrelevant is
not Hall-of-Fame-irrelevant: uploading the winner's deck admits them and deleting
it evicts them.

`len(rounds) == 0` is not "no results", and never measures field size. Every
pre-2014 import is rounds-less while carrying a full scored result sheet, so the
rounds-less branch of `players_with_rounds` already returns a real number for the
whole historic corpus. Measuring `len(rounds)` and reading it as a count has
already produced one confidently wrong conclusion about the archive.

**`external_ids['twda']` means *reconstructed from the archive*, not *linked to
it*.** Seven unrelated decisions read it that way, from the VEKN adopt carve-out to
the public archival badge, so an event we already held that the archive also
describes carries `twda_entry` instead — [vekn](vekn.md#inbound) enumerates them.

**`player_count` is a taken name.** `engine/src/league.rs` reads
`tournament["player_count"]` from a **caller-synthesized** summary object, not from
the Tournament model. A `player_count` field on `Tournament` would make real
tournament JSON silently satisfy that read with different semantics — which is why
the attested size is stored as `reported_player_count`. Name any further count
field the same way.

**Role writes have two out-of-band consumers** — the Discord Linked Roles push,
which fires on any role delta with no periodic reconcile, and the resync
fingerprint, which moves only for IC and NC. A role writer outside the users route
skips both silently ([access](access.md#capabilities)).

**A new full-access branch in `entitled_level` wires only the live path.** A
non-country, non-own-object full grant must also be added to the overlay frames, or
a resync re-delivers the lower projection ([sync](sync.md#access-entitlement)).

**Adding a precomputed access column** is warranted only when projection *content*
must vary by viewer at the same level. Otherwise collapse onto an existing column
and shrink the lower one. The base64 contact obfuscation is a harvester speed-bump,
not access control.

## Concurrency and connections

**Never start a DB-touching task inside a transaction** — the full connection
discipline is [architecture](architecture.md#database-access), and the ambient
connection raises if reached from another task.

**The pool is autocommit**, so a multi-statement write needing consistency must
take an explicit transaction. The object-delete and purge paths are the fixed
exemplar; don't re-fix them.

**Web Push VAPID, backwards from intuition**: the claims dict **is** mutated per
send, so each send needs a fresh one; the Vapid instance is **not**, so it is safe
to share across threads.

**The sync resync branch reconnects with no delay.** Route any resync reconnect
through the backoff, or a persistent cause spins a full-speed clear-and-reconnect
loop ([sync](sync.md#resync)).

## Cards and decks

**The card model has three name fields plus variants**, all four being parser
lookup keys, with distinct roles: printed (display), unique (text export), full
(the image filename is the normalized full name).

**Card sets are display *names*, not codes**, so a prefix test like
`starts_with("V5")` against a set field matches nothing.

**The deck parser's count-strip and prefix match miscount count-less lines** —
card names ending in digits or containing a slash are the failure cases. The fix is
exact-key gating, not a looser regex.

## Rounds and the bot

**Round lifecycle**: `RestoreRound` can re-derive to fully Finished; the finals are
not in `rounds`; the timer is online-only. Check these when reviewing any
round-lifecycle hook.

**The bot's active-table detection tags "finals" on seating truthiness, not
completion**, so consumers that should stop at completion — the timer reminders —
over-trigger. There is no top-level table result to gate on; gate on the pending
predicate instead.

**On the bot's live path the tournament frame precedes participant identity
frames**, so reconcile logic using the name cache for a just-added organizer or
player is one message stale. Catch-up is safe
([sync](sync.md#the-sse-endpoint)).

## Ratings and migration

**The ratings no-change guard converges only if its denormalized inputs are
stable** — the entry's embedded tournament name and its date fallback chain. A
flip-flopping name or a both-null date makes the daily job re-save forever.

**Dropping VEKN-less members is not reference-free.** Measured: dropping the 142
VEKN-less members orphans 9 references — 4 players and 5 seats — across 3 finished
tournaments, because legacy archon never enforced a VEKN id at registration.

**The `vekn_id` unique index spans tombstones**: a soft-deleted user still reserves
its number while `deleted_at`-filtered lookups disagree, so a seed insert can crash
on a reserved number. Reachable on steady-state nightly merges, since an admin
user-delete keeps the `vekn_id`.

**`authState.user` adopts its own sync frame, minus `calendar_token`.** The
signed-in user's row arrives over SSE like anyone else's, and every other surface
reads that synced copy — so auth adopts it wholesale rather than merging field by
field, and carries `calendar_token` forward because no projection holds it. **A
second non-projected field on `User` must join that carry-forward** or it is
wiped the first time the row syncs.

The adoption is what makes a second writer on a `User` field safe: `PATCH
/auth/me` replaces the **whole** `community_links` array, so an owner saving from
a stale copy would silently revert a moderator's edit. For the same reason an
editing surface must derive from the live user rather than snapshot it at mount —
`ProfileView` does, deliberately, against the general rule that a modal captures
its item at open time.

## Outbound fetches

**`GET /auth/me/link-title` fetches an address a member typed** — the only place
the server does, every other outbound call naming a hard-coded host.
`link_preview.py` resolves the host and refuses any non-global address before
connecting, re-checks on each redirect hop, and caps the body at 64 KB and the
exchange at 5 s; the route itself is member-gated and holds a per-user quota, as
`feedback.py` does for the other member-triggered outbound call. aiohttp resolves
a second time, so a DNS rebind between the two resolutions stays reachable; what
keeps that acceptable is that the response is a title rather than a body.
Anything else that comes to fetch a user-supplied URL goes through that module
instead of growing its own guard.

## Deploy

**A scheduled job whose period reaches a day never fires.** The backend unit sets
`RuntimeMaxSec=1d` — a daily restart that re-fetches the krcg-static card data
without a redeploy — and APScheduler 3.x fires an `IntervalTrigger` at start + N,
not immediately. Registration happens seconds into startup, so systemd's kill
always precedes the first fire of a 24-hour job: it is not a race a quieter
restart schedule wins. What survives is a `CronTrigger` at a fixed hour, a period
comfortably under the day, or an explicit `asyncio.create_task` kick at startup —
so **register a daily job as a `CronTrigger` with an explicit `timezone`**, since
nothing sets one on the servers and a bare `hour=` is a claim about a machine
setting. A restart takes seconds and there is no jobstore, so the cron hour the
drifting restart happens to land on loses that day's run; every one of these jobs
is idempotent, which is why that is tolerable rather than something to build
around.

**Production nginx proxies only an allowlist of top-level prefixes.** A new route
under an existing prefix is fine; a new top-level segment 404s in production while
passing dev CORS and the test suite ([access](access.md#deployment-gate)).

**A `ClientTimeout` breach raises `asyncio.TimeoutError`, not an
`aiohttp.ClientError`**, so `except aiohttp.ClientError` misses timeouts on every
external-proxy route — feedback, TWDA, web push ([vekn](vekn.md#outage-resilience)).

**`EXPLAIN` the `DECLARE … CURSOR FOR`, not the bare `SELECT`** — a named cursor is
costed with `cursor_tuple_fraction` and can report a different scan than the one
that runs ([sync](sync.md#streaming)).

**A backend-first deploy is safe by design**: an unknown snapshot type is counted
toward the `eof` total and ignored. Do not "fix" that by counting only recognised
types ([sync](sync.md#adding-a-new-object-type)).
