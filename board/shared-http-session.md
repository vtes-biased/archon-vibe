Doc-impact: `wiki/architecture.md` (the shared outbound transport, beside the
existing push fan-out paragraph), `wiki/hazards.md` (why link-preview is exempt).

# Shared outbound HTTP session

## The sites

Hot path — these run continuously during a tournament morning:

| Site | Function | Fires on |
|---|---|---|
| `routes/auth/discord.py:123` | `discord_callback` | every Discord login |
| `roles_hook/__init__.py:107` | `push_role_metadata` | any role delta |
| `roles_hook/__init__.py:125` | `refresh_discord_token` | paired with the above |
| `providers.py:75` | `fetch_deck_from_url` | every deck submitted by URL |

Cold path, same pattern: `github_app.py:67`, `twda_import.py:456`,
`roles_hook/__init__.py:77`, `twda.py:86`, `routes/feedback.py:124`,
`routes/auth/github.py:111`.

## The three that stay as they are

- `push_service.py:334` — one session per fan-out, shared across sends. A recorded
  decision (`wiki/architecture.md`), same rationale as this line.
- `vekn_api.py:74` — already the cached singleton this work generalises.
- `link_preview.py:82` — **must stay isolated.** It resolves the host and refuses
  non-global addresses before connecting, re-checking on each redirect hop
  (`wiki/hazards.md`). A shared connector would undermine that SSRF guard. The
  hazards entry exists so nobody later "finishes the job" and removes it.

`main.py:341` already has the `lifespan` asynccontextmanager to hang the
singleton on.

## Measured on prod, 2026-09-18

A 1 vCPU / 945MB VPS running a single uvicorn process, PG at
`max_connections: 20`.

Anonymous memory against process uptime:

```
 5h uptime  →  281 MB   (RssAnon 108.6 + VmSwap 172.3, measured 19:32 UTC)
16h uptime  →  489 MB   (derived, 06:52 UTC)
```

The 16h figure is **derived**, not directly measured: cgroup `memory.current`
269.5MB minus ~54MB page cache and ~2MB slab, plus 276MB swap. The two samples
are from different days under different load, so ~19 MB/h is indicative, not a
rigorous rate. What it does establish is that the footprint grows rather than
sitting flat — a flat baseline would have read ~281MB at both ends.

At 5h uptime `VmSwap` (172MB) already exceeded `RssAnon` (109MB) on a quiet
evening: more of the process on disk than in RAM before the day's load arrives.

Observed under load at 06:52 UTC that morning: 75% iowait against 0% user CPU,
21 connections queued to the single uvicorn process, and `/api/time` — a handler
that does nothing but `time.time_ns()` — taking 8s or timing out at 15s, while
nginx served static assets in 220ms.

`RuntimeMaxSec=1d` in the unit already calls itself "a low-key memory-leak
defense"; the daily restart resets the cycle and hides the growth.

## What is not established

That these call sites are the source of the growth. Repeated `SSLContext`
allocation through OpenSSL's malloc into glibc arenas that are never trimmed
back produces this linear-creep-then-reset-on-restart signature, but consistent
is not proven — confirming it means `tracemalloc`, or comparing a heavy-login
day against a quiet one.

The line does not depend on it. Removing a full TLS handshake from the login
path is a latency and CPU win on a 1 vCPU box whichever way the memory lands.
