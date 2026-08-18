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
   neither resolves is reported, never passed down to the weaker tiers. The
   short /t/<code> form is the one we emit ourselves, so it is what closes the
   round trip on everything we submit from now on.
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
import importlib.resources
import importlib.util
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import aiohttp  # noqa: E402
from archon_engine import PyEngine  # noqa: E402

from backend.src import db  # noqa: E402
from backend.src.geonames import normalize_country  # noqa: E402
from backend.src.models import ObjectType  # noqa: E402
from backend.src.twda_import import TWDA_URL, extract_vekn_event_id  # noqa: E402

_engine = PyEngine()

_ARCHON_UID_RE = re.compile(
    r"archon\.vekn\.net/tournaments?/"
    r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.I,
)
_ARCHON_CODE_RE = re.compile(r"archon\.vekn\.net/t/([0-9a-zA-Z]+)", re.I)
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
           coalesce(t."full"->>'event_code', ''),
           jsonb_array_length(coalesce(t."full"->'players', '[]'::jsonb))
    FROM objects t
    LEFT JOIN objects u
      ON u.type = %s AND u.deleted_at IS NULL AND u.uid = t."full"->>'winner'
    WHERE t.type = %s AND t.deleted_at IS NULL AND t."full"->>'start' IS NOT NULL
"""


def normalize(value: str) -> str:
    """Casefold, fold to ASCII and drop punctuation — for comparing names.

    The fold must go through the engine, not a bare NFD mark-drop: ł does not
    decompose, so "Paweł" would keep it, the alphanumeric filter would eat it,
    and the archive's ASCII "Pawel" would never match.
    """
    return re.sub(r"[^a-z0-9]+", " ", _engine.fold_ascii(value or "").lower()).strip()


def archon_uid(entry: dict) -> str | None:
    match = _ARCHON_UID_RE.search(entry.get("event_link", "") or "")
    return match.group(1).lower() if match else None


def archon_code(entry: dict) -> str | None:
    match = _ARCHON_CODE_RE.search(entry.get("event_link", "") or "")
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
        self.by_code: dict[str, dict] = {}
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
            code,
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
            if code:
                self.by_code[code.lower()] = row
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


ROSTER_QUERY = """
    SELECT uid, btrim(coalesce("full"->>'name', ''))
    FROM objects WHERE type = %s AND deleted_at IS NULL
