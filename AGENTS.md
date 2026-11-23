@[CLAUDE.md](CLAUDE.md)

## Antigravity

This repo's primary harness lives in `CLAUDE.md` and `.claude/`. Antigravity
loads the same instructions (inlined above) and the same skills
(`.agents/skills.json` -> `.claude/skills`), with Antigravity-native subagents
and hooks under `.agents/`:

- **Tool equivalents** for references in `CLAUDE.md` and `.claude/skills/*`:
  `AskUserQuestion` -> `ask_question`, `Agent` -> `invoke_subagent`,
  `ListAgents` / `SendMessage` -> `manage_subagents` / `send_message`.
- **Subagents** (`.agents/agents/`): `reviewer` (`pro`, read-only + shell),
  `mass-edit` (`flash`, no subagent tools), and `miner` (`flash`, read-only).
  Use `mass-edit` for mechanical fan-out passes rather than spawning `self` or
  a `pro` subagent.
- **Hooks** (`.agents/hooks.json`): `todo-lint` blocks `TODO`/`FIXME`/`XXX`/`HACK`
  in code via `PreToolUse`; `test-diff-flag` flags touched test files via
  `PostToolUse` + `PostInvocation`.
- **No personal memory store**: same three-lifespans rule as `CLAUDE.md` — put
  project facts in `docs/`, and standing harness fixes in `CLAUDE.md`/`AGENTS.md`,
  skills, agents, or hooks.
- **Upkeep retrospective**: mine Antigravity transcripts under
  `~/.gemini/antigravity*/brain/*/.system_generated/logs/transcript.jsonl`
  alongside `~/.claude/projects/"$(pwd | tr / -)"/*.jsonl`. The `miner` agent
  understands both formats.
- **Look it up (Antigravity)**: for Antigravity's own features (rules, skills,
  agents, hooks, plugins, MCP), read the built-in `agy-customizations` /
  `antigravity-guide` skills or `https://antigravity.google/docs`.
- **Grafana MCP** (`.agents/plugins/archon-grafana/`): ships disabled by default
  so contributors without `$GRAFANA_TOKEN_VTESBIASED` do not hit startup errors.
  Enable once locally with `agy plugin enable archon-grafana` or in the
  Customizations UI.
