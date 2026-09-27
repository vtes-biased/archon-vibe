"""TWDA (Tournament Winning Deck Archive) GitHub integration — auto-creates PRs to
GiottoVerducci/TWD when a sanctioned tournament finishes with a winner decklist.
One App installed twice: on our fork, which holds the branch and the deck commit,
and on the archive, which is asked for nothing but permission to open the PR.
Config: TWDA_GITHUB_{CLIENT_ID,PRIVATE_KEY,INSTALLATION_ID,FORK_INSTALLATION_ID,FORK_OWNER}."""

import base64
import json
import logging
import os
import re
from datetime import UTC, datetime

import aiohttp
import msgspec
from archon_engine import PyEngine

from . import github_app, http_client
from .broadcast import broadcast_precomputed
from .card_data import cards_json_text
from .db import (
    TWDA_MIN_PLAYERS,
    get_decks_for_tournament,
    get_user_by_uid,
    get_user_by_vekn_id,
    save_tournament,
    tournament_transaction,
)
from .geonames import get_country, normalize_country
from .models import (
    AttributionKind,
    Tournament,
    TournamentFormat,
    TournamentState,
    TwdaOutcome,
    TwdaStatus,
)

logger = logging.getLogger(__name__)

TWDA_GITHUB_CLIENT_ID = os.environ.get("TWDA_GITHUB_CLIENT_ID", "")
TWDA_GITHUB_PRIVATE_KEY = os.environ.get("TWDA_GITHUB_PRIVATE_KEY", "")
TWDA_GITHUB_INSTALLATION_ID = os.environ.get("TWDA_GITHUB_INSTALLATION_ID", "")
TWDA_GITHUB_FORK_INSTALLATION_ID = os.environ.get(
    "TWDA_GITHUB_FORK_INSTALLATION_ID", ""
)
TWDA_GITHUB_FORK_OWNER = os.environ.get("TWDA_GITHUB_FORK_OWNER", "")
TWDA_TARGET_REPO = "GiottoVerducci/TWD"
TWDA_FORK_REPO = f"{TWDA_GITHUB_FORK_OWNER}/{TWDA_TARGET_REPO.split('/')[1]}"

_GH_API_VERSION = github_app.GH_API_VERSION


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

_engine = PyEngine()
_engine_cards_loaded = False


def frontend_url() -> str:
    return os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def is_configured() -> bool:
    return bool(
        TWDA_GITHUB_CLIENT_ID
        and TWDA_GITHUB_PRIVATE_KEY
        and TWDA_GITHUB_INSTALLATION_ID
        and TWDA_GITHUB_FORK_INSTALLATION_ID
        and TWDA_GITHUB_FORK_OWNER
    )


def keep_curated_header(archived: str, ours: str) -> str:
    kept = archived.splitlines()[:3]
    lines = ours.splitlines()
    if _ISO_DATE.match(kept[2]):
        kept[2] = lines[2]
    return "\n".join(kept + lines[3:]) + ("\n" if ours.endswith("\n") else "")


