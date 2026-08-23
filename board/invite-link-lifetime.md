> Elaborated context for a line in `BOARD.md`. Deleted with the line.

# Invite link lifetime and the way back

**Doc-impact:** `wiki/access.md` — the magic-link row in the authentication table
states per-purpose lifetimes and names password reset as the invited member's
recovery. No domain page: the domain did not change, only our own UX.

## What is wrong

`MAGIC_LINK_EXPIRE_MINUTES = 15` in `backend/src/routes/auth/magic_link.py` is
shared by signup, password reset and invite. Fifteen minutes is a defensible
reset lifetime and an indefensible invite lifetime: the recipient did not ask for
the email and has no reason to be watching their inbox when an organizer creates
their member record.

Two call sites reach `send_invite_email` — creating a member from the users route
and creating one for an offline player mid-tournament — so the lifetime belongs in
that function, not raised on the shared constant.

## Traps

- The email body hardcodes **"This link will expire in 15 minutes"** in two places
  in `email_service.py`, plain-text and HTML. A longer invite with an unchanged
  template ships a lying email.
- There is a **second, tighter clock**: `SET_PASSWORD_EXPIRE_MINUTES = 10`, the
  window between clicking the link and submitting a password. It has its own error
  path in the frontend. Judge whether it contributes to the reported symptom before
  deciding to leave it alone.

## The recovery path already exists, invisibly

A member created with an email address gets a user record carrying
`contact_email` and no email auth method. In `set_password`, the `reset` purpose
handles exactly that case: no existing email auth, but a user found by contact
address, so it *creates* the email login. Password reset on the login page
therefore already mints an invited member a fresh working link.

Nobody would guess this. The expired-link page says only "The link may have
expired or already been used" and offers one button back to login.

**A true one-click resend button on that page is not buildable.** An expired
transient token is gone from storage, so the server cannot recover which address
to resend to. The affordance is "enter your email and we will send a fresh link" —
which is the reset form we already have, reached with wording that makes sense to
someone who has never had a password.
