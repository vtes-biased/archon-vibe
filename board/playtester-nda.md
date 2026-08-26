# Playtester NDA click-to-sign

Doc-impact: `wiki/access.md` (an NDA-record capability row for PTC + IC, and the
PT-grant precondition as a resolver beside `ROLE_APPOINTMENTS`), `wiki/architecture.md`
(the NDA record: storage, signing flow, sealed-PDF generation, endpoints),
`wiki/sync.md` (the NDA file and status excluded from broadcast projections, like
`calendar_token`), `wiki/product.md` (one line under member management).

## Decision record

Mechanism decided at intake (owner, 2026-08-26): in-app click-to-sign, not the
PDF print–sign–scan–upload loop and not a self-hosted signing service
(Docuseal/Documenso considered). Rationale: playtesters must be Archon members
anyway, and a verified login is stronger signer identity than a signing service's
emailed link. Legal basis: the template is governed by England & Wales law, which
accepts simple electronic signatures for NDAs (Law Commission 2019); eIDAS and
ESIGN concur. The evidentiary record is the point: document version + hash,
signer uid, typed name, timestamp, sealed into a PDF with an audit page.

**BCP has not yet agreed.** The owner demos the feature on beta to Hugh
(BCP CEO). The NDA text must therefore be *versioned* — his feedback will change
the wording, and each signature must pin the exact version + hash it was given.
His countersignature becomes a pre-embedded signature image or offer/acceptance
wording — his call, not ours; leave space for either. Feedback after the demo
returns through /intake.

No feature flag for production: the flow is PTC-triggered and IC controls who
holds PTC, so with no PTC appointed in production the feature is inert until
BCP's yes.

## Scope notes

- Source text: transcribe from `BCP_NDA_Agreement.pdf`, untracked at repo root —
  owner-provided. Do not commit the PDF; delete it once transcribed.
- Prefillable from Archon: name, email, date. Address and phone were blanks for
  handwriting in the paper template — whether the signing form collects them is
  BCP's evidence call; collect them on the form for now, stored only in the
  sealed record.
- Legal text stays English-only; no i18n.
- Email copy to signer uses the existing `email_service`. A copy to BCP is
  post-approval configuration, not part of this line.
- Grandfathering: ship-time check for existing PT holders (beta and prod); they
  keep the role and the member record shows missing-NDA for the PTC to backfill
  via the scan-upload fallback. The engine gate applies to *grants*, not holds.

## Hazards

- The signed record carries name, address, phone, signature intent — neither the
  file nor any NDA-status field on User may reach broadcast projections
  (`wiki/sync.md` access levels; the `calendar_token` exclusion is the pattern).
- Lifecycle: the record dies with `delete_member`; it **persists after PT role
  removal** (that is its purpose); merge must carry the record to the surviving
  account (account surgery is tested — extend the invariant, not a new suite).
- Role writes have two out-of-band watchers (Discord Linked Roles push, resync
  fingerprint) — the PT grant must keep going through the users route
  (`wiki/access.md`).
