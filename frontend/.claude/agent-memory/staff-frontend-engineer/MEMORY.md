# Staff Frontend Engineer Memory

## Established Surface Patterns
- **Data surfaces**: `bg-ash-900/50 rounded-lg p-4` is the standard container for tables, lists, score areas
- **Card containers**: `bg-dusk-950 rounded-lg shadow border border-ash-800` for outer card shells
- **Dividers**: `divide-y divide-ash-800` for list rows; `border-t border-ash-700` for table rows inside surfaces
- **Table headers**: Mostly `text-ash-500 text-xs` (tournament pages), league uses `bg-ash-900 text-ash-300 border-b border-ash-700`

## Color Scale Inversion
- All custom palette classes (dusk, ash, bone, crimson) auto-invert via CSS variables
- Standard Tailwind colors (emerald, amber, red) do NOT invert -- use semantic classes (badge-*, btn-*, banner-*)
- Light mode: dusk-950 becomes #FFFFFF, ash-900 becomes #E8E6E4, ash-800 becomes #D4D0CC

## Key Files
- Design system: `/Users/lionelpanhaleux/dev/perso/archon-cursor/frontend/DESIGN.md`
- CSS/theme: `/Users/lionelpanhaleux/dev/perso/archon-cursor/frontend/src/app.css`
- Tournament page: `/Users/lionelpanhaleux/dev/perso/archon-cursor/frontend/src/routes/tournaments/[uid]/+page.svelte`
- PlayersTab: `/Users/lionelpanhaleux/dev/perso/archon-cursor/frontend/src/routes/tournaments/[uid]/PlayersTab.svelte`
- RoundsTab: `/Users/lionelpanhaleux/dev/perso/archon-cursor/frontend/src/routes/tournaments/[uid]/RoundsTab.svelte`
- FinalsTab: `/Users/lionelpanhaleux/dev/perso/archon-cursor/frontend/src/routes/tournaments/[uid]/FinalsTab.svelte`

## Reviewed Issues
- PlayersTab lacked bg-ash-900/50 container, header border, and had weak row separators (fixed 2026-02-17)
