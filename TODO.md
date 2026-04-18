# TODO

Deferred work surfaced during setup/deploy. Not blocking deploy but worth doing
before opening to a wider audience.

## Legal pages in the PWA (GDPR + Discord portal)

Add two static routes to the frontend and wire them to:
- Discord Developer Portal → *General Information* → **Terms of Service URL** + **Privacy Policy URL**
- A footer link on every page in the PWA
- A tick-box on the signup / consent flow: "I agree to the ToS and Privacy Policy"

### Files to create

- `frontend/src/routes/legal/privacy/+page.svelte`
- `frontend/src/routes/legal/terms/+page.svelte`

Same static content on beta + prod (short markdown-like prose in a Svelte
page). i18n via paraglide if we want multi-language later.

### Why this matters

- **GDPR** — archon collects from EU users: email, Discord ID + OAuth refresh
  token, VEKN ID + real name (via VEKN sync), tournament history, geonames
  city data, IPs in request logs. Under GDPR Art. 13–14 a privacy policy is
  mandatory for any of those. Not optional for an EU-hosted community service.
- **Discord bot verification** — becomes blocking once the bot crosses 100
  guilds (auto-triggers Discord's verification review), and some privileged
  scopes require the URLs to be set even earlier.
- **Trust** — the Discord OAuth consent screen shows these links; users are
  more likely to approve when they see a same-origin policy instead of blank
  fields.

### Minimum content outline

**Privacy policy**
- Data collected (email, Discord ID + refresh token, VEKN ID + profile,
  tournament history, locations, request logs)
- Purposes (auth, tournament management, Linked Roles via Discord, result
  submission to VEKN)
- Third parties data is shared with: Discord, vekn.net, Gmail SMTP (MAIL_*),
  GitHub (TWDA pull requests)
- Retention (tied to account lifetime; logs rotated per journald defaults)
- GDPR rights (access / export / deletion / rectification) + how to request
- Contact: `lionel.panhaleux@gmail.com`

**Terms of service**
- Community / non-commercial service
- Acceptable use (no abuse, no impersonation, organizers are responsible for
  their tournaments' accuracy)
- Code of conduct (point to VEKN's official CoC)
- Account termination clause
- "No warranty" disclaimer
- Governing law (France)
- Change process (we'll notify via email + in-app banner)

### After pages are live

Set in `ansible/inventories/{beta,prod}/group_vars/all.yml` if we ever want
them in env vars — currently they only need to be set in the Discord portal:

```
Terms of Service URL: https://archon.{domain}/legal/terms
Privacy Policy URL:   https://archon.{domain}/legal/privacy
```
