Doc-impact: the round-timer reminders paragraph in `wiki/discord.md`. `wiki/hazards.md` untouched unless the countdown formula changes.

The 15-minute, 5-minute and time-up posts per pending table, with per-table extra time, shipped in v0.3.0 (`compute_timer_reminders` in the bot's SSE listener). This line adds the start post, a 1-minute warning and an extension post.

**Start post** cannot ride the threshold tuple: when the start event arrives its delay is already at or below zero and the reschedule marks such tokens fired without posting. It needs edge handling on `timer.started_at` appearing with `elapsed_before_pause` at zero, gated on the synced flag so catch-up stays silent, and quiet on resume.

**1-minute warning** joins `_TIMER_THRESHOLDS`; the exact-list asserts in `bot/tests/test_timer_reminders.py` move with it.

**Extension post** fires on a diff of `table_extra_time` per table, into that table's chat, silent during catch-up. The rules require an extension to be clearly communicated.

**Two silence checks to run while in the code**, since the owner may have seen the existing reminders stay quiet at an event:
- `_timer_signature` ignores the table channel list, so voice channels created in a later snapshot than the clock start leave a schedule computed against zero sentinels that never rebuilds.
- Passed thresholds are suppressed on reconnect by design, so a bot restart or deploy after a threshold has passed means it never posts. Changing that is a wiki decision, not a side effect.
