# Legal pages — privacy policy + terms of service (epic #20)

Migrated from the old `TODO.md` (2026-06-03). GDPR + Discord-portal driven. Children: #21–#24.
Not blocking deploy, but do before opening to a wider audience.

## Why this matters
- **GDPR** — Archon collects from EU users: email, Discord ID + OAuth refresh token, VEKN ID + real name (via VEKN sync), tournament history, geonames city data, IPs in request logs. Under GDPR Art. 13–14 a privacy policy is mandatory for any of those — not optional for an EU-hosted community service.
- **Discord bot verification** — becomes blocking once the bot crosses 100 guilds (auto-triggers Discord's verification review); some privileged scopes require the URLs even earlier.
- **Trust** — the Discord OAuth consent screen shows these links; users approve more readily with a same-origin policy than blank fields.

## Tickets
- **#21** Create the two static Svelte routes: `frontend/src/routes/legal/privacy/+page.svelte` and `frontend/src/routes/legal/terms/+page.svelte`. Same static content on beta + prod (short prose). i18n via Paraglide later if wanted.
- **#22** Footer link to both pages on every page.
- **#23** Consent tick-box on the signup/consent flow: "I agree to the ToS and Privacy Policy".
- **#24** Set the URLs in the Discord Developer Portal (General Information → Terms of Service URL + Privacy Policy URL). Optionally surface via ansible group_vars.

## Privacy policy — content outline
- Data collected: email, Discord ID + refresh token, VEKN ID + profile, tournament history, locations, request logs.
- Purposes: auth, tournament management, Linked Roles via Discord, result submission to VEKN.
- Third parties data is shared with: Discord, vekn.net, Gmail SMTP (`MAIL_*`), GitHub (TWDA pull requests).
- Retention: tied to account lifetime; logs rotated per journald defaults.
- GDPR rights: access / export / deletion / rectification + how to request.
- Contact: lionel.panhaleux@gmail.com

## Terms of service — content outline
- Community / non-commercial service.
- Acceptable use (no abuse, no impersonation; organizers responsible for their tournaments' accuracy).
- Code of conduct (point to VEKN's official CoC).
- Account termination clause.
- "No warranty" disclaimer.
- Governing law: France.
- Change process (notify via email + in-app banner).

## After pages are live
Optionally set in `ansible/inventories/{beta,prod}/group_vars/all.yml` if we ever want them as env vars — currently they only need to be set in the Discord portal:
- Terms of Service URL: `https://archon.{domain}/legal/terms`
- Privacy Policy URL: `https://archon.{domain}/legal/privacy`
