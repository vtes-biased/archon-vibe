> Elaborated context for one line in `BOARD.md`. Deleted with the line.

# vekn.net refuses members created without a city

**Doc-impact:** `wiki/vekn.md` — what the registry requires on member creation,
and what we send when a field is empty.

## Evidence (production, read 2026-08-23)

`vekn_push` logs `Create member failed: Required data is empty (code: 400)` for
three members. The stored rows:

| vekn | name | country | city | state | stuck since |
|---|---|---|---|---|---|
| 1000023 | Aron Hilmarsson Björk | SE | *(empty)* | *(empty)* | 2026-08-15 17:49 |
| 1000030 | Johan Thörnqvist | SE | *(empty)* | *(empty)* | 2026-08-15 17:49 |
| 1000036 | Gian Carlo Perfetti | SE | *(empty)* | *(empty)* | 2026-08-23 09:55 |

The hourly batch has been retrying and failing for **eight days**. The only
symptom is log noise: `push_member` returns False, `vekn_synced` stays false, the
request that created the member already returned 201. The sponsor has no reason
to think anything failed.

## Which field

`country` is populated (`SE`) on all three, so the first hypothesis — empty
country — is **wrong**. `create_member` sends exactly `veknid, firstname,
lastname, email, country, state, city` (`vekn_api.py:317`). Name, email and
country are all populated; `city` and `state` are the only empty ones. By
elimination the refused field is city and/or state.

Control if the exact field matters: member 1000015 got *past* validation (it
failed with `PLAYER_ALREADY_EXISTS`), so its stored city/state discriminate.

## Shelf life

`wiki/vekn.md:515` retires member-creation push at decommission stage 2, gated on
vekn.net registration closing. This code is scheduled to die — cap the
investment accordingly, but it is dropping real members today.

## Repair

The three stuck members get a city: the capital of their country. They are all
`SE`, so Stockholm. Once stored, the hourly batch picks them up on its own —
`vekn_synced` is still false, so no manual push is needed.
