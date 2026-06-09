# #83 — CI deploy workflow (manual-dispatch + approval)

`.github/workflows/deploy.yml`. Runs the self-fetching deploy playbook (#82) from
a runner so deploys don't need a laptop.

## Decision (owner)
Both environments: **`workflow_dispatch`-only + approval gate**. Nothing
auto-deploys; beta and prod each pause for a required reviewer.

## How it works
- `workflow_dispatch` inputs: `environment` (choice beta|prod), `release_tag`
  (optional; blank = latest).
- `environment: ${{ inputs.environment }}` binds the job to the GitHub
  Environment → its **Required reviewers** rule is the approval gate.
- Steps: checkout → uv → write SSH key + known_hosts + vault pass from secrets →
  `uv run --project .. --group dev ansible-playbook -i inventories/<env>
  -e ansible_host=$DEPLOY_HOST [-e release_tag=…]` → cleanup.
- Inventory hosts are placeholders in git, so CI injects the real host via
  `-e ansible_host` (DEPLOY_HOST secret). `ansible_user=lpanhaleux` from inventory.
- `concurrency: deploy-<env>` serializes deploys to the same target.
- `permissions: contents: read`; `GITHUB_TOKEN` passed only to lift the release
  lookup's API rate limit (public repo).

## Manual setup the owner must do (workflow is inert without it)
Per-Environment (beta, prod): enable Required reviewers. Variables (not secret —
host IP + host key are public): `DEPLOY_HOST`, `DEPLOY_HOST_KEY` (a known_hosts
line whose host matches DEPLOY_HOST exactly). Secrets: `SSH_PRIVATE_KEY`
(dedicated key; public half in the server's authorized_keys),
`ANSIBLE_VAULT_PASSWORD`. VPS must allow SSH from GitHub runner IPs (port 22).
See ansible/README.md.

## Untested
Can't be exercised from here — needs the Environments/secrets configured and a
real run. Secrets are passed via step `env:` (not inline `${{ }}`) to avoid
shell-injection from secret content.

## Follow-up
#84 — consolidate ansible/Makefile → ansible/justfile (depends on #82, done).
