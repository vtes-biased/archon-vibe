"""Drive N concurrent SSE clients through the EC-rehearsal phases (wiki/sync.md).

Three phases, mirroring what a 200-player room does to the stream stack:

  cold        every client fetches /snapshot (full download, header line parsed
              for the cursor pair, X-Access-Version kept), then opens /stream
              with since/generated_at/av and reads to sync_complete; streams
              are then held live.
  cursorless  every client opens a bare /stream in parallel with the held
              streams and expects the resync directive followed by server close.
  reconnect   every held stream is dropped hard (no goodbye, venue-wifi style),
              then all clients reconnect at once with their cursors and read to
              sync_complete again.

Usage:
    python loadtest_stream.py --base-url https://archon.krcg.org \
        --clients 200 --tokens-file tokens.txt --out metrics.json

Clients beyond the tokens file run anonymous (public level). Emits a JSON
metrics file with per-phase wall-clock bounds (epoch seconds, for joining
against loadtest_sample.sh output) and per-client timings, and prints a
summary table. Timings are seconds.
"""

import argparse
import asyncio
import json
import resource
import statistics
import sys
import time
import uuid

import aiohttp

SYNC_COMPLETE_PREFIX = 'data: {"type":"sync_complete"'
RESYNC_LINE = 'data: {"type":"resync"}'
HEARTBEAT_LINE = 'data: {"type":"heartbeat"}'


class Client:
    def __init__(self, idx: int, token: str | None):
        self.idx = idx
        self.token = token
        self.device_id = f"loadtest-{uuid.uuid4()}"
        self.av: str | None = None
        self.since: str | None = None
        self.generated_at: str | None = None
        self.resp: aiohttp.ClientResponse | None = None
        self.reader: asyncio.Task | None = None
        self.live_frames = 0

    def stream_params(self, cursorless: bool = False) -> dict[str, str]:
        params = {"device_id": self.device_id}
        if self.token:
            params["token"] = self.token
        if not cursorless:
            if self.since:
                params["since"] = self.since
            if self.generated_at:
                params["generated_at"] = self.generated_at
            if self.av:
                params["av"] = self.av
        return params


async def fetch_snapshot(session: aiohttp.ClientSession, base: str, c: Client) -> dict:
    params = {"token": c.token} if c.token else {}
    t0 = time.monotonic()
    async with session.get(f"{base}/snapshot", params=params) as resp:
        ttfb = time.monotonic() - t0
        if resp.status != 200:
            return {"error": f"snapshot HTTP {resp.status}", "ttfb": ttfb}
        c.av = resp.headers.get("X-Access-Version")
        header_line = await resp.content.readline()
        header = json.loads(header_line)
        c.since = header.get("timestamp")
        c.generated_at = header.get("generated_at")
        nbytes = len(header_line)
        async for chunk in resp.content.iter_chunked(1 << 16):
            nbytes += len(chunk)
        return {
            "ttfb": ttfb,
            "duration": time.monotonic() - t0,
            "bytes_inflated": nbytes,
        }


async def read_to_sync_complete(
    resp: aiohttp.ClientResponse, c: Client, t0: float
) -> dict:
    ttfb = None
    frames = 0
    async for raw in resp.content:
        if ttfb is None:
            ttfb = time.monotonic() - t0
        line = raw.decode(errors="replace").rstrip("\n")
        if not line.startswith("data: "):
            continue
        frames += 1
        if line.startswith(SYNC_COMPLETE_PREFIX):
            ts = json.loads(line[6:]).get("timestamp")
            if ts:
                c.since = ts
            return {
                "ttfb": ttfb,
                "sync_complete": time.monotonic() - t0,
                "frames": frames,
            }
        if line == RESYNC_LINE:
            return {"error": "unexpected resync", "ttfb": ttfb}
    return {"error": "stream ended before sync_complete", "ttfb": ttfb}


async def hold_live(resp: aiohttp.ClientResponse, c: Client) -> None:
    try:
        async for raw in resp.content:
            line = raw.decode(errors="replace").rstrip("\n")
            if line.startswith("data: ") and line != HEARTBEAT_LINE:
                c.live_frames += 1
    except (aiohttp.ClientError, asyncio.CancelledError):
        pass


