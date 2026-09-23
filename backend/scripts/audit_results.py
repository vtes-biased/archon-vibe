"""List where vekn.net, the TWDA and our corpus disagree on an event's results.

Every finished event more than one source describes is compared on winner,
finalists, prelim GW/VP, round count and field size, and each disagreement is
printed under its class:

    archon/vekn   an event with rounds here against the sheet it was pushed as
    vekn/twda     a vekn.net sheet, as the importer reads it today, against its
                  archive entry — so what the import rules already correct is gone
    archon/twda   an event with rounds here against its archive entry
    twda/vekn     an archive reconstruction whose winner also won a vekn.net
                  event within a day: one event held twice. Only a single twin
                  on the same day and of the same field size is emitted as a
                  merge; the rest are for a human
    vekn          a prelim GW above the round count, as the importer reads the
                  sheet today — what the next sync will write
    ours          the same, on the row as it stands

Read-only — it writes nowhere. It scans vekn.net unless `--vekn-cache` names a
JSON Lines file of `fetch_all_events` output, and needs the VEKN credentials the
service env carries:

    sudo -u archon bash -c 'set -a; . /etc/archon/archon-backend.env; set +a; \\
      /opt/archon/backend/.venv/bin/python \\
      /opt/archon/backend/scripts/audit_results.py'
"""

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import unicodedata
from collections import Counter
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path

try:
    _have_backend = importlib.util.find_spec("backend.src") is not None
except ModuleNotFoundError:
    _have_backend = False
if not _have_backend:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import msgspec  # noqa: E402

from backend.src import db, http_client  # noqa: E402
from backend.src.models import ObjectType  # noqa: E402
from backend.src.twda_import import TWDA_URL, extract_vekn_event_id  # noqa: E402
from backend.src.vekn_api import VEKNAPIClient  # noqa: E402
from backend.src.vekn_tournament_sync import (  # noqa: E402
    _TWDA_SCORE_RE,
    _map_vekn_to_tournament,
    _parse_rounds,
    _TwdaScore,
)

OURS_QUERY = """
    SELECT uid, "full"->>'name', left("full"->>'start', 10), "full"->'external_ids',
           coalesce("full"->>'winner', ''), coalesce(("full"->>'max_rounds')::int, 0),
           jsonb_array_length(coalesce("full"->'rounds', '[]'::jsonb)),
           coalesce("full"->'standings', '[]'::jsonb),
           coalesce("full"->'finals'->'seating', '[]'::jsonb),
           coalesce(("full"->>'reported_player_count')::int, 0)
    FROM objects
    WHERE type = %s AND deleted_at IS NULL AND "full"->>'state' = 'Finished'
"""
VEKN_UIDS_QUERY = """
    SELECT "full"->'external_ids'->>'vekn', uid FROM objects
    WHERE type = %s AND deleted_at IS NULL AND "full"->'external_ids' ? 'vekn'
"""
USERS_QUERY = """
    SELECT uid, coalesce("full"->>'vekn_id', ''), coalesce("full"->>'name', '')
    FROM objects WHERE type = %s
"""
_KEPT = ("veknid", "pos", "dq", "wd", "gw", "vp", "vpf", "tp", "tie")
_EVENT_KEPT = ("event_id", "event_startdate", "rounds")


_UNDECOMPOSED = str.maketrans("łŁøØđĐßæÆ", "lLoOdDsaA")


def _tokens(name: str) -> set[str]:
    folded = unicodedata.normalize("NFKD", name.translate(_UNDECOMPOSED))
    ascii_name = folded.encode("ascii", "ignore")
    return set(ascii_name.decode().lower().replace("-", " ").replace('"', " ").split())


def _same_person(a: str, b: str) -> bool:
    """Our names are routinely fuller than the archive's, so containment agrees."""
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and (ta <= tb or tb <= ta or len(ta & tb) >= 2)


def _placed(row: dict) -> int | None:
    pos = str(row.get("pos") or "")
    flagged = "1" in (str(row.get("dq") or "0"), str(row.get("wd") or "0"))
    return int(pos) if pos.isdigit() and not flagged else None