async def submit_twda_pr(
    event_key: str,
    deck_text: str,
    tournament_name: str,
) -> tuple[str, str]:
    """Create or update a PR on GiottoVerducci/TWD with the winner's deck.

    Returns `(pr_url, "")` on success, `("", "step[:http-status]")` on failure —
    the code the organizer's failure notice reads back.
    """
    try:
        private_key = github_app.load_private_key(TWDA_GITHUB_PRIVATE_KEY)
    except Exception:
        logger.exception("Failed to load the TWDA GitHub App private key")
        return "", "config"

    try:
        fork_token = await github_app.get_installation_token(
            TWDA_GITHUB_CLIENT_ID,
            private_key,
            TWDA_GITHUB_FORK_INSTALLATION_ID,
            {"contents": "write"},
        )
        archive_token = await github_app.get_installation_token(
            TWDA_GITHUB_CLIENT_ID,
            private_key,
            TWDA_GITHUB_INSTALLATION_ID,
            {"pull_requests": "write"},
        )
    except github_app.InstallationTokenError as exc:
        logger.exception("Failed to get TWDA GitHub installation tokens")
        return "", f"auth:{exc.status}"
    except Exception:
        logger.exception("Failed to get TWDA GitHub installation tokens")
        return "", "auth"

    branch = f"archon/{event_key}"
    file_path = f"decks/{event_key}.txt"
    head = f"{TWDA_GITHUB_FORK_OWNER}:{branch}"

    async def _req(method: str, path: str, token: str, **kwargs) -> tuple[int, str]:
        """Run a GitHub API request, returning (status, body_text). Reads the
        body inside the response context so it's available after it closes."""
        async with http_client.session().request(
            method,
            f"https://api.github.com{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _GH_API_VERSION,
            },
            timeout=aiohttp.ClientTimeout(total=30.0),
            **kwargs,
        ) as resp:
            return resp.status, await resp.text()

    try:
        # Fast-forward the fork's master to the archive's, so the branch is
        # cut from what the PR will actually be diffed against.
        sync_status, sync_text = await _req(
            "POST",
            f"/repos/{TWDA_FORK_REPO}/merge-upstream",
            fork_token,
            json={"branch": "master"},
        )
        if sync_status != 200:
            logger.error(f"Failed to sync TWD fork: {sync_status} {sync_text}")
            return "", f"fork_sync:{sync_status}"

        status, text = await _req(
            "GET", f"/repos/{TWDA_FORK_REPO}/git/refs/heads/master", fork_token
        )
        if status != 200:
            logger.error(f"Failed to get TWD fork master ref: {status}")
            return "", f"fork_ref:{status}"
        base_sha = json.loads(text)["object"]["sha"]

        file_status, file_text = await _req(
            "GET",
            f"/repos/{TWDA_FORK_REPO}/contents/{file_path}",
            fork_token,
            params={"ref": base_sha},
        )
        # A GET failure that is not the file's absence would drop the sha and
        # turn the update into a 422 the organizer would read as a refusal.
        if file_status not in (200, 404):
            logger.error(f"Failed to read deck file: {file_status} {file_text}")
            return "", f"commit:{file_status}"

        verb = "Update" if file_status == 200 else "Add"
        if file_status == 200:
            archived = base64.b64decode(json.loads(file_text)["content"]).decode()
            deck_text = keep_curated_header(archived, deck_text)
            if deck_text == archived:
                return (
                    f"https://github.com/{TWDA_TARGET_REPO}/blob/master/{file_path}",
                    "",
                )

        ref_status, _ = await _req(
            "GET",
            f"/repos/{TWDA_FORK_REPO}/git/refs/heads/{branch}",
            fork_token,
        )
        if ref_status == 200:
            reset_status, reset_text = await _req(
                "PATCH",
                f"/repos/{TWDA_FORK_REPO}/git/refs/heads/{branch}",
                fork_token,
                json={"sha": base_sha, "force": True},
            )
            if reset_status != 200:
                logger.error(f"Failed to reset branch: {reset_status} {reset_text}")
                return "", f"branch:{reset_status}"
        else:
            create_status, create_text = await _req(
                "POST",
                f"/repos/{TWDA_FORK_REPO}/git/refs",
                fork_token,
                json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            )
            if create_status not in (200, 201):
                logger.error(f"Failed to create branch: {create_status} {create_text}")
                return "", f"branch:{create_status}"

        content_b64 = base64.b64encode(deck_text.encode()).decode()
        file_data: dict = {
            "message": f"{verb} TWD: {tournament_name}",
            "content": content_b64,
            "branch": branch,
        }
        if file_status == 200:
            file_data["sha"] = json.loads(file_text)["sha"]

        put_status, put_text = await _req(
            "PUT",
            f"/repos/{TWDA_FORK_REPO}/contents/{file_path}",
            fork_token,
            json=file_data,
        )
        if put_status not in (200, 201):
            logger.error(f"Failed to commit deck file: {put_status} {put_text}")
            return "", f"commit:{put_status}"

        pr_status, pr_text = await _req(
            "GET",
            f"/repos/{TWDA_TARGET_REPO}/pulls",
            archive_token,
            params={"head": head, "state": "open"},
        )
        if pr_status == 200:
            prs = json.loads(pr_text)
            if prs:
                pr_url = prs[0]["html_url"]
                logger.info(f"TWDA PR already open, updated via branch push: {pr_url}")
                return pr_url, ""

        pr_create_status, pr_create_text = await _req(
            "POST",
            f"/repos/{TWDA_TARGET_REPO}/pulls",
            archive_token,
            json={
                "title": f"{verb} TWD: {tournament_name}",
                "body": (
                    "Automatically submitted by Archon tournament manager.\n\n"
                    f"{frontend_url()}/t/{event_key}"
                ),
                "head": head,
                "base": "master",
                # GitHub defaults this to true and refuses it with 422 for this App.
                "maintainer_can_modify": False,
            },
        )
        if pr_create_status == 201:
            pr_url = json.loads(pr_create_text)["html_url"]
            logger.info(f"TWDA PR created: {pr_url}")
            return pr_url, ""

        logger.error(f"Failed to create TWDA PR: {pr_create_status} {pr_create_text}")
        return "", f"pull_request:{pr_create_status}"

    except Exception:
        logger.exception("TWDA PR submission failed")
        return "", "internal"


