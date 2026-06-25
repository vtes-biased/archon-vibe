---
name: aiohttp-timeout-escapes-clienterror
description: aiohttp ClientTimeout breaches raise asyncio.TimeoutError, NOT aiohttp.ClientError — `except aiohttp.ClientError` misses timeouts on every GitHub/external-proxy route
metadata:
  type: feedback
---

When reviewing any aiohttp-based external-proxy route (GitHub-issue filing in `routes/feedback.py`, TWDA importer in `twda.py`, Web Push sends), a total-timeout breach from `aiohttp.ClientTimeout(...)` raises `asyncio.TimeoutError` (== `TimeoutError` on 3.11+), which is **NOT** a subclass of `aiohttp.ClientError`.

So `except aiohttp.ClientError:` silently misses the timeout path → an upstream stall becomes an unhandled 500 instead of the intended friendly 502/503. The correct catch is `except (aiohttp.ClientError, asyncio.TimeoutError):`.

**Why:** Found during the #332 feedback-endpoint review — the friendly-502 transport branch only caught `aiohttp.ClientError`, so a 15s GitHub stall would have bubbled as a 500. Easy to miss because the timeout is configured *on the same ClientSession* that throws ClientError for everything else, so it reads as covered.

**How to apply:** On any review of an aiohttp call that sets a timeout and has a try/except meant to convert transport failures into a clean HTTP error, verify the except includes `asyncio.TimeoutError` (or bare `TimeoutError`), not just `aiohttp.ClientError`. Cross-check the other proxy sites listed above for the same gap.
