# Community page restructure

Doc-impact: `wiki/architecture.md` (community-links model and placement rules),
`wiki/access.md` (moderation scope keyed to link country), `wiki/hazards.md`
(og:title fetch guard), plus the in-app help guides (`PlayerGuide` `pg_community`
section, `OrganizerGuide` curation section — code, listed here because the ask
names them).

## Why

The current page derives its two sections from a hardcoded platform partition
(`CommunityTab.svelte` `SOCIAL_TYPES`/`CONTENT_TYPES`, duplicated in
`ProfileView.svelte`), but platform does not determine function: an NC's
Instagram is an announcements channel, a player's Instagram is content. The
signal that *does* determine function already exists — the moderation pins.
Placement follows pins; platform only drives icon and label.

## Model and engine

- `CommunityLink` gains an optional `country`, defaulting to the owner's at
  creation and owner-settable (the Brazilian Discord run from Portugal).
  Moderation (`moderate_link`, `promote_link_national`) keys off the **link's**
  country, not the owner's — engine change in `engine/src/permissions.rs`,
  mirrored in the Python/TS wrappers and the moderation route, which addresses
  links by owner uid + url.
- New `CommunityLinkType` values: `spotify`, `x`, `bluesky` (backend enum +
  `types.ts` + pill label/color/icon maps in `CommunityLinkPills.svelte`).
- Content-type links require ≥1 language at input: enforced in the editor
  (picker pre-selected to the owner's site language) and in `PATCH /auth/me`.
  Legacy language-less links keep the current display semantics (shown under
  every filter) and decay; no data back-fill.
- Centralize the social/content type partition (and the platform→media-kind
  mapping below) in one shared module; delete the two duplicated sets.

## Page structure

Placement rules: global pin ⇒ Global card; national pin ⇒ that country's card,
whatever the platform; unpinned social types ⇒ their country's card (venues
list); unpinned content types ⇒ the content pool.

Order on the page:

1. **Global** card — expanded (small, IC-curated).
2. **Your country** card — expanded: nationally pinned channels first, then
   social groups, then that country's officials (contact detail stays behind
   sign-in as today).
3. **Country search** (combobox) replacing the full country list — picking a
   country materializes its card. Travelers search; nobody scans 60 cards.
4. **Content pool** — flat list filtered by a language **multiselect**
   (endonym labels from `languages.ts`, defaulting to the reader's site
   language, replacing the pill row) and a **media-kind facet** (video /
   podcast / text / social), derived from platform (youtube, twitch → video;
   spotify → podcast; blog, website → text; instagram, x, bluesky, facebook,
   reddit → social). Known lossy case: YouTube podcasts — acceptable; add a
   real field only if it bites.

Sponsor mode (`?sponsor=1`) must keep working: it hides the link sections and
narrows officials to the visitor's country.

## Add/edit

One shared link-editor modal component, two mounts: the community page (primary
— "Add your link" button where the link will appear) and the profile page
(compact "your links" summary opening the same modal). Same `PATCH /auth/me`
underneath. The modal:

- carries type, url, label, languages, country;
- offers the target's **og:title as an editable label suggestion** — fetched
  once, server-side, at registration; never re-fetched; the fetch must refuse
  private/internal addresses, cap size and time out (hazard to record). No
  og:image — hostile image swaps after approval, hosting/moderation liability,
  and uniform pills read better at scale;
- warns before saving a URL edit on a pinned link that the pin will drop
  (moderation is re-applied by exact URL match — existing recorded decision,
  unchanged).

Moderation stays the three inline icons; no new moderation surface.

## Cold start and empty states

An NC viewing their own empty country card gets a targeted prompt ("nothing
pinned for France yet — pin community links or add official channels") instead
of the generic member banner. Getting NCs to each pin a few links is the actual
launch of this page.

## Help

- Player Guide `pg_community` section: how to add links, what languages and
  country on a link mean, where the link will appear.
- Organizer Guide: how NCs/ICs curate — hide, pin national, pin global, and
  what each placement does. New paraglide messages are a translation unit
  (`wiki/i18n.md`).

## Explicitly out

- og:image previews (decided against, see Add/edit above).
- Physical meetup venues / playgroup locations — a later idea; the social
  channel is the entry point for now.
- IC editing other owners' link fields — hide + contact the owner suffices;
  revisit only if that proves insufficient.
