"""Pure message rendering for the Discord SSE listener.

Data -> string. No I/O, no bot/store handles, no module state: the listener owns
*when* and *where* to post (and the state-transition detection that decides it);
this module owns *how* each announcement reads. Keeping the text here makes the
wording reviewable in one place and unit-testable without a live stream.
"""

_SANCTION_LEVEL_LABELS = {
    "caution": "Caution",
    "warning": "Warning",
    "standings_adjustment": "Standings Adjustment",
    "disqualification": "Disqualification",
}

_SANCTION_LEVEL_EMOJI = {
    "caution": "\u26a0\ufe0f",  # ⚠️
    "warning": "\U0001f7e0",  # 🟠
    "standings_adjustment": "\U0001f7e3",  # 🟣
    "disqualification": "\U0001f534",  # 🔴
}


def player_display(
    puid: str,
    players: list,
    *,
    discord_id_map: dict | None = None,
    user_names: dict | None = None,
    mention: bool = False,
) -> str:
    """Resolve a player UID to a display string.

    Priority: Discord ``@mention`` (when linked and ``mention``) → per-tournament
    Discord nickname (``display_name``) → cached user nickname → user name → uid
    prefix. ``mention`` is set only where a ping is wanted (seating/finals — "go
    to your table"); standings/warnings leave it off so the per-round post reads
    as plain names and doesn't notify every listed player.

    ``user_names`` maps uid → ``{"name", "nickname"}`` (seeded from the scoped
    stream's participant identities) and is what lets non-Discord players —
    webapp/VEKN-added — resolve to a real name instead of a raw uid.
    """
    if mention and discord_id_map and puid in discord_id_map:
        return f"<@{discord_id_map[puid]}>"
    p = next((p for p in players if p.get("user_uid") == puid), None)
    if p and p.get("display_name"):
        return p["display_name"]
    ident = (user_names or {}).get(puid)
    if ident:
        return ident.get("nickname") or ident.get("name") or puid[:8]
    return puid[:8]


def format_standings(
    standings: list,
    standings_mode: str,
    players: list,
    *,
    user_names: dict | None = None,
) -> str:
    """Format standings respecting the tournament's standings_mode setting.

    - Private: no standings shown
    - Cutoff: only the 5th-place score threshold (no names)
    - Top 10: top 10 players with scores
    - Public: all players with scores
    """
    if standings_mode == "Private" or not standings:
        return ""

    if standings_mode == "Cutoff":
        if len(standings) < 5:
            return "\n**Top 5 cutoff:** Not enough players yet."
        s = standings[4]
        gw = s.get("gw", 0)
        vp = s.get("vp", 0)
        return f"\n**Top 5 cutoff score:** {gw}GW {vp}VP"

    limit = {"Top 10": 10, "Public": len(standings)}.get(standings_mode, 0)
    if limit == 0:
        return ""

    label = "Top 10" if standings_mode == "Top 10" else "Standings"
    lines = [f"\n**{label}:**"]
    for i, s in enumerate(standings[:limit]):
        display = player_display(s.get("user_uid", ""), players, user_names=user_names)
        gw = s.get("gw", 0)
        vp = s.get("vp", 0)
        tp = s.get("tp", 0)
        lines.append(f"{i + 1}. {display} — {gw}GW {vp}VP {tp}TP")
    return "\n".join(lines)


def format_round_seating(
    round_count: int,
    tables_player_uids: list[list[str]],
    players: list,
    *,
    discord_id_map: dict | None = None,
    user_names: dict | None = None,
) -> str:
    """Render the new-round seating announcement (prey → predator per table).

    Mentions linked players (pings them to join their table); falls back to
    nickname/name for everyone else.
    """
    lines = [f"**Round {round_count} — Seating**\n"]
    for ti, player_uids in enumerate(tables_player_uids):
        seat_names = [
            player_display(
                uid,
                players,
                discord_id_map=discord_id_map,
                user_names=user_names,
                mention=True,
            )
            for uid in player_uids
        ]
        lines.append(f"**Table {ti + 1}**: {' → '.join(seat_names)}")
    lines.append(
        "\nJoin your table's voice channel and use `/report` when the round ends."
    )
    return "\n".join(lines)


def format_finals(
    name: str,
    seating: list,
    seed_order: list,
    players: list,
    *,
    discord_id_map: dict | None = None,
    user_names: dict | None = None,
) -> str:
    """Render the finals seating announcement (prey → predator, with seeds).

    Mentions linked finalists (pings them to join the finals voice channel);
    falls back to nickname/name otherwise.
    """
    lines = [f"**Finals — {name}**\n", "Seating order (prey → predator):"]
    for i, s in enumerate(seating):
        uid = s.get("player_uid", "")
        display = player_display(
            uid,
            players,
            discord_id_map=discord_id_map,
            user_names=user_names,
            mention=True,
        )
        seed = seed_order.index(uid) + 1 if uid in seed_order else "?"
        lines.append(f"  {i + 1}. {display} (seed #{seed})")
    lines.append("\nJoin the Finals voice channel. Good luck!")
    return "\n".join(lines)


def _fmt_vp(vp) -> str:
    """VPs are whole in normal play but the model allows halves (split finals);
    render '3' not '3.0', and '2.5' as-is."""
    f = float(vp)
    return str(int(f)) if f == int(f) else str(f)


def format_table_result(
    table_index: int,
    table: dict,
    players: list,
    *,
    is_finals: bool = False,
    user_names: dict | None = None,
) -> str:
    """Render a table's current reported VPs for its voice channel.

    Posted on every score change so everyone seated sees what was entered —
    open reporting deters mis-reporting. No pings (players are already here), so
    names resolve without a mention (nickname/name fallback, not @handle).
    The footer reflects the engine-computed table ``state``.
    """
    label = "Finals" if is_finals else f"Table {table_index + 1}"
    lines = [f"**Results reported — {label}**"]
    for s in table.get("seating", []):
        name = player_display(s.get("player_uid", ""), players, user_names=user_names)
        vp = (s.get("result") or {}).get("vp", 0)
        judged = " _(entered by judge)_" if s.get("judge_uid") else ""
        lines.append(f"{name}: {_fmt_vp(vp)} VP{judged}")

    if table.get("override"):
        lines.append("\n_Result finalized by a judge._")
    else:
        state = table.get("state", "")
        if state == "Finished":
            lines.append("\n_Table complete — VP total checks out._")
        elif state == "Invalid":
            lines.append("\n⚠️ _Reported VPs don't add up — check with a judge._")
        else:
            lines.append("\n_Awaiting the rest of the table's results._")
    return "\n".join(lines)


def format_sanction(
    level: str,
    category: str,
    subcategory: str,
    description: str,
    round_number: int | None,
    player_mention: str,
) -> tuple[str, str]:
    """Render the (judges, player) sanction announcement pair.

    ``category`` is expected already space-normalized; ``subcategory`` raw.
    """
    level_label = _SANCTION_LEVEL_LABELS.get(level, level)
    level_emoji = _SANCTION_LEVEL_EMOJI.get(level, "")
    round_info = f" (Round {round_number + 1})" if round_number is not None else ""
    subcategory_info = f" — {subcategory.replace('_', ' ')}" if subcategory else ""

    judges_msg = (
        f"{level_emoji} **{level_label}** issued to {player_mention}{round_info}\n"
        f"Category: {category}{subcategory_info}\n"
        f"_{description}_"
    )
    player_msg = (
        f"{level_emoji} {player_mention} received a **{level_label}**{round_info}\n"
        f"_{description}_"
    )
    return judges_msg, player_msg
