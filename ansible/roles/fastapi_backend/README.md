# fastapi_backend role

Deploys the Archon FastAPI backend (wheel + venv + env file + systemd unit).
Parametrised via the `r` dict — see `defaults/main.yml` for the contract.

## Officials contacts (personal data — vault-delivered)

NC/Prince contact emails (scraped from the vekn.net official lists) are personal
data and are **never committed in plaintext** (the repo is public and CI ships
wheels as release assets). They're delivered out of band:

- The role copies `files/officials_contacts.json.vault` (an `ansible-vault`
  file) to `{{ env_dir }}/officials_contacts.json`, decrypting on the fly, and
  points the backend at it via `OFFICIALS_CONTACTS_FILE` (set in `env.j2`).
- The copy task uses `fileglob`, so it's a **no-op when the vault file is
  absent** — deploys never break, the backend just runs without the data.
- The backend (`vekn_sync.py`) loads it on sync and skips gracefully if missing.

### Provide / refresh the data

Regenerate the plaintext list with `backend/scripts/` tooling (the scrape isn't
fully automatable — the NC list is login-gated and emails are cloaked), then:

```bash
# from repo root, with your vault password configured (ansible.cfg / --vault-id)
cp <plaintext>/officials_contacts.json \
   ansible/roles/fastapi_backend/files/officials_contacts.json.vault
ansible-vault encrypt ansible/roles/fastapi_backend/files/officials_contacts.json.vault
git add ansible/roles/fastapi_backend/files/officials_contacts.json.vault   # ciphertext is safe to commit
```

`files/.gitignore` blocks committing a plaintext `officials_contacts.json` by
accident; only the `.vault` file is allowed.