def _score(entry: dict) -> tuple[int | None, float | None, float | None]:
    m = _TWDA_SCORE_RE.fullmatch(entry.get("score", ""))
    if not m:
        return None, None, None
    return (
        int(m.group(1)) if m.group(1) else None,
        float(m.group(2)) if m.group(2) else None,
        float(m.group(3)) if m.group(3) else None,
    )


def _sheet(event: dict) -> list[dict]:
    """A sheet's rows as the importer reads them, built per event: held as dicts
    for the whole scan they are most of this script's memory."""
    return [dict(zip((*_KEPT, "name"), row, strict=True)) for row in event["rows"]]


async def _vekn_events(cache: str | None) -> dict[str, dict]:
    """event id -> the event, trimmed to what the comparison and the importer read."""

    def trim(event: dict) -> dict:
        return {
            **{k: event.get(k) for k in _EVENT_KEPT},
            "rows": tuple(
                tuple(row.get(k) for k in _KEPT)
                + (f"{row.get('firstname', '')} {row.get('lastname', '')}",)
                for row in event.get("players") or []
            ),
        }

    events: dict[str, dict] = {}
    if cache:
        with open(cache) as f:
            for line in f:
                event = json.loads(line)
                events[str(event["event_id"])] = trim(event)
        return events
    async for event in VEKNAPIClient().fetch_all_events():
        events[str(event["event_id"])] = trim(event)
    return events


class _Entry(msgspec.Struct):
    id: str
    player: str = ""
    players_count: int = 0
    tournament_format: str = ""
    score: str = ""
    event_link: str = ""


async def _twda() -> dict[str, dict]:
    """The archive without its decklists, which are most of its 12 MB."""
    async with http_client.session().get(TWDA_URL) as resp:
        resp.raise_for_status()
        entries = msgspec.json.decode(await resp.read(), type=list[_Entry])
    return {entry.id: msgspec.structs.asdict(entry) for entry in entries}


async def _ours(conn) -> AsyncIterator[tuple]:
    async with conn.transaction():
        async with conn.cursor(name="audit_results") as cur:
            await cur.execute(OURS_QUERY, (ObjectType.TOURNAMENT,))
            while rows := await cur.fetchmany(200):
                for row in rows:
                    yield row