async def winner_deck_twda(tournament: Tournament) -> str | None:
    """TWDA-formatted winner decklist (event header + deck), or None if the
    winner has no stored deck."""
    if not tournament.winner:
        return None

    decks = await get_decks_for_tournament(tournament.uid)
    finals_round = len(tournament.rounds) if tournament.multideck else None
    winner_deck = next(
        (
            d
            for d in decks
            if d.user_uid == tournament.winner and d.round == finals_round
        ),
        None,
    )
    if not winner_deck:
        return None

    player_user = await get_user_by_uid(tournament.winner)
    player_name = player_user.name if player_user else "Unknown"

    credit = winner_deck.attribution
    if credit.kind == AttributionKind.MEMBER:
        designer = await get_user_by_vekn_id(credit.vekn_id)
        designer_credit = designer.name if designer else ""
    elif credit.kind == AttributionKind.ARCHIVE:
        designer_credit = credit.name
    else:
        designer_credit = ""

    deck_json = json.dumps(
        {
            "name": winner_deck.name,
            "author": designer_credit,
            "comments": winner_deck.comments,
            "cards": winner_deck.cards,
        }
    )

    def us_date(d: datetime) -> str:
        suffix = (
            "th"
            if 11 <= d.day % 100 <= 13
            else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
        )
        return f"{d.strftime('%B')} {d.day}{suffix} {d.year}"

    start = tournament.start or tournament.modified
    tournament_date = us_date(start)
    if tournament.finish and tournament.finish.date() != start.date():
        tournament_date += f" -- {us_date(tournament.finish)}"
    rounds_count = len(tournament.rounds)
    tournament_format = f"{rounds_count}R" + (
        "+F" if tournament.finals else " (no final)"
    )

    standing = next(
        (s for s in tournament.standings if s.user_uid == tournament.winner), None
    )
    winner_score = ""
    if standing:
        winner_score = f"{int(standing.gw)}GW{standing.vp:g}"
        finals_seat = next(
            (
                s
                for s in (tournament.finals.seating if tournament.finals else [])
                if s.player_uid == tournament.winner
            ),
            None,
        )
        if finals_seat:
            winner_score += f" + {finals_seat.result.vp:g}vp in final"

    # The archive keeps this line forever, so it must be the citable form. Two
    # TWDA entries already point at legacy-archon uids that resolve to nothing.
    handle = (
        f"/t/{tournament.event_code}"
        if tournament.event_code
        else f"/tournaments/{tournament.uid}"
    )

    named = get_country(normalize_country(tournament.country or "") or "")

    _load_engine_cards()
    return _engine.export_twda(
        deck_json,
        tournament.name,
        tournament_date,
        "Online"
        if tournament.online
        else ", ".join(
            p
            for p in (tournament.city, named["name"] if named else tournament.country)
            if p
        ),
        tournament_format,
        f"{frontend_url()}{handle}",
        _engine.attested_player_count(msgspec.json.encode(tournament).decode()),
        player_name,
        winner_score,
    )


