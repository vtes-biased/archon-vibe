Doc-impact: `wiki/access.md` (login-methods table: removal, last-method refusal, which Discord the profile shows), `wiki/hazards.md` (last-method removal reopens claim and email matching).

**Why the last method must be refused.** A VEKN record with no auth method reads as unclaimed: `POST /vekn/claim` accepts it, and `get_user_by_email` starts matching its unverified contact email at signup and Discord login. Removing a member's last login hands their account to whoever claims the id or typed their address into a profile. The refusal is server-side, not just a hidden button.

**Two Discord fields drift today.** `discord_id` follows the last Discord sign-in; `contact_discord` is only filled when empty, and a merge takes the dropped account's values first. A member with two Discord logins (merged accounts) ends up with one account's username linking to the other's profile. Sign-in should set both together; removing the Discord that `discord_id` points at re-points both at a remaining Discord login, or clears them.

**Discord Linked Roles.** The role token is per user, not per Discord login; removing the Discord it was minted for must revoke or drop it rather than leave it pushing roles to a Discord account no longer linked.

**Passkeys.** `/auth/me` returns auth methods as type + identifier only; for a passkey that is a credential id, which a member cannot tell apart. The removal list needs something recognisable (creation date, last used, authenticator name if stored).

Out of scope: removing an email/password login (not asked).
