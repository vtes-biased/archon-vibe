from .command_mentions import command_mention

_SANCTION_LEVEL_LABELS = {
    "caution": "Caution",
    "warning": "Warning",
    "standings_adjustment": "Standings Adjustment",
    "disqualification": "Disqualification",
}

_SANCTION_LEVEL_EMOJI = {
    "caution": "\u26a0\ufe0f",
    "warning": "\U0001f7e0",
    "standings_adjustment": "\U0001f7e3",
    "disqualification": "\U0001f534",
}


def player_display(
    puid: str,
    players: list,
    *,
    discord_id_map: dict | None = None,
    user_names: dict | None = None,
    mention: bool = False,
) -> str:
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
        f"\nJoin your table's voice channel and use {command_mention('report')} when the round ends."
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


def format_timer_reminder(table_label: str, threshold_seconds: int) -> str:
    if threshold_seconds <= 0:
        return (
            f"⏰ **Time!** {table_label} — the round clock has run out. "
            f"Finish the current turn, then report results with {command_mention('report')}."
        )
    minutes = threshold_seconds // 60
    unit = "minute" if minutes == 1 else "minutes"
    return f"⏳ **{minutes} {unit} remaining** at {table_label}."


def format_announcement(text: str) -> str:
    return f"📣 **Announcement**\n{text}"


def format_sanction(
    level: str,
    category: str,
    subcategory: str,
    description: str,
    round_number: int | None,
    player_mention: str,
) -> tuple[str, str]:
    """``category`` is expected already space-normalized; ``subcategory`` raw."""
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
