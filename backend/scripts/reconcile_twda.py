"""Resolve every TWDA entry against our live tournament corpus. Read-only.

Half the TWDA carries no vekn event id — the archive only began linking events
around 2013 — so `import_twda_decks` never sees those entries and the historic
Hall of Fame is derived from the half we can link. Most of the unlinked entries
are events we ALREADY HOLD, imported from legacy archon without a vekn id: the
gap is a linking gap, not an event gap, and reconstructing blind would mint a
thousand duplicates.

    # report, and write the proposed decisions
    /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/reconcile_twda.py --emit-decisions /tmp/twda.tsv

    # also write the human-readable review table, and re-derive the tier-3 score
    … reconcile_twda.py --emit-decisions /tmp/twda.tsv --report /tmp/table.md --validate

This script creates nothing and has no --apply: its output is a decisions file a
human reviews, which the reconstruction then consumes. Entries left unreviewed
are skipped by that consumer, never created.

Four tiers, strongest first:

1. an archon.vekn.net link in `event_link`. The two url forms quote uids from two
   different id spaces — the live /tournaments/<uid> one ours, the dead legacy
   /tournament/<uid>/display.html one the uid legacy archon minted, which the
   import kept in external_ids['archon'] — so both indexes are consulted. A uid
   neither resolves is reported, never passed down to the weaker tiers.
2. the vekn event id. NOT infallible: an organizer can submit under an event id
   they later abandoned (12797 points at a 0-player row named "delete me" while
   the real event is 12794). A disagreeing winner name alone does not unseat it —
   ours are routinely fuller than the archive's — only a rival event on the same
   date actually won by that player does. An id we do not hold falls through to
   tier 3, since we often hold the event without its id.
3. name-free — date +/- 1 day, winner name, country narrowing, with the event
   name and then the player count breaking a tie. Neither is a KEY: 869 of our
   pre-2014 tournaments are named "Imported VTES Event", so name matching tops
   out around 22% of the corpus while winner name resolves half of it, and the
   count is absent on 100 entries and collides freely across the corpus. As a
   tie-break the count is decisive — the archive and the archon row agree on it
   exactly for most of the same-winner-same-weekend clusters this tier stalls on.
   Measured against the tier-2 entries as ground truth, this tier is 99.9%
   precise at 95.6% recall.
4. no match — a reconstruction candidate.

A collision pass then runs over the whole verdict set, because the tiers above
judge one entry at a time and cannot see that two of them claimed one tournament.

Country only ever BREAKS TIES: a candidate that declares no country stays in, and
a filter that would empty the candidate set is discarded. Both sides are
normalized to ISO codes first because 208 live rows store a country NAME in a
field that holds a code ("Brazil", not "BR"), which an exact match would drop.
"""

import argparse
import asyncio
import importlib.util
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import aiohttp  # noqa: E402

from backend.src import db  # noqa: E402
from backend.src.geonames import normalize_country  # noqa: E402
from backend.src.models import ObjectType  # noqa: E402
from backend.src.twda_import import TWDA_URL, extract_vekn_event_id  # noqa: E402

