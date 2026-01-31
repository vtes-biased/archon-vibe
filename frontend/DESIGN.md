# Frontend Design Guidelines

## Color Palette

VTES / Vampire: the Masquerade inspired. Gothic horror, pale and muted, with dark mode as primary.

| Name      | Light Mode        | Dark Mode         | Usage                        |
|-----------|-------------------|-------------------|------------------------------|
| `crimson` | `#8B0000`         | `#DC143C`         | Primary accent, CTAs         |
| `bone`    | `#F5F0E6`         | `#2A2520`         | Backgrounds                  |
| `dusk`    | `#E8E0D5`         | `#1C1A1E`         | Cards, surfaces              |
| `ash`     | `#6B6560`         | `#A09890`         | Text, borders                |
| `mist`    | `#9B9590`         | `#605850`         | Muted text, disabled states  |

Role badges use distinct colors but remain muted/dusty to fit the gothic aesthetic.

## Country Display

Show country flag emoji with country name. Use `getCountryFlag(isoCode)` from `lib/geonames.ts`.

- **Display text**: Flag before name: `🇫🇷 France`
- **In `<select>` options**: Name before flag: `France 🇫🇷` (enables browser type-ahead)

## Material Design

- Clean card-based layouts with subtle shadows
- Crisp typography, good contrast
- Consistent spacing (4px grid)
- Rounded corners (4-8px)

## Auto-Save Pattern

**No explicit save buttons.** Changes save/sync immediately on input.

- Provide clear feedback (loading states, success indicators)
- Always allow undo/cancel/revert
- Exception: destructive or batch actions may require confirmation

## Mobile First

Design for touch devices first, then enhance for desktop.

- **Touch targets**: Minimum 44x44px
- **No hover-only interactions**: Always have tap/click equivalent
- **Drag and drop**: Must not conflict with scrolling; provide alternative (buttons/menus)
- **Navigation**: Bottom nav or hamburger, not top-heavy headers
- **Forms**: Large inputs, avoid complex multi-column layouts on mobile
- **Containers**: Full-width on mobile, max-width on larger screens

## Modals

### Click Propagation

Modals must prevent click events from bubbling to parent elements. Always add `stopPropagation` to:
- Modal overlay (backdrop)
- Modal content container
- Forms inside the modal

```svelte
<div class="fixed inset-0 ..." onclick={(e) => e.stopPropagation()}>
  <div class="modal-content" onclick={(e) => e.stopPropagation()}>
    <form onclick={(e) => e.stopPropagation()}>
```

Without this, clicking inside a modal (e.g., on a text input) can trigger parent handlers like collapsing an expanded list item.

### Edit Modals vs Inline Actions

For objects with multiple actions (edit fields + lift + delete), prefer a dedicated edit modal over inline action buttons. Benefits:
- More space for editable fields
- Cleaner list UI (single edit button per item)
- Actions grouped logically in one place
- Easier to show/hide actions based on object state

### Captured State

When opening a modal from a list item, capture the item's data at open time:

```typescript
let editingItem = $state<Item | null>(null);

function openModal(item: Item) {
  editingItem = item;  // Capture snapshot
  showModal = true;
}
```

This prevents SSE sync updates from changing the modal's data mid-edit.

## Context-Specific Options

Scope form options by context. Example: sanctions from user list only allow PROBATION/SUSPENSION (global sanctions), while tournament view will allow all types (CAUTION, WARNING, DQ, etc.).
