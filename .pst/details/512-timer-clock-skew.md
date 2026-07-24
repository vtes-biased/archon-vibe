# 512 — Round timer wrong on devices with a mis-set system clock

## Symptom
A beta tester (Spain) reported: clicking "iniciar" (Start) on a fresh round timer started the
countdown at **115:32** instead of the configured 120:00 (round_time 7200s). 7200 − 6932 = **268s**
(4m28s) of phantom elapsed at the instant of Start.

## Root cause (confirmed)
`TimerDisplay.svelte` computes the countdown as:

```
elapsed = elapsed_before_pause + (now − new Date(started_at)) / 1000     // now = Date.now()
```

`now` is the **client** wall clock; `started_at` is stamped by the **server** wall clock. The
subtraction mixes two clocks, so any client-vs-server offset shows up as phantom elapsed time. A
device ~268s fast makes a fresh timer (started_at ≈ server-now, elapsed_before_pause = 0) read
`7200 − 268 = 6932s = 115:32`. There is **no clock-offset correction anywhere** in the frontend.

## Evidence
- **Reproduced exactly on beta** (new.archon.krcg.org, "Test" tournament 019f705a…): started the
  timer (120:00), then overrode only `Date.now()` to `+268000ms`. Display dropped to 115:15
  (= 7200 − 268 − ~17s real elapsed); at the exact instant of Start it is 115:32 — the reporter's
  precise value. Restoring `Date.now()` fixed it.
- **Server clock verified accurate**: `timedatectl` synchronized, NTP active, stratum-2, 2ms jitter;
  `systemd-timesyncd`/kernel journals show **no clock step or adjustment in 3 days**. So the skew is
  client-side, not server-side.
- **This dev machine measured synced**: Date-header probe `serverDate − Date.now()` ≈ −0.5s (that
  −0.5s is just the HTTP Date header's 1-second quantization, not real skew).

## Hypotheses ruled out
- **"Start round → wait → start timer leaks the seating gap."** REFUTED empirically: waited 128s
  paused, then Start; `started_at` landed +3.1s after the Start *click* (= POST→SSE→IDB round-trip),
  **not** +131s after the round start; `elapsed_before_pause = 0`; countdown began at 120:00. The
  clock anchors to Start, the wait contributes nothing (matches `tournaments.py` — StartRound resets
  the timer to a fresh `TimerState()`; `timer_start` stamps `started_at = now`).
- **Page reload injects skew.** No — reload changes neither operand: `Date.now()` is the live OS
  clock; `started_at` is re-read byte-for-byte from IndexedDB. A reload computes the identical value.
  (The one reload-adjacent path — a stale running timer in IDB from a missed pause/reset frame —
  would show a "Pause" button and the reduced value *on load*, not the reported 120:00→snap-on-Start.)
- **"Drift."** The device doesn't need to *drift* (modern devices don't drift minutes); it needs to
  be *set wrong* (auto-time off, wrong manual set, VM/emulator, battery-pull with no re-sync) — a
  static offset with mundane causes, plausible on a tester's non-pristine rig.

## Chosen fix: correct Date.now()'s offset via mini-NTP (NOT a monotonic timebase)

Keep **`Date.now()` as the timebase** and correct only its **offset** against our server.

Why not the alternatives we walked through:
- **Monotonic (`performance.now()`) timebase** (the "roll our own clock / NTP" idea): principled for
  skew, but on several platforms (notably macOS) `performance.now()` **pauses during suspend/
  hibernate**, so after a lid-close it under-counts elapsed and shows too much time left. Crucially,
  `Date.now()` **already survives sleep** (the OS restores the wall clock on wake, so the countdown
  correctly accounts for the sleep). Switching to a monotonic timebase to fix the *rare* skew would
  **regress on the common** sleep case. So monotonic is used only as a **watchdog**, not the clock.
