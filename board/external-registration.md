Doc-impact: `wiki/product.md` — the paragraph "An Archon registration is not always
the entry" states the decision this line reverses and must be rewritten, not
amended around: the app no longer records a sign-up alongside the ticket shop, it
sends the player there and takes the roster back as a file. `wiki/tournaments.md` —
the `registration_url` row in the config table, which today says the link only
*surfaces* the CSV import, and the "Only a self-service sign-up waitlists"
paragraph, since with the button gone the import is the sole path that can
waitlist. Not `wiki/domain/tournament-rules.md`: nothing in the VEKN rules changed.
Not `wiki/public-api.md`: the refusal rides the existing `Register` rejection shape.

## The decision this reverses

`wiki/product.md` records that a player who registers in the app on an event with a
`registration_url` is *told* it does not book their seat and sent to the link, the
app recording them for the organizer anyway. The code implements that faithfully:
`PlayerView.svelte` renders the Register button and the external-registration
notice together. The owner's model of the feature is the opposite one — the link
replaces Archon's sign-up entirely — and that is the model to ship.

## Why the engine, not the button

There are three self-service registration paths, not one: the web Register button,
the Discord bot's `/register`, and the API. Hiding the button leaves the other two
open and desynchronised. The engine already refuses `Register` on an empty
`vekn_id`; a non-empty `registration_url` becomes a refusal of the same shape, and
every surface inherits it. The player view then shows the link because the action
is gone, not because a component chose to hide it.

## Decided at intake

**Self-unregister goes with it.** A seat bought at a ticket shop is cancelled at
the source, so a player on such an event sees their status and the link, not an
Unregister button. The organizer can still remove them.

**Nothing else moves.** Walk-in check-in stays open and still enrols — that is how
a latecomer, or a CSV row the import could not match, gets in. The import resolves
rows to real accounts, so an imported player is an ordinary registered player: they
see themselves on the roster and upload a decklist as before.

## Strings this touches

`tfield_registration_url_desc` (rewritten once already this cycle and wrong again
under this line), `tournament_external_registration_notice`, the button label
`tournament_external_registration_btn`, the wizard tip
`tournament_wiz_tip_reglink_b`, and whatever the bot answers `/register` with. All
five catalogs — en, es, fr, it, pt.
