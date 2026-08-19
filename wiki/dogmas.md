# Dogmas

Human-chosen paradigms. Ingress checks a new ask against this page; egress checks
a change against it. Overturning one of these is valid work — violating one
silently is not.

## Architecture

**Offline-first is non-negotiable.** Every UI read comes from IndexedDB. The
backend API exists for mutations. SSE pushes state changes per user at the
role-appropriate level. There is exactly one sanctioned exception, and it has
four conditions — [sync](sync.md#online-only-rest-reads).

**All business logic lives in the shared Rust engine**, compiled to WASM
(frontend) and PyO3 (backend), so online and offline paths cannot diverge. No
business logic in Python or TypeScript. Authorization predicates, scoring,
validation, seating, ratings and the error taxonomy are all single-sourced there.

**A fact the engine holds is exported, never re-typed.** Sharing one
implementation across the frontend, the backend and the offline path is the whole
reason the engine compiles to WASM and PyO3 — a table, a normalizer or a
predicate copied into TypeScript or Python is drift waiting to surface as a
user-visible wrong answer. Export it and call it. When the export is awkward
because the engine loads asynchronously and the caller is synchronous, fix the
call site; a copy is not the cheaper option, it is the one whose cost lands later.

**Server always wins.** Mutations apply optimistically in WASM; the server's SSE
frame is authoritative and overwrites. Apply semantics are overwrite-by-uid,
never field-merge — a merge would preserve stale optimistic fields forever.

**One schemaless table, three pre-computed projections.** All synced objects live
in `objects` with `public`/`member`/`full` JSONB columns written at write time.
No ORM, no schema migrations, no read-time per-viewer filtering.

**No server-side pagination** on the rare online-only REST reads. Those datasets
are small by design; return the whole role-scoped set and filter client-side.
Role scoping stays server-side — it is access control, not computation.
Authoritative totals everyone must agree on (ratings, stock counts) are the
inverse: server-computed, denormalized, streamed through the normal sync. A total
derived client-side shows different numbers to viewers with different sync state.

## Code

**Locality over DRY.** Co-locate what changes together. Prefer explicit, greppable
local code over clever wrappers. Extract a module only behind an interface much
narrower than what it hides; layering ceremony and hexagonal indirection
mass-produce shallow modules, which are pure token cost and misuse surface.

**SoT for facts, repetition for shape.** Facts and invariants — schemas,
constants, protocol rules, permission predicates — live in exactly one place.
Similar-looking but causally unrelated code stays repeated. Never factor on
resemblance.

**KISS means hazard-avoidance.** Difficulty is not measured in hours: big
rewrites are cheap. What is expensive is *hazard* — non-local interdependency,
behavior not evident where it lives, traps for an agent without today's context.
Prefer the design a fresh agent understands from the files in front of it. The
standing traps are catalogued in [hazards](hazards.md).

**Comments are for traps only.** The wiki holds the why, the code shows the how.
A comment is justified only by a subtle non-local constraint invisible at the
point of reading. No narration, no changelogs, no TODOs — discovered work goes
through ingress or gets done now. A comment past ~2 lines is usually narrating,
and a contiguous comment block over three fails `just lint` whatever token it is
written in ([dev](dev.md#lint-gates)) —
a rationale that needs more room is a wiki page in the wrong file. Code never
references the wiki: a trap comment states its constraint and stands alone; the
wiki points at code, never the reverse.

**Component splitting.** A Svelte page past ~1000 lines gets its sections
extracted into child components: props down, state ownership stays in the parent.

**No red builds.** Never report done over a failing build, test or lint. When
touching build/packaging/test config, run the affected `just` target and confirm
green.

## Testing

Few tests, high coverage of behavior. Test what the product does at its
boundaries — API, CLI, end-to-end nominal paths, and the failure modes that
matter — never how it does it. Agents don't make local mistakes; they make
non-local ones. Unit tests of internals calcify implementation and tax every
change; integration and non-regression tests catch what matters and survive
refactors.

- Every test traces to a behavior declared in this wiki. A test nobody can map to
  a wiki claim is evicted.
- **Mocks are banned by default** — a mock that mirrors the code tests the code
  against itself. Use real dependencies (containers, temp files) or don't test
  that path. The one carve-out is a system we neither own nor can run — Discord,
  the VEKN registry, GitHub — where a validated fake paired with a guard test
  pinning it to the real contract is legitimate. It never reaches our own code:
  faking the engine, the database or one of our own modules is the banned case
  itself, not an instance of the exception.
- Property-style tests are for genuinely hazardous invariants — parsing, money,
  concurrency — the same spots KISS flags.
- Never encode engine-impossible states: VP sums equal table size, tables are 4–5
  seats, stored `gw`/`tp` agree with `compute_gw`/`compute_tp`, officials hold a
  `vekn_id`.

Mechanics, layers and known fixture traps: [testing](testing.md).

## Review

**Every review finding is addressed.** Egress classifies a finding blocking or
advisory; advisory means it does not stop the landing, never that it may be
dropped — it is fixed in the same change, or becomes a board line through
ingress. The counterweight is a reviewer with no quota: "looks good" is a common
verdict, and report-everything must not become find-something.

Egress runs a named **comment pass** over every diff that touches code, deleting
any comment the wiki, another comment, or the code itself already states. The
three-line ceiling above catches the bulk; the pass catches the duplication.

## Product

**The app manages tournament logistics, not the card game.** No card rulings, no
rules engine for play itself.

**Payments are status-only** — Pending/Paid/Refunded/Cancelled, no amounts, no
reconciliation. If richer money handling is ever wanted, integrate a ticketing
platform rather than building a ledger.

**No public/third-party API today.** The half-built read surface was removed
deliberately. The OAuth2 provider stays as the auth substrate. Building one is a
real project — versioning, OpenAPI, rate limiting, scoped tokens, pagination,
tests against a real client — and waits for an actual external consumer.

**IC holds every capability, everywhere.** Wherever a rule names Prince or NC, IC
has the same or more.

**Reversibility over confirmation.** Prefer making an action cleanly undoable to
adding a confirm dialog. Reserve explicit confirmation for the genuinely
irreversible or externally visible — finishing a tournament (write-once VEKN
push), removing your own organizer access, destructive deletes.

**Never render a figure we can't compute correctly.** Authoritative numbers
(ratings, totals, standings) are blank rather than approximate. Compute through
the engine, never beside it, and match the backend's inclusion filter as well as
its formula. A plausible wrong number is worse than an absent one because nobody
can tell it is wrong.

## Frontend

**Mobile-first.** 44×44px touch-target floor, no hover-only interaction, bottom
navigation, tap-to-swap instead of drag-and-drop anywhere in the app.

**Auto-save.** No explicit save buttons; changes persist as they are made, so the
exit action is Close/Done and a pending debounce is flushed on close, never
dropped.

**The gothic palette is pinned.** Role tokens via CSS `light-dark()`, crimson as
the single positive accent, violet for destructive, no green/amber/teal. The
`frontend-design` skill contributes craft and a quality floor; its "pick a
bespoke palette" guidance does not apply to surfaces inside the app. Details:
[design](design.md).

**Every user-facing string goes through Paraglide** in all five locales. Official
VTES game terms use the Black Chantry rulebook translations. Conventions and
per-locale traps: [i18n](i18n.md).

## Dependencies and data

Minimal dependencies, chosen against the offline constraint — `lucide-svelte`
over `@iconify` because runtime icon fetching breaks offline; `pywebpush` owns the
RFC 8291/8292 crypto we deliberately don't hand-roll while we own only the
transport.

**Bundled data files load via `importlib.resources`**, never `Path(__file__)`.
The backend ships as an installed wheel in CI; `files()` resolves there,
`__file__` is a runtime-path bug waiting to happen.

**Personal data and secrets are never committed.** The repo is public and CI
publishes wheels as release assets, so PII bundled into the package ships inside
the public wheel. Deliver it out of band: an `ansible-vault` file decrypted at
deploy to an env-pointed runtime path, with an untracked dev copy and graceful
absence.

## Git

Commit the wiki edit and the board line deletion with the code change that earns
them — one unit of work, one change.

**Reference GitHub issues, never close them from a commit.** `#N` in a commit
message means a GitHub issue, and a fix for a user-reported one carries
`Reported in #N.` — that backlink is how a release works out which issues it
ships. Never use `Closes`/`Fixes`/`Resolves`: those auto-close on push, and a
public feedback issue closes when the fix **deploys** and the reporter can see it
work.