- **Server-authoritative "push remaining"**: makes everyone agree, but needs the server to recompute
  and re-broadcast remaining (fresh on every connect, not the 15-min cached snapshot) + interpolation
  — more server machinery than warranted.
- **Detect-and-deactivate only**: simple, but loses the timer on a skewed device; at a live event a
  timer that *works* (corrected) beats one that refuses. We keep the *advisory* from this idea.

### Mechanics
- **`/api/time`**: new tiny endpoint returning microsecond `server_time` (`datetime.now(UTC)`).
- **Sync (SNTP-over-HTTP)**: fire ~5 quick probes; keep the **minimum-RTT** sample (least jitter);
  `offset = server_time + RTT/2 − clientReceipt`. Accuracy ~tens–hundreds of ms — far inside a
  seconds-level tournament timer. Sync to **our** server (not pool.ntp.org): `started_at` is in our
  server's clock, so aligning to us is what makes the timer correct *and* converges every device.
- **Apply**: `elapsed = (Date.now() + offset) − started_at`. Every viewer references the same server
  clock → they agree to sub-second (kills the "5 devices, 5 timers" failure — passing devices
  converge; the wrong-number mode is gone).
- **Re-sync triggers**: on load, on `visibilitychange`→visible (resume), on SSE reconnect, and every
  few minutes.
- **Watchdog**: each tick compare `Δwall` (Date.now) vs `Δmono` (performance.now); if they diverge
  past a threshold, a sleep or a wall-clock step happened → force an offset re-sync before trusting
  the display. One check covers both.
- **Advisory**: when the raw system clock is off by **>15s**, show a non-blocking notice ("device
  clock ~X off — enable automatic date & time"). Surfaces the real fault (it also breaks the user's
  auth-token timing, calendar, etc.) without hiding the (now-corrected) timer. 15s chosen because the
  offset distribution is bimodal (synced ±1s vs wrong-by-minutes) — almost nothing lives in the
  15s–60s band, so the exact cutoff is not sensitive; 15s is well above measurement noise given the
  precise `server_time` source.

### Edge cases
- **Offline-first**: offline a tournament is single-device-locked, cross-device agreement is moot and
  we can't reach the server — fall back to the last-known offset / local tick (a countdown only needs
  monotonic elapsed on one device).
- **Bot**: unaffected — it runs server-side, so its clock *is* the server clock. No bot change.

## Scope
New frontend clock module (offset store + sync + watchdog) → consumed in `TimerDisplay.svelte`;
soft advisory in the timer UI; small `/api/time` endpoint. No change to the timer data model or the
sync architecture.

`TimerDisplay` is the **single** elapsed-computation site — round *and* finals both render it (513
wires the same component into FinalsTab + PlayerView's finals block via a `finals` prop). So this
one-place fix covers the finals timer too; no per-surface work, and 513 does not fragment the timer
math. (Do not reference 513 by `#`-number in code/commits per the repo convention.)

## Confirmed (root cause closed)
The reporter confirmed their **system clock was ~4 minutes wrong**; fixing it fixed the timer on
their end — matching the +268s reproduction exactly. Root cause fully closed (reproduction +
real-world confirmation). The fix stays warranted regardless: at a live event other officials/
players will have mis-set clocks we can't rely on them noticing, so the app must be robust
(offset-correct + advisory) rather than trusting every device's clock.

The console skew probe below is the diagnostic this feature would automate for any future report:

```js
(async () => {
  const p = [];
  for (let i=0;i<3;i++){
    const t0 = Date.now();
    const r = await fetch(location.origin + '/api/__clockprobe__' + t0, {cache:'no-store'});
    const t1 = Date.now();
    p.push(Math.round(Date.parse(r.headers.get('date')) - (t0+t1)/2));
  }
  console.log('device skew vs server (ms):', p);
})();
```
`~0` → their device was fine (hunt elsewhere); `~±268000` → wrong device clock, confirmed.
