# fastapi_backend role

Deploys the Archon FastAPI backend (wheel + venv + env file + systemd unit).
Parametrised via the `r` dict — see `defaults/main.yml` for the contract.

## Per-env vault files

Each env (`beta`, `prod`) has its **own** ansible-vault password, stored as the
`ANSIBLE_VAULT_PASSWORD` secret on the matching GitHub Environment (and locally in
`ansible/.vault_pass`). A deploy decrypts everything with that single per-env key,
so any secret file the role touches must be encrypted with **that env's** key.

Secret files in `files/` therefore come in per-env variants —
`<name>.beta.vault` and `<name>.prod.vault` — and the caller selects the right one
per env (`r.officials_contacts_vault` / `r.twda_key_vault`, set in
`deploy-beta.yml` / `deploy.yml`). The runtime destination is identical; only the
source variant (and its key) differs, so each env only ever decrypts its own file.

## Officials contacts (personal data — vault-delivered)

NC/Prince contact emails (scraped from the vekn.net official lists) are personal
data and are **never committed in plaintext** (the repo is public and CI ships
wheels as release assets). They're delivered out of band:

- The role copies `files/officials_contacts.json.<env>.vault` (an `ansible-vault`
  file) to `{{ env_dir }}/officials_contacts.json`, decrypting on the fly, and
  points the backend at it via `OFFICIALS_CONTACTS_FILE` (set in `env.j2`).
- The copy task uses `fileglob`, so it's a **no-op when the vault file is
  absent** — deploys never break, the backend just runs without the data.
- The backend (`vekn_sync.py`) loads it on sync and skips gracefully if missing.

### Provide / refresh the data

Regenerate the plaintext list with `backend/scripts/` tooling (the scrape isn't
fully automatable — the NC list is login-gated and emails are cloaked), then
encrypt it for **each env with that env's key** (`--vault-id` or the matching
`ANSIBLE_VAULT_PASSWORD_FILE`):

```bash
# from repo root. Repeat per env (beta, prod) with that env's vault password.
cp <plaintext>/officials_contacts.json \
   ansible/roles/fastapi_backend/files/officials_contacts.json.beta.vault
ansible-vault encrypt ansible/roles/fastapi_backend/files/officials_contacts.json.beta.vault
git add ansible/roles/fastapi_backend/files/officials_contacts.json.beta.vault   # ciphertext is safe to commit
```

To re-key the existing `…prod.vault` from an old password to the new prod key:
`ansible-vault rekey --new-vault-password-file <newprod> …officials_contacts.json.prod.vault`.

`files/.gitignore` blocks committing a plaintext `officials_contacts.json` by
accident; only the `.beta.vault` / `.prod.vault` files are allowed.

### Dev

The committed ciphertext is also the dev source — decrypt it directly (with the
matching env's vault password) into the gitignored runtime path the backend reads
when `OFFICIALS_CONTACTS_FILE` is unset:

```bash
ansible-vault view ansible/roles/fastapi_backend/files/officials_contacts.json.prod.vault \
  > backend/src/data/officials_contacts.json
```

The repo never holds the plaintext; the vault password is the only gate.

## Feedback GitHub App (env vars + vault-delivered key)

The in-app feedback endpoint files GitHub issues on `vtes-biased/archon-vibe` via a
**dedicated GitHub App** (separate from TWDA's, so the two integrations stay isolated)
with **Issues: write**, installed only on this repo. Three env vars, configured like
the TWDA App below:

- `FEEDBACK_GITHUB_CLIENT_ID` (the App's client id, used as the JWT iss) and
  `FEEDBACK_GITHUB_INSTALLATION_ID` (numeric) are short, so they ride in the env file
  via `vault_feedback_github_client_id` / `vault_feedback_github_installation_id`.
- `FEEDBACK_GITHUB_PRIVATE_KEY` is the multi-line PEM — delivered out of band exactly like
  the TWDA key (next section): the role copies `files/feedback_github_app.pem.<env>.vault`
  to `{{ env_dir }}/feedback_github_app.pem`, and `vault_feedback_github_private_key` is set
  to that **path**.

Any of the three unset → `POST /api/feedback/` returns 503 (graceful degradation). Provide /
refresh the key the same way as the TWDA key, using `feedback_github_app.pem.<env>.vault`.

Pre-create the `feedback` label on the repo once (the category labels `bug`/`enhancement`/
`question` are GitHub defaults) for predictable colour/grouping.

## TWDA GitHub App key (secret — vault-delivered)

The TWDA importer authenticates as a GitHub App using a private key (PEM). The key
is a **multi-line** secret, so it can't ride in the systemd `EnvironmentFile`
(flat `KEY=value` lines) — it's delivered out of band, same pattern as above:

- The role copies `files/twda_github_app.pem.<env>.vault` (an `ansible-vault` file)
  to `{{ env_dir }}/twda_github_app.pem`, decrypting on the fly. Point the backend
  at it by setting `TWDA_GITHUB_PRIVATE_KEY` to that **path** (`twda.py:_load_private_key`
  reads the file when the value isn't inline PEM). On beta that's
  `vault_twda_github_private_key: /etc/new_archon/twda_github_app.pem`.
- Each env has its own GitHub App, so the `.beta.vault` and `.prod.vault` hold
  *different* keys (encrypted with that env's vault password).
- The copy task uses `fileglob`, so it's a **no-op when the vault file is absent**
  — deploys never break. TWDA itself also no-ops unless all three of
  `TWDA_GITHUB_CLIENT_ID` (client id, JWT iss), `TWDA_GITHUB_INSTALLATION_ID` (numeric),
  and `TWDA_GITHUB_PRIVATE_KEY` are set (`twda.py:93`).

### Provide / refresh the key

Download the App's private key from the GitHub portal (a `.pem`), then encrypt it
with the matching **env's** vault password:

```bash
# from repo root. Per env (beta, prod), each with its own App's key + that env's vault password.
cp <downloaded>.pem \
   ansible/roles/fastapi_backend/files/twda_github_app.pem.beta.vault
ansible-vault encrypt ansible/roles/fastapi_backend/files/twda_github_app.pem.beta.vault
git add ansible/roles/fastapi_backend/files/twda_github_app.pem.beta.vault   # ciphertext is safe to commit
```

`files/.gitignore` blocks committing a plaintext `twda_github_app.pem` by accident;
only the `.beta.vault` / `.prod.vault` files are allowed.
