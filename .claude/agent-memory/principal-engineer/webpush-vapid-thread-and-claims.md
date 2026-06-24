---
name: webpush-vapid-thread-and-claims
description: Web Push (pywebpush) thread-safety + vapid_claims mutation traps — what is and isn't safe to share across concurrent sends
metadata:
  type: project
---

Web Push delivery (`backend/src/push_service.py`) fans `webpush()` out over `asyncio.to_thread` under a `Semaphore`. Two pywebpush/py_vapid facts decide what's safe to share:

- **`vapid_claims` dict IS mutated in place** by `webpush()` (py_vapid `__init__.py` lines ~489-499 set per-endpoint `aud` and a 12h `exp`). A shared claims dict would carry a stale `aud` to the next endpoint. Fix is a fresh `{"sub": ...}` dict per send (`_webpush_sync` builds one each call). Preserve this — don't hoist it to a module constant.
- **The `Vapid01` instance is NOT mutated** by signing: `Vapid01.sign` → `_base_sign` deep-copies the claims and only reads `self._private_key`/`self._public_key`; the underlying cryptography `EllipticCurvePrivateKey` sign is thread-safe. So one shared `_vapid` instance across concurrent `to_thread` calls is safe — no per-send keypair load needed.

**Why:** the obvious "share one object, copy the other" instinct is backwards here — the cheap dict is the one that must be fresh, the expensive keypair is the one that's shareable.
**How to apply:** if anyone "optimizes" by caching the claims dict or by re-loading `Vapid01` per send, the first breaks correctness (cross-endpoint audience) and the second is pointless overhead. Verify both against the installed pywebpush/py_vapid source, not from memory — these are version-specific internals.
