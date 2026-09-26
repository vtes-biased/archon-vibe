# FastAPI → Litestar

Doc-impact: architecture (stack line; API conventions — the Pydantic request-body
decision flips to msgspec), public-api (opening line; the whole Documentation
section), hazards (the "request accepted at the SIGTERM instant can still 502"
item: fix or re-defer; the socket-unit and uvicorn items stay true since uvicorn
stays), dev (nginx paragraph, Context7 table → `/websites/litestar_dev`, tree
listing), sync (pipeline line), access (nginx allowlist paragraph). Domain pages:
none.

## Decisions taken at intake

- **Server unchanged.** Litestar runs on the same uvicorn; the systemd units keep
  calling `uvicorn --fd 3 … <module>:app` directly — only the ASGI app object
  changes. Nothing socket-unit related is in scope.
- **Request bodies become msgspec Structs** injected via Litestar's `data`
  parameter; the recorded reason for Pydantic (FastAPI parses it) dies with
  FastAPI.

## Measured footprint (2026-09-26)

- 27 backend files import `fastapi`/`starlette`; nothing in `bot`, `vekn-api`,
  `engine`, `scripts` or `deploy/templates`.
- ~130 route decorators; imports dominated by `HTTPException` (24), `APIRouter`
  (22), `Response` (20), `Request` (10); `Depends` in only 3 files.
- 55 `BaseModel` request classes across 16 files.
- Two apps: `backend/src/main.py` (lifespan, CORS, SSE `StreamingResponse` for
  `/stream`) and `backend/src/public_api/main.py` (CORS, NDJSON streams,
  `FileResponse`, `get_openapi` + `openapi_extra` per route).
- The tests hit the HTTP boundary through Starlette's `TestClient` — they port
  to Litestar's test client.

## Traps to watch

- `main.py`'s SIGTERM hook chains onto uvicorn's plain `signal.signal` handler so
  `/stream` generators self-close; it is uvicorn-coupled, not FastAPI-coupled, and
  must survive the port.
- Public API docs: FastAPI adds its own `application/json` 200 which a pruning
  pass removes; Litestar's `ResponseSpec` / `Stream` schema generation differs
  (Stream-as-file was fixed in 2.18). Re-derive "exactly one media type per
  route" rather than translating the pruning. Scalar has a Litestar render plugin.
- Ranked last, so the request-ID/log-masking and per-client throttle lines may
  land on FastAPI first: whatever they add to the backend's HTTP layer
  (middleware, access-log format, throttle keying) ports with this line.