_ARCHON_UID_RE = re.compile(
    r"archon\.vekn\.net/tournaments?/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CORPUS_QUERY = """
    SELECT t.uid,
           t."full"->>'start',
           coalesce(t."full"->>'country', ''),
           btrim(coalesce(t."full"->>'name', '')),
           coalesce(t."full"->>'winner', ''),
           coalesce(u."full"->>'name', ''),
           coalesce(t."full"->'external_ids'->>'vekn', ''),
           coalesce(t."full"->'external_ids'->>'archon', ''),
           jsonb_array_length(coalesce(t."full"->'players', '[]'::jsonb))
    FROM objects t
    LEFT JOIN objects u
      ON u.type = %s AND u.deleted_at IS NULL AND u.uid = t."full"->>'winner'
    WHERE t.type = %s AND t.deleted_at IS NULL AND t."full"->>'start' IS NOT NULL
"""


def normalize(value: str) -> str:
    """Casefold, strip diacritics and punctuation — for comparing names."""
    stripped = "".join(
        c
        for c in unicodedata.normalize("NFD", value or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def archon_uid(entry: dict) -> str | None:
    match = _ARCHON_UID_RE.search(entry.get("event_link", "") or "")
    return match.group(1).lower() if match else None


def twda_country(entry: dict) -> str | None:
    """The ISO code from a TWDA `place` ("City (STATE), Country").

    "Online" is a pseudo-country here and resolves to None, which is what keeps
    online events from being filtered as if they had a location.
    """
    place = (entry.get("place") or "").strip()
    return normalize_country(place.rsplit(",", 1)[-1]) if place else None


class Corpus:
    """Our live tournaments, indexed the four ways the tiers look them up."""

    def __init__(self, rows: list[tuple]):
        self.by_uid: dict[str, dict] = {}
        self.by_archon: dict[str, dict] = {}
        self.by_vekn: dict[str, list[dict]] = defaultdict(list)
        self.by_day: dict[str, list[dict]] = defaultdict(list)
        for (
            uid,
            start,
            country,
            name,
            winner_uid,
            winner_name,
            vekn,
            archon,
            size,
        ) in rows:
            row = {
                "uid": uid,
                "start": start,
                "cc": normalize_country(country),
                "name": name,
                "winner_uid": winner_uid,
                "winner": normalize(winner_name),
                "vekn": vekn,
                "size": size,
            }
            self.by_uid[uid] = row
            if archon:
                self.by_archon[archon.lower()] = row
            if vekn:
                self.by_vekn[vekn].append(row)
            self.by_day[start[:10]].append(row)

    def around(self, day: date) -> list[dict]:
        """Candidates within a day either side — our start carries a GUESSED
        venue timezone while the TWDA date is a bare local one, so the same
        event routinely lands on the adjacent day."""
        return [
            row
            for offset in (-1, 0, 1)
            for row in self.by_day.get((day + timedelta(days=offset)).isoformat(), [])
        ]


def winner_candidates(entry: dict, corpus: Corpus) -> list[dict]:
    """Our tournaments won by this entry's player within a day of its date.

    The event NAME is not consulted: 869 of our pre-2014 rows are named
    "Imported VTES Event", so the name carries no information for a quarter of
    the era this reconciles. Country only narrows — a candidate declaring none
    stays in, and a filter that would empty the set is discarded.
    """
    player = normalize(entry.get("player", ""))
    day = entry.get("date", "")
    if not player or not _ISO_DATE_RE.match(day):
        return []
    hits = [
        row for row in corpus.around(date.fromisoformat(day)) if row["winner"] == player
    ]
    country = twda_country(entry)
    if country:
        narrowed = [row for row in hits if not row["cc"] or row["cc"] == country]
        if narrowed:
            return narrowed
    return hits


def resolve(entry: dict, corpus: Corpus) -> tuple[str, str, str]:
    """Return (action, target, why) for one TWDA entry."""
    uid = archon_uid(entry)
    if uid:
        # The two link forms carry uids from two different id spaces: the live
        # one quotes our uid, the dead legacy one quotes the uid legacy archon
        # minted, which we keep in external_ids['archon'] on the imported row.
        row = corpus.by_uid.get(uid) or corpus.by_archon.get(uid)
        if row:
            return "attach", row["uid"], "own link"
        return "review", "", "own link resolves to nothing"

    player = normalize(entry.get("player", ""))
    vekn = extract_vekn_event_id(entry)
    if vekn and corpus.by_vekn.get(vekn):
        candidates = corpus.by_vekn[vekn]
        if len(candidates) > 1:
            return (
                "review",
                ",".join(r["uid"] for r in candidates),
                "vekn id duplicated",
            )
        row = candidates[0]
        rivals = [r for r in winner_candidates(entry, corpus) if r["uid"] != row["uid"]]
        if row["winner"] != player and len(rivals) == 1:
            return "review", f"{row['uid']},{rivals[0]['uid']}", "vekn id contested"
        return "attach", row["uid"], "vekn id"

    if not _ISO_DATE_RE.match(entry.get("date", "")):
        return "review", "", "no usable date"
    if not player:
        return "review", "", "no winner name"

    hits = winner_candidates(entry, corpus)
    if len(hits) == 1:
        return "attach", hits[0]["uid"], "winner+date"
    if len(hits) > 1:
        # `event` is the event name; `name` is the DECK's.
        event = normalize(entry.get("event", ""))
        exact = [row for row in hits if normalize(row["name"]) == event]
        if len(exact) == 1:
            return "attach", exact[0]["uid"], "winner+date+name"
        size = entry.get("players_count")
        sized = [row for row in hits if size and row["size"] == size]
        if len(sized) == 1:
            return "attach", sized[0]["uid"], "winner+date+size"
        return "review", ",".join(row["uid"] for row in hits), f"{len(hits)} candidates"
    return "create", "", "no candidate"


_TIER_STRENGTH = {
    "own link": 4,
    "vekn id": 3,
    "winner+date+name": 2,
    "winner+date+size": 2,
    "winner+date": 1,
}


def demote_collisions(verdicts: list[list]) -> int:
    """Send every attach that contests an already-claimed tournament back to the queue.

    `resolve` sees one entry at a time and so cannot notice that two of them
    landed on the same tournament. The TWDA holds one winning deck per event, so
    a collision means at most one claimant is right and the other is a real event
    we do not hold — attaching it would both mislabel a tournament and lose a win.
    The stronger tier keeps the target; a tie sends every claimant to the queue.
    """
    claims: dict[str, list[list]] = defaultdict(list)
    for verdict in verdicts:
        if verdict[1] == "attach":
            claims[verdict[2]].append(verdict)
    demoted = 0
    for group in claims.values():
        if len(group) < 2:
            continue
        ranked = sorted(group, key=lambda v: -_TIER_STRENGTH[v[3]])
        strongest = _TIER_STRENGTH[ranked[0][3]]
        keep = ranked[0] if strongest > _TIER_STRENGTH[ranked[1][3]] else None
        for verdict in group:
            if verdict is not keep:
                verdict[1], verdict[3] = "review", "target claimed by another entry"
                demoted += 1
    return demoted


def validate(entries: list[dict], corpus: Corpus) -> str:
    """Score the name-free tier against the linked entries, which know the answer.

    Every entry whose vekn id resolves to exactly one of our tournaments is a free
    labelled example: hide the id and the link, let the weak tier answer blind, and
    compare. This is the number that justifies keying on the winner rather than the
    event name, so it has to stay re-derivable as both corpora move.
    """
    truth = {
        str(e.get("id", "")): corpus.by_vekn[extract_vekn_event_id(e)][0]["uid"]
        for e in entries
        if extract_vekn_event_id(e)
        and len(corpus.by_vekn.get(extract_vekn_event_id(e), [])) == 1
    }
    right = wrong = 0
    for entry in entries:
        known = truth.get(str(entry.get("id", "")))
        if not known:
            continue
        blind = {k: v for k, v in entry.items() if k not in ("id", "event_link")}
        action, target, _ = resolve(blind, corpus)
        if action == "attach":
            right += target == known
            wrong += target != known
    answered = right + wrong
    if not answered:
        return "no labelled entries — cannot validate"
    return (
        f"name-free tier: {right}/{answered} = {right / answered:.1%} precise, "
        f"recall {answered / len(truth):.1%} over {len(truth)} labelled entries"
    )


async def fetch_twda() -> list[dict]:
    timeout = aiohttp.ClientTimeout(total=120.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(TWDA_URL) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def load_corpus() -> Corpus:
    async with db.get_connection() as conn:
        result = await conn.execute(
            CORPUS_QUERY, (ObjectType.USER, ObjectType.TOURNAMENT)
        )
        return Corpus(await result.fetchall())


def write_report(path: str, verdicts: list[tuple], corpus: Corpus, reasons: Counter):
    review = [v for v in verdicts if v[1] == "review"]
    create = [v for v in verdicts if v[1] == "create"]
    lines = [
        "# TWDA event reconciliation",
        "",
        "Read-only output of `backend/scripts/reconcile_twda.py`. Deleted with the",
        "board line that owns it.",
        "",
        f"Run {datetime.now(UTC).date().isoformat()} against {len(corpus.by_uid)} live "
        f"tournaments and {len(verdicts)} TWDA entries. The archive grows weekly —"
        " re-run before acting on a stale queue.",
        "",
        "| outcome | entries |",
        "|---|---|",
    ]
    for reason, count in reasons.most_common():
        lines.append(f"| {reason} | {count} |")
    lines += [
        "",
        f"**{len(create)} entries have no candidate** and are the reconstruction.",
        f"**{len(review)} need a human.**",
        "",
        "## Review queue",
        "",
        "| twda id | date | winner | twda event | why | candidates |",
        "|---|---|---|---|---|---|",
    ]
    for entry_id, _, target, why, meta in review:
        cands = " ".join(
            # 13 chars is where uuid7 stops colliding across the corpus — the
            # 8-char prefix is shared by thousands of rows minted the same ms.
            f"`{u[:13]}` {corpus.by_uid[u]['name']!r}"
            f"@{corpus.by_uid[u]['start'][:10]}/{corpus.by_uid[u]['size']}p"
            for u in target.split(",")
            if u in corpus.by_uid
        )
        lines.append(
            f"| {entry_id} | {meta['date']} | {meta['player']} | "
            f"{meta['name']} ({meta['size'] or '?'}p) | {why} | {cands} |"
        )
    Path(path).write_text("\n".join(lines) + "\n")


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    os.environ["DATABASE_URL"] = args.dsn
    await db.init_db()
    try:
        corpus = await load_corpus()
        print(f"corpus: {len(corpus.by_uid)} live tournaments")
        entries = await fetch_twda()
        print(f"twda:   {len(entries)} entries")

        verdicts = []
        for entry in entries:
            action, target, why = resolve(entry, corpus)
            verdicts.append(
                [
                    str(entry.get("id", "")),
                    action,
                    target,
                    why,
                    {
                        "date": entry.get("date", ""),
                        "player": entry.get("player", ""),
                        "name": entry.get("event", ""),
                        "size": entry.get("players_count"),
                    },
                ]
            )
        print(f"\ncontested targets requeued: {demote_collisions(verdicts)}")
        reasons = Counter(f"{v[1]} — {v[3]}" for v in verdicts)

        print()
        for reason, count in reasons.most_common():
            print(f"  {count:6d}  {reason}")
        totals = Counter(v[1] for v in verdicts)
        print(
            f"\n  attach {totals['attach']}   create {totals['create']}   "
            f"review {totals['review']}"
        )
        if args.validate:
            print(f"\n  {validate(entries, corpus)}")

        if args.emit_decisions:
            body = "\n".join(
                f"{entry_id}\t{action}"
                + (f":{target}" if action == "attach" and target else "")
                + (f"\t{target}" if action == "review" and target else "")
                for entry_id, action, target, _, _ in verdicts
            )
            Path(args.emit_decisions).write_text(
                "# twda_id<TAB>action — attach:<tournament_uid>, create, skip, or\n"
                "# review (UNDECIDED, with candidate uids). Every review line must\n"
                "# become one of the others before this file is consumed.\n"
                + body
                + "\n"
            )
            print(f"\nDecisions written to {args.emit_decisions} — review before use.")
        if args.report:
            write_report(args.report, verdicts, corpus, reasons)
            print(f"Review table written to {args.report}.")
        return 0
    finally:
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument("--emit-decisions", metavar="PATH", help="write the decisions file")
    p.add_argument("--report", metavar="PATH", help="write the human review table")
    p.add_argument(
        "--validate",
        action="store_true",
        help="score the name-free tier against the vekn-linked entries",
    )
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