"""

# Diminutives seen in the confirmed matches plus their obvious siblings.
# Deliberately tiny: a longer list would fire on names it was never scored against.
NICK = {
    "tomek": "tomasz", "mike": "michael", "jon": "john", "jonny": "johnny",
    "bob": "robert", "rob": "robert", "bill": "william", "will": "william",
    "dave": "david", "dan": "daniel", "tom": "thomas", "chris": "christopher",
    "nick": "nicholas", "matt": "matthew", "steve": "stephen", "jim": "james",
    "pete": "peter", "rick": "richard", "dick": "richard", "ken": "kenneth",
    "greg": "gregory", "andy": "andrew", "tony": "anthony", "joe": "joseph",
    "ed": "edward", "sam": "samuel", "ben": "benjamin", "alex": "alexander",
    "josh": "joshua", "zack": "zachary", "gabe": "gabriel", "vinny": "vincent",
}  # fmt: skip


# How many members may share a surname before the surname-anchored classes stop
# being evidence. Every value from 1 to 5 scores 100% on the bootstrap; 3 is the
# one the earlier pass was validated at.
MAX_SHARING_SURNAME = 3


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


class Roster:
    """Our members, indexed the four ways the winner passes look them up."""

    def __init__(self, rows: list[tuple]):
        self.by_name: dict[str, list[dict]] = defaultdict(list)
        self.by_surname: dict[str, list[dict]] = defaultdict(list)
        self.by_token: dict[str, list[dict]] = defaultdict(list)
        # Bucketed by the sorted letter-set of each token's first 4 characters,
        # so a transposition or a doubled letter still lands somewhere comparable.
        self.buckets: dict[str, set[str]] = defaultdict(set)
        for uid, name in rows:
            key = normalize(name)
            if not key:
                continue
            member = {"uid": uid, "name": name, "key": key}
            self.by_name[key].append(member)
            tokens = key.split()
            self.by_surname[tokens[-1]].append(member)
            for token in set(tokens):
                self.by_token[token].append(member)
                if len(token) >= 4:
                    self.buckets["".join(sorted(set(token[:4])))].add(key)

    def exact(self, name: str) -> list[dict]:
        return self.by_name.get(name, [])

    def classes(self, name: str) -> tuple[str, list[dict]]:
        """(class, members) — the strongest surname-anchored class yielding one member.

        Country is deliberately not a tie-break anywhere in here: scored over the
        bootstrap it fired 4 times and got 1 wrong, against 1095/1095 for the
        paths that need no tie-break at all.
        """
        tokens = name.split()
        if len(tokens) < 2:
            return "too-short", []
        surname, given = tokens[-1], tokens[:-1]

        # 1. the archive carries surnames the member record drops. Anchored on the
        # rarest token so the scan stays small. Two-token floor: a member recorded
        # as "Nick ?" is a subset of every "Nick <surname>" in the archive.
        rarest = min(tokens, key=lambda t: len(self.by_token.get(t, [])))
        subset = [
            m
            for m in self.by_token.get(rarest, [])
            if len(m["key"].split()) >= 2 and set(m["key"].split()) <= set(tokens)
        ]
        if len(subset) == 1:
            return "member-subset", subset

        # Everything below rests on "same surname, given names correspond", which
        # on a crowded surname is not evidence — that is where the bootstrap's one
        # wrong match sat. Refuse, and let review turn it into a ruling.
        pool = self.by_surname.get(surname, [])
        if not pool:
            return "no surname", []
        if len(pool) > MAX_SHARING_SURNAME:
            return f"surname-only ({len(pool)})", pool

        # 2. same surname, one given name a prefix of the other. The floor is on
        # the SHORTER side, or a lone initial or particle satisfies it.
        prefix = [
            m
            for m in pool
            if (g := m["key"].split()[:-1])
            and any(
                min(len(a), len(b)) >= 3 and (a.startswith(b) or b.startswith(a))
                for a in given
                for b in g
            )
        ]
        if len(prefix) == 1:
            return "given-prefix", prefix

        # 3. same surname, given name a known diminutive of the member's
        nick = [
            m
            for m in pool
            if (g := m["key"].split()[:-1])
            and {NICK.get(a, a) for a in given} & {NICK.get(b, b) for b in g}
        ]
        if len(nick) == 1:
            return "diminutive", nick
        return f"surname-only ({len(pool)})", pool

    def fuzzy(self, name: str, floor: float = 0.86) -> list[dict]:
        """Best whole-name match, only when it clearly beats the runner-up."""
        if len(name.split()) < 2:  # a lone given name identifies nobody
            return []
        pool: set[str] = set()
        for token in set(name.split()):
            if len(token) >= 4:
                pool |= self.buckets.get("".join(sorted(set(token[:4]))), set())
        scored = sorted(((_similar(name, key), key) for key in pool), reverse=True)
        if not scored or scored[0][0] < floor:
            return []
        if len(scored) > 1 and scored[1][0] > scored[0][0] - 0.04:
            return []  # two equally good — ambiguous, refuse
        best = scored[0][1]
        # A whole-name ratio clears the floor on given name and length alone
        # ("David Magri" against "David Martin"), so demand a corresponding
        # surname — Spanish double surnames put it mid-name — or containment.
        surname_ok = max(_similar(name.split()[-1], t) for t in best.split()) >= 0.75
        if not (surname_ok or set(best.split()) <= set(name.split())):
            return []
        return self.by_name[best]


def resolve_winner(name: str, roster: Roster, rulings: dict) -> tuple[str, str]:
    """(user_uid, class) for one normalised archive winner name; uid "" = unresolved.

    Ordered by measured precision. Every class below scored 100% against the
    bootstrap — the entries whose event we already hold, which know the answer and
    which no pass here ever sees. Classes that scored under that went to human
    review instead and come back through `rulings`, never through code.
    """
    ruled = rulings.get(name)
    if ruled:
        return ruled, "ruling"
    hits = roster.exact(name)
    if len(hits) == 1:
        return hits[0]["uid"], "exact"
    if hits:
        return "", f"ambiguous ({len(hits)} of that name)"
    cls, hits = roster.classes(name)
    if len(hits) == 1 and not cls.startswith("surname-only"):
        return hits[0]["uid"], cls
    hits = roster.fuzzy(name)
    if len(hits) == 1:
        return hits[0]["uid"], "whole-name fuzzy"
    return "", "no member"


def bootstrap_winners(verdicts: list[list], corpus: Corpus, by_id: dict) -> dict:
    """archive name -> user_uid, taken from the events we already hold.

    An entry that attaches to one of our tournaments hands over that tournament's
    winner, so the archive's spelling of the name is labelled for free. This is
    both the strongest resolver and the only honest scoring set for the others.
    A name our corpus maps to two different members is dropped, not guessed.
    """
    seen: dict[str, set[str]] = defaultdict(set)
    for entry_id, action, target, _, _ in verdicts:
        if action != "attach":
            continue
        row = corpus.by_uid.get(target)
        name = normalize(by_id[entry_id].get("player", "")) if entry_id in by_id else ""
        if row and row["winner_uid"] and name:
            seen[name].add(row["winner_uid"])
    return {name: next(iter(uids)) for name, uids in seen.items() if len(uids) == 1}


def validate_winners(bootstrap: dict, roster: Roster, rulings: dict) -> str:
    """Score the winner passes against the bootstrap, which they never see.

    Held to the same standard as the event tiers: a class that cannot be scored
    here does not get to auto-apply. Rulings are excluded — they are the answer
    key for names no pass reached, so scoring against them measures nothing.
    """
    score: Counter = Counter()
    for name, truth in bootstrap.items():
        uid, cls = resolve_winner(name, roster, {})
        if not uid:
            score["unresolved"] += 1
            continue
        score["correct" if uid == truth else "WRONG"] += 1
        score[f"  .. via {cls}"] += 1
    answered = score["correct"] + score["WRONG"]
    if not answered:
        return "no bootstrapped names — cannot validate"
    scored = {
        label.strip().removeprefix(".. via "): n
        for label, n in score.items()
        if label.startswith("  ")
    }
    detail = "  ".join(f"{cls} {n}" for cls, n in sorted(scored.items()))
    # A class the bootstrap never exercises is unmeasured, not proven — say so
    # rather than let its absence read as "no errors".
    blind = sorted({"exact", "member-subset", "given-prefix", "diminutive",
                    "whole-name fuzzy"} - set(scored))  # fmt: skip
    return (
        f"winner passes: {score['correct']}/{answered} = "
        f"{score['correct'] / answered:.1%} precise, recall "
        f"{answered / len(bootstrap):.1%} over {len(bootstrap)} labelled names\n"
        f"    scored: {detail}"
        + (
            f"\n    UNMEASURED (no labelled example): {', '.join(blind)}"
            if blind
            else ""
        )
    )


def load_rulings(path: Path | None) -> tuple[dict, dict]:
    """(events, winners) from the hand-authored rulings file.

    The packaged copy by default: a deployed box has the scripts beside the venv
    and no repo tree at all, so a path relative to this file resolves to nothing
    there — which is where this is actually run.
    """
    text = (
        path.read_text()
        if path
        else importlib.resources.files("backend.src.data")
        .joinpath("twda_rulings.tsv")
        .read_text()
    )
    events: dict[str, str] = {}
    winners: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, key, value = line.split("\t")
        if kind == "event":
            events[key] = value
        elif kind == "winner":
            winners[normalize(key)] = value
        else:
            raise ValueError(f"unknown ruling kind {kind!r}")
    return events, winners


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
        row = corpus.by_uid.get(uid) or corpus.by_archon.get(uid)
        if row:
            return "attach", row["uid"], "own link"
        return "review", "", "own link resolves to nothing"

    code = archon_code(entry)
    if code:
        row = corpus.by_code.get(code)
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


async def load_roster() -> Roster:
    async with db.get_connection() as conn:
        result = await conn.execute(ROSTER_QUERY, (ObjectType.USER,))
        return Roster(await result.fetchall())


def write_report(path: str, verdicts: list[list], corpus: Corpus, reasons: Counter):
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

        roster = await load_roster()
        print(f"roster: {len(roster.by_name)} distinct member names")
        event_rulings, winner_rulings = load_rulings(args.rulings)
        print(f"rulings: {len(event_rulings)} events, {len(winner_rulings)} winners")

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
        # After the collision pass, so a ruling is never undone by it.
        for verdict in verdicts:
            ruled = event_rulings.get(verdict[0])
            if ruled == "create":
                verdict[1], verdict[2], verdict[3] = "create", "", "ruling"
            elif ruled:
                verdict[1], verdict[2], verdict[3] = "attach", ruled, "ruling"
        reasons = Counter(f"{v[1]} — {v[3]}" for v in verdicts)

        by_id = {str(e.get("id", "")): e for e in entries}
        bootstrap = bootstrap_winners(verdicts, corpus, by_id)
        winners = {}
        for verdict in verdicts:
            if verdict[1] != "create":
                continue
            name = normalize(by_id[verdict[0]].get("player", ""))
            if name not in winners:
                uid = bootstrap.get(name)
                winners[name] = (
                    (uid, "bootstrap")
                    if uid
                    else resolve_winner(name, roster, winner_rulings)
                )
            verdict[2] = winners[name][0]

        print()
        for reason, count in reasons.most_common():
            print(f"  {count:6d}  {reason}")
        totals = Counter(v[1] for v in verdicts)
        print(
            f"\n  attach {totals['attach']}   create {totals['create']}   "
            f"review {totals['review']}"
        )
        created = [v for v in verdicts if v[1] == "create"]
        resolved = [v for v in created if v[2]]
        print(
            f"  reconstruction: {len(resolved)}/{len(created)} with a resolved "
            f"winner ({len(resolved) / max(len(created), 1):.1%}), "
            f"{len(created) - len(resolved)} held out"
        )
        by_class: Counter = Counter(cls for _, cls in winners.values())
        for cls, n in by_class.most_common():
            print(f"    {n:5d} names  {cls}")

        if args.validate:
            print(f"\n  {validate(entries, corpus)}")
            print(f"  {validate_winners(bootstrap, roster, winner_rulings)}")

        if args.emit_decisions:
            body = "\n".join(
                f"{entry_id}\t{action}"
                + (f":{target}" if action == "attach" and target else "")
                + (f"\t{target}" if action in ("create", "review") and target else "")
                for entry_id, action, target, _, _ in verdicts
            )
            Path(args.emit_decisions).write_text(
                "# GENERATED by backend/scripts/reconcile_twda.py — do not hand-edit.\n"
                "# Human decisions belong in backend/src/data/twda_rulings.tsv, which\n"
                "# is an input to this file.\n"
                "#\n"
                "# twda_id<TAB>action[<TAB>target]\n"
                "#   attach:<tournament_uid>  we already hold this event\n"
                "#   create<TAB><user_uid>    reconstruct it, won by that member\n"
                "#   create                   reconstruct nothing: winner unresolved\n"
                "#   review<TAB><uids>        UNDECIDED, with the candidates\n"
                "#\n"
                "# The consumer creates only `create` lines carrying a winner. Every\n"
                "# other shape is logged and skipped, never guessed at.\n" + body + "\n"
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
        "--rulings",
        metavar="PATH",
        type=Path,
        help="override the packaged hand-authored rulings file",
    )
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