async def open_stream(
    session: aiohttp.ClientSession, base: str, c: Client, hold: bool
) -> dict:
    t0 = time.monotonic()
    try:
        resp = await session.get(f"{base}/stream", params=c.stream_params())
        if resp.status != 200:
            resp.close()
            return {"error": f"stream HTTP {resp.status}"}
        result = await read_to_sync_complete(resp, c, t0)
        if "error" in result or not hold:
            resp.close()
            return result
        c.resp = resp
        c.reader = asyncio.create_task(hold_live(resp, c))
        return result
    except (aiohttp.ClientError, ValueError, TimeoutError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def phase_cold(session: aiohttp.ClientSession, base: str, c: Client) -> dict:
    try:
        snap = await fetch_snapshot(session, base, c)
        if "error" in snap:
            return {"snapshot": snap, "error": snap["error"]}
        stream = await open_stream(session, base, c, hold=True)
        out = {"snapshot": snap, "stream": stream}
        if "error" in stream:
            out["error"] = stream["error"]
        return out
    except (aiohttp.ClientError, ValueError, TimeoutError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def phase_cursorless(
    session: aiohttp.ClientSession, base: str, c: Client
) -> dict:
    t0 = time.monotonic()
    try:
        async with session.get(
            f"{base}/stream", params=c.stream_params(cursorless=True)
        ) as resp:
            if resp.status != 200:
                return {"error": f"stream HTTP {resp.status}"}
            async for raw in resp.content:
                line = raw.decode(errors="replace").rstrip("\n")
                if line == RESYNC_LINE:
                    resync_at = time.monotonic() - t0
                    await resp.content.read()
                    return {"resync": resync_at, "closed": time.monotonic() - t0}
            return {"error": "stream ended without resync"}
    except (aiohttp.ClientError, ValueError, TimeoutError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


def drop_stream(c: Client) -> None:
    if c.reader:
        c.reader.cancel()
        c.reader = None
    if c.resp:
        c.resp.close()
        c.resp = None


async def phase_reconnect(session: aiohttp.ClientSession, base: str, c: Client) -> dict:
    return await open_stream(session, base, c, hold=True)


def aggregate(values: list[float]) -> dict:
    if not values:
        return {}
    values = sorted(values)
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 3),
        "p50": round(values[len(values) // 2], 3),
        "p95": round(values[int(len(values) * 0.95) - 1], 3),
        "max": round(values[-1], 3),
    }


def summarize(name: str, results: list[dict], keys: list[tuple[str, ...]]) -> dict:
    errors = [r.get("error") for r in results if r.get("error")]
    agg: dict = {"clients": len(results), "errors": len(errors)}
    if errors:
        agg["error_samples"] = errors[:5]
    for path in keys:
        values = []
        for r in results:
            v: object = r
            for k in path:
                v = v.get(k) if isinstance(v, dict) else None
            if isinstance(v, int | float):
                values.append(float(v))
        agg[".".join(path)] = aggregate(values)
    print(f"\n== {name} ==")
    for k, v in agg.items():
        print(f"  {k}: {v}")
    return agg


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--clients", type=int, default=200)
    parser.add_argument("--tokens-file")
    parser.add_argument("--hold", type=float, default=30.0)
    parser.add_argument("--drop-gap", type=float, default=5.0)
    parser.add_argument("--out", default="loadtest_metrics.json")
    args = parser.parse_args()

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < args.clients * 4:
        resource.setrlimit(
            resource.RLIMIT_NOFILE, (min(max(args.clients * 4, 4096), hard), hard)
        )

    tokens: list[str] = []
    if args.tokens_file:
        with open(args.tokens_file) as f:
            tokens = [line.strip() for line in f if line.strip()]
    clients = [
        Client(i, tokens[i] if i < len(tokens) else None) for i in range(args.clients)
    ]
    print(
        f"{len(clients)} clients ({min(len(tokens), len(clients))} member, "
        f"{len(clients) - min(len(tokens), len(clients))} anonymous) "
        f"against {args.base_url}"
    )

    report: dict = {
        "base_url": args.base_url,
        "clients": len(clients),
        "member_clients": min(len(tokens), len(clients)),
        "phases": {},
    }
    connector = aiohttp.TCPConnector(limit=0)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=30, sock_read=90)
    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout, read_bufsize=1 << 20, auto_decompress=True
    ) as session:
        base = args.base_url.rstrip("/")

        t_start = time.time()
        cold = await asyncio.gather(*(phase_cold(session, base, c) for c in clients))
        report["phases"]["cold"] = {
            "t_start": t_start,
            "t_end": time.time(),
            "summary": summarize(
                "cold connect",
                cold,
                [
                    ("snapshot", "ttfb"),
                    ("snapshot", "duration"),
                    ("snapshot", "bytes_inflated"),
                    ("stream", "ttfb"),
                    ("stream", "sync_complete"),
                ],
            ),
            "results": cold,
        }

        print(f"\nholding {args.hold}s of live streams...")
        await asyncio.sleep(args.hold)

        t_start = time.time()
        cursorless = await asyncio.gather(
            *(phase_cursorless(session, base, c) for c in clients)
        )
        report["phases"]["cursorless"] = {
            "t_start": t_start,
            "t_end": time.time(),
            "summary": summarize(
                "mass cursorless connect", cursorless, [("resync",), ("closed",)]
            ),
            "results": cursorless,
        }

        print(f"\ndropping every held stream, reconnecting in {args.drop_gap}s...")
        for c in clients:
            drop_stream(c)
        await asyncio.sleep(args.drop_gap)

        t_start = time.time()
        reconnect = await asyncio.gather(
            *(phase_reconnect(session, base, c) for c in clients)
        )
        report["phases"]["reconnect"] = {
            "t_start": t_start,
            "t_end": time.time(),
            "summary": summarize(
                "reconnect burst",
                reconnect,
                [("ttfb",), ("sync_complete",), ("frames",)],
            ),
            "results": reconnect,
        }

        await asyncio.sleep(min(args.hold, 15.0))
        for c in clients:
            drop_stream(c)

    with open(args.out, "w") as f:
        json.dump(report, f, indent=1)
    print(f"\nmetrics written to {args.out}")
    failed = sum(
        1
        for phase in report["phases"].values()
        for r in phase["results"]
        if r.get("error")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
