# Board

A list designed to shrink. **The goal is zero.** Completion is deletion — there is
no closed state, no archive; git history is the record and `git blame` knows a
line's age.

**Order is priority.** Ranking rules, applied top to bottom when two unrelated
lines compete:

1. user-reported defects
2. correctness
3. blocking work and useful refactorings
4. polish
5. new capability

**Hard limit: 15 lines.** Adding a sixteenth forces a drop or a promotion to the
docs. **No waiting state**: externally-gated work is deferred on the docs page
that owns it — see [docs/vekn-decommission.md](docs/vekn-decommission.md) — with a
named trigger, and returns through `/intake` when the trigger fires.

**Every line must be completable** — if "done" cannot be stated, it is a subject:
promote it to a [docs](docs/index.md) page and delete the line. Context lives in
the docs; asks live here. Bulky context for an in-flight line goes in
`board/<slug>.md`, deleted with the line.

Board changes ride the commit that earns them.

- Adopt a `WATCH.md` beside the board for dated checks, recurring checks and externally-gated work: move the deferred asks out of `vekn-decommission.md` (its evidence stays as docs) and the Rules Director trigger off `tournaments.md`, leave the post-release journal where it is since it waits on a release rather than a date, add a watch-check skill that reads the file and sends fired items through intake, and stop upkeep watching triggers. Done when no docs page carries a triggered ask except the post-release journal, `WATCH.md` holds the moved items with when, what to check and what each outcome does, the intake and upkeep skills name the file, and `index.md` and `dev.md` describe it.
- Run the retrospective as published: ship writes a friction trailer on each commit (owner corrections, review rounds, surprises, failing checks); upkeep reads the trailers and recent session transcripts through a cheap-model subagent, proposes a rule at two occurrences with its evidence and a one-line reason, and removes rules whose reason has lapsed. Done when the ship skill names the trailer format, the upkeep skill names the mining step and the removal verdict, `principles.md` carries the trailer in its Git section, and one upkeep pass has run it.
- Explain what the event and member city field means — the community it belongs to, usually the nearest large city, not the exact location — with a hint on the event form and the member profile in every locale, so organizers stop looking for their village (gh-89). **Done when** both forms carry that hint, the event hint points the exact location to Address, and `docs/tournaments.md` (city row) and `docs/product.md` state the field's purpose: community size and turnout for organizers and the IC, which is why only larger cities are offered.
- Let a Prince see the members they sponsored: the members directory's Mine filter is empty for every Prince because their device never receives a member's sponsor — only IC and an NC in their own country do — so French Princes and a UK Prince find none of the members issued under their prefix. Add `coopted_by` to the member projection of a user: the id prefix and vekn.net's public registry already make a member's sponsor public. **Done when** a Prince's Mine filter lists every member whose recorded sponsor is them; a production check (owner-run) shows the members under the reported prefix carry that Prince as sponsor, or they are repaired in this change, including the case where one official's prefix starts another's; and `docs/sync.md` (user row, member column) and `docs/vekn.md` (`coopted_by`) are updated.
- Bring the remaining forms under `docs/design.md`'s handler-validation rule: the sanctions forms (SanctionsManager, TournamentSanctionModal — a date `min` tied to today), the auth forms (login, verify-email, LinkedAccounts — `type="email"`, `minlength`), User, nda, leagues/new and the two promo modals still let a browser constraint bubble gate their submit. **Done when** each such `<form>` carries `novalidate` and its submit handler checks every constraint the submit actually depends on (the rest of the attributes stay input hints), showing the message in the form's own error banner; no wiki page changes beyond the rule already stated.
- Run CI on the repo's mise toolchain: every job in the CI and release workflows installs its tools with `jdx/mise-action` from `mise.lock`, replacing the separate Python, Node, Rust and wasm-pack setup steps, so CI and the laptop build with the same versions. **Done when** no workflow carries its own tool setup or version (apart from the backend image's base and the manylinux wheel's `-i`, which cannot read mise), a pushed run is green, and `docs/dev.md` says CI takes its versions from `mise.lock`.
- Replace the justfile with mise tasks, per the owner's rule that a repo's commands live in mise: every recipe becomes a mise task under the same name (in `mise.toml` or `mise-tasks/`), the justfile and the `just` tool go away, and the pre-commit hook, the check scripts' messages, `CLAUDE.md`, the skills, the reviewer agent, the README and every wiki page name `mise run …` instead. **Done when** no `just <recipe>` call remains in those sources, `mise run test` and `mise run lint-check` pass, and `docs/dev.md` lists the tasks.