async def _record_twda_status(
    uid: str, outcome: TwdaOutcome, reason: str = "", pr_url: str = ""
) -> None:
    """Locked fetch-modify-save so only twda_status lands on the CURRENT row,
    never clobbering concurrent edits; an unchanged outcome skips the write."""
    async with tournament_transaction(uid) as (fresh, tx_conn):
        if not fresh:
            return
        prev = fresh.twda_status
        if prev and (prev.outcome, prev.reason, prev.pr_url) == (
            outcome,
            reason,
            pr_url,
        ):
            return
        fresh.twda_status = TwdaStatus(
            outcome=outcome, reason=reason, pr_url=pr_url, at=datetime.now(UTC)
        )
        fresh.modified = datetime.now(UTC)
        bd = await save_tournament(fresh, conn=tx_conn)
    broadcast_precomputed(bd)


async def maybe_submit_twda(tournament: Tournament) -> None:
    """Self-contains its errors, recording outcome/reason on the tournament
    either way. `ranking_eligibility` (the ranked-badge predicate) is distinct
    from `rank` (the Basic/NC/CC championship axis) — don't conflate them."""
    if tournament.state != TournamentState.FINISHED:
        return
    t_json = msgspec.json.encode(tournament).decode()
    if not tournament.winner:
        outcome = (TwdaOutcome.SKIPPED, "no_winner", "")
    elif tournament.format == TournamentFormat.Limited:
        # Limited events are rated (own category) but draft/sealed decks
        # don't belong in a constructed-deck archive.
        outcome = (TwdaOutcome.SKIPPED, "limited", "")
    elif tournament.format == TournamentFormat.Storyline:
        outcome = (TwdaOutcome.SKIPPED, "storyline", "")
    elif tournament.external_ids.get("twda"):
        outcome = (TwdaOutcome.SKIPPED, "reconstructed", "")
    elif not tournament.rounds:
        outcome = (TwdaOutcome.SKIPPED, "no_rounds", "")
    elif _engine.attested_player_count(t_json) < TWDA_MIN_PLAYERS:
        outcome = (TwdaOutcome.SKIPPED, "too_few_players", "")
    elif _engine.ranking_eligibility(t_json) != "eligible":
        outcome = (TwdaOutcome.SKIPPED, "unranked", "")
    elif not tournament.event_code:
        outcome = (TwdaOutcome.SKIPPED, "no_event_code", "")
    elif not tournament.online and not tournament.country:
        outcome = (TwdaOutcome.SKIPPED, "no_place", "")
    elif not is_configured():
        outcome = (TwdaOutcome.SKIPPED, "not_configured", "")
    else:
        try:
            deck_text = await winner_deck_twda(tournament)
            if not deck_text:
                outcome = (TwdaOutcome.SKIPPED, "no_deck", "")
            else:
                pr_url, reason = await submit_twda_pr(
                    tournament.event_code, deck_text, tournament.name
                )
                if pr_url:
                    outcome = (TwdaOutcome.SUBMITTED, "", pr_url)
                else:
                    outcome = (TwdaOutcome.FAILED, reason, "")
        except Exception:
            logger.exception("Failed to submit TWDA PR")
            outcome = (TwdaOutcome.FAILED, "deck", "")

    try:
        await _record_twda_status(tournament.uid, *outcome)
    except Exception:
        logger.exception("Failed to record TWDA status")


def _load_engine_cards() -> None:
    """Hand cards.json to the engine, which parses and holds it."""
    global _engine_cards_loaded
    if _engine_cards_loaded:
        return
    text = cards_json_text()
    if text is None:
        raise RuntimeError("Cards data not available. Run: just cards")
    _engine.load_cards(text)
    _engine_cards_loaded = True
