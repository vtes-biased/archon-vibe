// Server-clock offset correction (mini-NTP over /api/time).
//
// The round timer subtracts a SERVER-stamped `started_at` from the CLIENT's
// Date.now(); a mis-set device clock therefore renders phantom elapsed time
// (a device 4m fast shows a fresh 120:00 round as 115:32).
//
// We keep Date.now() as the timebase — it survives sleep/hibernate (the OS
// restores the wall clock on wake, so the countdown accounts for the sleep) —
// and correct only its OFFSET against OUR server, the same clock that stamps
// started_at. Every viewer then references one reference clock and converges to
// sub-second (no "5 devices, 5 timers"). A monotonic performance.now() timebase
// would fix skew but regress on sleep (it pauses during suspend), so it is used
// only as a divergence watchdog, never as the clock.

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const OFFSET_KEY = "clock-offset"; // persisted last-known offset (ms), for offline fallback
const PROBES = 5; // SNTP samples per sync; keep the min-RTT one (least jitter)
const PROBE_TIMEOUT_MS = 4000; // abort a wedged probe so a flaky venue Wi-Fi can't freeze re-sync
const RESYNC_INTERVAL_MS = 5 * 60_000; // periodic re-sync
const WATCHDOG_INTERVAL_MS = 1000; // wall-vs-mono divergence check cadence
const WATCHDOG_DIVERGENCE_MS = 2000; // Δwall−Δmono past this ⇒ sleep/step ⇒ re-sync
const ADVISORY_THRESHOLD_MS = 15_000; // raw system-clock skew past this ⇒ soft notice

// offset (ms) added to Date.now() to align it with the server clock.
let offset = $state(loadPersistedOffset());
// True once a successful probe has landed this session (gates the advisory so a
// pre-sync fallback offset never fires a false "wrong clock" notice).
let synced = $state(false);

let syncing = false;
let lastSyncMono = 0; // performance.now() at the last sync ATTEMPT (throttles re-sync)
let lastWall = 0;
let lastMono = 0;

let consumers = 0;
let watchdog: ReturnType<typeof setInterval> | undefined;
let cleanup: (() => void) | undefined;

function loadPersistedOffset(): number {
  if (typeof localStorage === "undefined") return 0;
  const v = Number(localStorage.getItem(OFFSET_KEY));
  return Number.isFinite(v) ? v : 0;
}

function persistOffset(v: number): void {
  try {
    localStorage?.setItem(OFFSET_KEY, String(Math.round(v)));
  } catch {
    // private-mode / quota — the in-memory offset still works for this session
  }
}

/** SNTP-over-HTTP: probe /api/time a few times, keep the min-RTT sample. */
async function syncClock(): Promise<void> {
  if (syncing) return;
  if (typeof navigator !== "undefined" && !navigator.onLine) return;
  syncing = true;
  try {
    let best: { rtt: number; off: number } | null = null;
    for (let i = 0; i < PROBES; i++) {
      const t0 = Date.now();
      let serverMs: number;
      try {
        const res = await fetch(`${API_URL}/api/time`, {
          cache: "no-store",
          signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
        });
        if (!res.ok) continue;
        serverMs = (await res.json()).server_time / 1000; // µs → ms
      } catch {
        continue; // transport failure, timeout, or malformed body — next probe
      }
      const t1 = Date.now();
      const rtt = t1 - t0;
      // Midpoint offset: assume the server stamp lands halfway through the RTT.
      const off = serverMs - (t0 + t1) / 2;
      // Reject a non-finite sample (missing/garbled server_time) so it can never
      // poison the offset into a NaN:NaN timer.
      if (Number.isFinite(off) && (!best || rtt < best.rtt)) best = { rtt, off };
    }
    if (best) {
      offset = best.off;
      synced = true;
      persistOffset(best.off);
    }
  } finally {
    lastSyncMono = performance.now(); // stamp the ATTEMPT to throttle re-sync
    syncing = false;
  }
}

// Each tick: compare Δwall (Date.now) vs Δmono (performance.now). Normal ticks —
// including a throttled hidden tab — advance both together. A sleep pauses mono
// but not wall, and a wall-clock step (NTP jump, manual set) moves wall but not
// mono; either diverges the deltas and invalidates the offset ⇒ re-sync. One
// check covers both. A step fires the divergence exactly once (next tick both
// deltas are normal again), so a failed re-sync can't loop.
function tick(): void {
  const wall = Date.now();
  const mono = performance.now();
  const diverged = Math.abs(wall - lastWall - (mono - lastMono)) > WATCHDOG_DIVERGENCE_MS;
  lastWall = wall;
  lastMono = mono;
  if (diverged || mono - lastSyncMono > RESYNC_INTERVAL_MS) void syncClock();
}

function onVisible(): void {
  if (document.visibilityState === "visible") void syncClock();
}

function start(): void {
  if (typeof window === "undefined") return;
  lastWall = Date.now();
  lastMono = performance.now();
  void syncClock();
  watchdog = setInterval(tick, WATCHDOG_INTERVAL_MS);
  // Resume (tab foreground / device wake) and SSE-reconnect proxy (online) both
  // re-align the offset. The SyncManager 'connected' event isn't wired here to
  // keep the store decoupled; 'online' covers the reconnect case in practice.
  document.addEventListener("visibilitychange", onVisible);
  window.addEventListener("online", syncClock);
  cleanup = () => {
    clearInterval(watchdog);
    watchdog = undefined;
    document.removeEventListener("visibilitychange", onVisible);
    window.removeEventListener("online", syncClock);
    cleanup = undefined;
  };
}

/**
 * Ref-counted activation: a TimerDisplay calls this on mount and invokes the
 * returned disposer on unmount. The probe/watchdog run only while a timer is on
 * screen (many timers share one clock). Not reactive — call from an $effect.
 */
export function activateClock(): () => void {
  consumers++;
  if (consumers === 1) start();
  return () => {
    consumers--;
    if (consumers === 0) cleanup?.();
  };
}

/** Offset (ms) to add to Date.now() so it matches the server clock. Reactive. */
export function getClockOffset(): number {
  return offset;
}

/**
 * Signed raw system-clock skew (ms) when it exceeds the advisory threshold, else
 * null. Positive = device clock ahead of the server. The offset CORRECTS the
 * skew, so raw skew = −offset. Reactive; null until a sync lands.
 */
export function getClockSkewAdvisory(): number | null {
  if (!synced) return null;
  const skew = -offset;
  return Math.abs(skew) > ADVISORY_THRESHOLD_MS ? skew : null;
}
