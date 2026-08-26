# Organizer guide restructure

Doc-impact: none — this reorders and rewrites help copy (`og_*` messages rendered
by `frontend/src/lib/components/help/OrganizerGuide.svelte`); no domain fact or
behavior changes, so no wiki page moves.

## Target order (owner's outline, 2026-08-26)

1. **The common case first: a small real-life tournament.** Prior registration is
   optional; check in and take payment at the gate; seat and play. Walk the whole
   run-of-show in order:
   - create the event (timer optional)
   - check-in at the gate, payment status
   - the classic problem: adding a late arrival to the first round
   - seat rounds, record scores
   - sanctions, score overrides (Life Boon)
   - toss for finals and the seating dance
   - distribute promos: recording distribution + the raffle
   - **offline mode as the first option branch** — if the venue may lack
     connectivity, decide before the event and activate offline mode.
2. **Advanced topics** (pre-registration and big events):
   - pre-registration to size a bigger event, get payment upfront, collect
     decklists in advance (advise VDB QR-code scanning — faster than pasting a
     list from a message)
   - third-party online payment combined with app registration: the CSV import
     of paid registrations (Tools → CSV import; matches VEKN id first, email as
     last resort) and how it coexists with in-app registration and decklist
     uploads
   - big-event features: QR-code self-check-in, on-the-spot decklist upload via
     VDB QR, configuring rooms, live announcements.
3. **Online events**, their own section:
   - advise the official VTES Discord (bot already installed); guide bot
     installation for another server
   - sync events: one round after the other, reset check-in between rounds
   - async / parallel rounds (JOL-style) at the end of the online section.
4. **Open rounds and self-organized rounds close the guide** — an option in both
   worlds (long online events people join whenever; real-life long-running
   open-round events with self-organized games).

## Notes

- Five locales (en, fr, es, pt, it) of `og_*` keys — the reorder fans out across
  all of them; consider the `mass-edit` agent for the mechanical per-locale pass
  once the English target text is settled.
- The FAQ section survives the restructure.
- French check-in vocabulary trap: see `wiki/glossary.md` note on `og_*` wording.
