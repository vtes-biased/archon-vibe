# Profile tabs

Doc-impact: `wiki/design.md` — the profile's tab structure; the tab-label rule
lifted out of *The redesign pass* to govern every tab row; one app-wide fold
grammar, with the four patterns it replaces named.

## Where the size comes from

Measured on `/profile` for a top player (4 rating categories, 5 wins, 6
decklists): about 2,400px at 390px wide, roughly three screens. Nine stacked
sections, of which the record — ratings, wins, decklists — is about 950px, and
that record is *duplicated*: the same two components already render on the public
`/users/[uid]` page (`frontend/src/routes/profile/+page.svelte:249` says so in a
comment).

Four structures were drawn to scale and compared on one canvas:
<https://claude.ai/code/artifact/3fbeda74-8c1c-47c1-9656-cfbe5f1e8a10>

Owner picked page tabs. The others, and what killed each: one unified fold
grammar was shortest but turned the page into a directory of closed doors;
tabs inside the record block cut the most length but left the account stack
untouched and nested a strip inside a page that may want its own; truncating
each list to its top three added a third disclosure pattern and saved least.

## What to build

Identity stays above the strip on every tab — it is the page's subject, not tab
content. Below it:

| Surface | Tabs |
|---|---|
| `/profile` | Profile · Play record · Account |
| `/users/[uid]` | Profile · Play record |

- **Profile** — contact info, community links; on the public page also the
  sponsor note and any manager-only controls the viewer's access grants.
- **Play record** — `PlayerRatings`, then `PlayerRecord`'s wins, the
  undocumented-decklist nudge, and the decklists.
- **Account** — linked accounts, authorized apps, settings, developer,
  administration, data.

Reuse the console's tab anatomy verbatim
(`frontend/src/routes/tournaments/[uid]/+page.svelte:964-979`): icon always,
`<span class={active ? '' : 'hidden sm:inline'}>` on the label, `aria-label` the
full label at every width, `aria-current="page"` on the active one. Three tabs at
360px leave roughly 65px a label — `Historique de jeu` and `Histórico de partidas`
do not fit, so the active-only rule is load-bearing here, not decoration.

## Two constraints that bind

- **Auditability.** `wiki/tournaments.md` promises the profile lists the wins
  behind the count "so the number is auditable rather than asserted". The count
  and its evidence stay together on the Play record tab.
- **The nudge must keep nudging.** The undocumented-decklist block pairs with the
  nudge on the tournament page. Tabs put it one gesture deep — the accepted cost
  of this structure — so it sits beside the wins it names, never below the
  decklists.

## The fold grammar

Four hand-rolled chevron patterns exist for one gesture:

| Pattern | Where |
|---|---|
| `FoldableSection` — muted box, chevron right/down | `TournamentFields.svelte`, `SetupTab.svelte` |
| Uppercase header + rotating chevron | `AuthorizedApps.svelte`, `DeveloperSection.svelte`, `AdminSection.svelte` |
| Card, count in header, rotating chevron | `PlayerRatings.svelte` |
| `DeckAccordion` | `PlayerRecord.svelte` |

`wiki/design.md` today calls `FoldableSection` "the one shell every config section
uses" inside the console section, which is both narrower than the truth and wider
than the code. Owner's ruling: state it as **app-wide** grammar. Record the rule
and name the drift honestly — this line does not fix the drift, and the console
redesign pass already parked on that page is where the cleanup happens.
