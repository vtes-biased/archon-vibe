# Putting the public API online — context for the beta deploy

Doc-impact: none left. The grant, the throttle and the deployment shape are on
[`wiki/access.md`](../wiki/access.md), [`wiki/dev.md`](../wiki/dev.md) and
[`wiki/public-api.md`](../wiki/public-api.md); this file is only the runbook.

Everything is written and unrun: the `client_credentials` grant, the `public_api`
role (unit + env + `conf.d` zones + vhost), `nginx_tls` for `domain_api`, and both
playbooks. Beta values: `api.archon.krcg.org`, port 7008, unit
`new-archon-public-api`.

## Order

1. **DNS A record** for `api.archon.krcg.org` → the beta host. Nothing else can
   run first: `nginx_tls` calls certbot with `--webroot`, which needs the name to
   resolve to that box.
2. **Full beta deploy** — `cd ansible && just deploy-beta`. Not the quick lane:
   `--tags app` skips `nginx_tls` and `public_api` entirely, so the cert, the
   unit and the vhost would never be created.
3. **Register a client.** Profile → Developer → Register, name it, leave the
   redirect URIs empty, tick `api:read` only. Keep the secret; it is shown once.

## Verification

Against `https://api.archon.krcg.org`, with `$ID`/`$SECRET` from step 3 and
`$TOKEN` from the first call:

```bash
curl -sX POST https://archon.krcg.org/oauth/token -H 'Content-Type: application/json' \
  -d "{\"grant_type\":\"client_credentials\",\"client_id\":\"$ID\",\"client_secret\":\"$SECRET\"}"

# one full refresh, unthrottled: five streams, ~6.5 MB gzipped
for p in tournaments leagues decks rankings community-links; do
  curl -s -o /dev/null -w "$p %{http_code} %{size_download}\n" \
    -H "Authorization: Bearer $TOKEN" --compressed "https://api.archon.krcg.org/v1/$p"
done

# a tight loop: the first ten clear the burst, the rest must 429
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code} " -H "Authorization: Bearer $TOKEN" \
    "https://api.archon.krcg.org/v1/leagues"
done; echo

# the app refuses the token it minted
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" \
  https://archon.krcg.org/oauth/userinfo     # expect 401

curl -s https://api.archon.krcg.org/docs | head -c 200   # reference page renders
```

`/v1/export` needs the app's snapshot generator to have run at least once on
beta; before that it answers 503, which is correct rather than broken.

Prod repeats the same three steps with `api.archon.vekn.net`, port 7007, unit
`archon-public-api` — after beta has been observed, and it is the owner's window.

## Still binding

Owner decisions (intake 2026-08-22): auth required, no anonymous read;
Archon-native rather than under the krcg umbrella — krcg stays the card-data
authority, Archon is the system of record for organizational data.