async def run(args: argparse.Namespace) -> int:
    db.DB_URL = args.dsn
    await db.init_db()
    findings: list[tuple[str, str, str, str]] = []

    def report(cls: str, field: str, ref: str, detail: str) -> None:
        findings.append((cls, field, ref, detail))

    try:
        async with db.get_connection() as conn:
            users = {
                uid: (vekn_id, name)
                for uid, vekn_id, name in await (
                    await conn.execute(USERS_QUERY, (ObjectType.USER,))
                ).fetchall()
            }
            uid_by_event = dict(
                await (
                    await conn.execute(VEKN_UIDS_QUERY, (ObjectType.TOURNAMENT,))
                ).fetchall()
            )
        uid_by_vekn_id = {v: uid for uid, (v, _) in users.items() if v}
        events = await _vekn_events(args.vekn_cache)
        entries = await _twda()
        entry_by_vekn = {
            vekn_id: entry
            for entry in entries.values()
            if (vekn_id := extract_vekn_event_id(entry))
        }
        duplicates: list[str] = []
        wins_by_day: dict[tuple[str, str], list[str]] = {}
        for event_id, event in events.items():
            for row in _sheet(event):
                if _placed(row) == 1:
                    key = (event.get("event_startdate") or "", str(row["veknid"]))
                    wins_by_day.setdefault(key, []).append(event_id)

        finished = 0
        async with db.get_connection() as conn:
            async for (
                uid,
                name,
                start,
                ext,
                winner,
                max_rounds,
                n_rounds,
                standings,
                seats,
                reported,
            ) in _ours(conn):
                finished += 1
                vekn_id = ext.get("vekn")
                event = events.get(vekn_id or "")
                sheet = _sheet(event) if event else []
                entry = entries.get(ext.get("twda_entry") or ext.get("twda") or "") or (
                    entry_by_vekn.get(vekn_id or "")
                )
                ref = f"{vekn_id or '-'}/{uid}"
                final_vp = {s["player_uid"]: s["result"].get("vp", 0) for s in seats}
                prelim = {s["user_uid"]: s for s in standings}
                played = sum(
                    1
                    for s in standings
                    if s.get("finalist") or any(s.get(k) for k in ("gw", "vp", "tp"))
                )

                for s in standings:
                    if max_rounds and s.get("gw", 0) > max_rounds:
                        report(
                            "ours",
                            "prelim-gw",
                            ref,
                            f"{s['gw']:g} GW over {max_rounds}R",
                        )

                if n_rounds and sheet:
                    ours_winner = users.get(winner, ("", ""))[0]
                    theirs_winner = {str(r["veknid"]) for r in sheet if _placed(r) == 1}
                    if theirs_winner and {ours_winner} != theirs_winner:
                        report(
                            "archon/vekn",
                            "winner",
                            ref,
                            f"{ours_winner} vs {theirs_winner}",
                        )
                    ours_five = {
                        users.get(u, ("", ""))[0]
                        for u, s in prelim.items()
                        if s.get("finalist")
                    }
                    theirs_five = {
                        str(r["veknid"]) for r in sheet if (_placed(r) or 99) <= 5
                    }
                    if theirs_five and ours_five != theirs_five:
                        report(
                            "archon/vekn",
                            "finalists",
                            ref,
                            f"ours only {sorted(ours_five - theirs_five)}, "
                            f"theirs only {sorted(theirs_five - ours_five)}",
                        )
                    if (their_rounds := _parse_rounds(event.get("rounds"))) != n_rounds:
                        report(
                            "archon/vekn",
                            "rounds",
                            ref,
                            f"{n_rounds} vs {their_rounds}",
                        )
                    if len(sheet) != played:
                        report("archon/vekn", "field", ref, f"{played} vs {len(sheet)}")
                    folded = other = 0
                    for row in sheet:
                        u = uid_by_vekn_id.get(str(row["veknid"]))
                        if u not in prelim:
                            continue
                        ogw, ovp = prelim[u].get("gw", 0), prelim[u].get("vp", 0)
                        tgw, tvp = float(row["gw"] or 0), float(row["vp"] or 0)
                        if (ogw, ovp) == (tgw, tvp):
                            continue
                        won = 1 if u == winner else 0
                        if tgw in (ogw, ogw + won) and tvp == ovp + final_vp.get(u, 0):
                            folded += 1
                        else:
                            other += 1
                    if folded:
                        report(
                            "archon/vekn", "holds-final", ref, f"{folded} finalist(s)"
                        )
                    if other:
                        report("archon/vekn", "prelim", ref, f"{other} player(s)")

                mapped = None
                if sheet and not n_rounds:
                    twda = msgspec.convert(entry, _TwdaScore) if entry else None
                    mapped = _map_vekn_to_tournament(
                        {**event, "players": sheet}, uid_by_vekn_id, twda=twda
                    )
                    for s in mapped.standings if mapped else []:
                        if mapped.max_rounds and s.gw > mapped.max_rounds:
                            report(
                                "vekn",
                                "prelim-gw",
                                ref,
                                f"{s.gw:g} GW over {mapped.max_rounds}R once imported",
                            )

                if entry and sheet and not n_rounds:
                    sheet_winner = next((r for r in sheet if _placed(r) == 1), None)
                    if sheet_winner and not _same_person(
                        sheet_winner["name"], entry["player"]
                    ):
                        report(
                            "vekn/twda",
                            "winner",
                            ref,
                            f"{sheet_winner['name']!r} vs {entry['player']!r}",
                        )
                    twda_rounds = _parse_rounds(entry.get("tournament_format", ""))
                    their_rounds = _parse_rounds(event.get("rounds"))
                    if twda_rounds and their_rounds and twda_rounds != their_rounds:
                        report(
                            "vekn/twda",
                            "rounds",
                            ref,
                            f"{their_rounds} vs {twda_rounds}",
                        )
                    count = entry.get("players_count") or 0
                    if count and count != len(sheet):
                        report("vekn/twda", "field", ref, f"{len(sheet)} vs {count}")
                    x, y, z = _score(entry)
                    if mapped and mapped.winner and z is not None:
                        w = next(
                            s for s in mapped.standings if s.user_uid == mapped.winner
                        )
                        seats = mapped.finals.seating if mapped.finals else []
                        got_z = next(
                            (
                                s.result.vp
                                for s in seats
                                if s.player_uid == mapped.winner
                            ),
                            0.0,
                        )
                        if (x is not None and (w.gw, w.vp) != (x, y)) or got_z != z:
                            report(
                                "vekn/twda",
                                "winner-score",
                                ref,
                                f"{w.gw:g}GW{w.vp:g}+{got_z:g} vs {entry['score']}",
                            )

                if entry and n_rounds:
                    ours_name = users.get(winner, ("", ""))[1]
                    if not _same_person(ours_name, entry["player"]):
                        report(
                            "archon/twda",
                            "winner",
                            ref,
                            f"{ours_name!r} vs {entry['player']!r}",
                        )
                    twda_rounds = _parse_rounds(entry.get("tournament_format", ""))
                    if twda_rounds and twda_rounds != n_rounds:
                        report(
                            "archon/twda", "rounds", ref, f"{n_rounds} vs {twda_rounds}"
                        )
                    count = entry.get("players_count") or 0
                    if count and count != played:
                        report("archon/twda", "field", ref, f"{played} vs {count}")
                    x, y, z = _score(entry)
                    if z is not None and winner in prelim:
                        got = (prelim[winner].get("gw", 0), prelim[winner].get("vp", 0))
                        if (x is not None and got != (x, y)) or final_vp.get(
                            winner, 0
                        ) != z:
                            report(
                                "archon/twda",
                                "winner-score",
                                ref,
                                f"{got[0]:g}GW{got[1]:g}+{final_vp.get(winner, 0):g} "
                                f"vs {entry['score']}",
                            )

                if ext.get("twda") and not vekn_id and start:
                    winner_vekn = users.get(winner, ("", ""))[0]
                    day = date.fromisoformat(start)
                    twins = [
                        event_id
                        for k in (-1, 0, 1)
                        for event_id in wins_by_day.get(
                            ((day + timedelta(k)).isoformat(), winner_vekn), []
                        )
                    ]
                    if winner_vekn and twins:
                        report(
                            "twda/vekn", "duplicate", ref, f"{name!r} also vekn {twins}"
                        )
                        twin = events[twins[0]]
                        if (
                            len(twins) == 1
                            and twins[0] in uid_by_event
                            and twin.get("event_startdate") == start
                            and reported in (0, len(twin["rows"]))
                        ):
                            duplicates.append(
                                f"{uid_by_event[twins[0]]}\t{uid}\t{twins[0]}"
                            )

        counts = Counter((cls, field) for cls, field, _, _ in findings)
        print(
            f"{finished} finished events, {len(events)} vekn.net, {len(entries)} TWDA"
        )
        for (cls, field), n in sorted(counts.items()):
            print(f"  {cls:<12} {field:<15} {n:>6}")
        print()
        for cls, field, ref, detail in sorted(findings):
            print(f"{cls}\t{field}\t{ref}\t{detail}")
        if args.emit_duplicates:
            with open(args.emit_duplicates, "w") as f:
                f.write(
                    "# keep_uid<TAB>drop_uid<TAB>vekn_id — the vekn.net copy survives "
                    "and takes the archive key; review before dedup_tournaments.py "
                    "--apply\n"
                )
                f.writelines(line + "\n" for line in duplicates)
            print(f"\n{len(duplicates)} duplicate pair(s) → {args.emit_duplicates}")
        return 0
    finally:
        await http_client.close()
        await db.close_db()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dsn", default=os.getenv("DATABASE_URL"), help="target DSN")
    p.add_argument(
        "--vekn-cache", help="JSON Lines of vekn.net events, instead of a scan"
    )
    p.add_argument(
        "--emit-duplicates",
        metavar="PATH",
        help="write each twda/vekn pair as a dedup_tournaments.py decision",
    )
    args = p.parse_args()
    if not args.dsn:
        p.error("--dsn or DATABASE_URL is required")
    return args


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
