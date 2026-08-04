import type { Role } from '$lib/types';
import * as m from '$lib/paraglide/messages.js';

// Gothic-inspired muted role colors - see DESIGN.md
// Uses semantic badge-* classes from app.css for light/dark mode support
const ROLE_CLASSES: Record<Role, string> = {
  // Gothic-jewel families: governance = crimson · judiciary = amethyst · playtest = blue · ethics = fuchsia · dev = slate
  IC: 'badge-crimson',
  NC: 'badge-crimson',
  Prince: 'bg-accent-soft/60 text-link-soft', // crimson uses custom palette
  Ethics: 'badge-fuchsia',
  PTC: 'badge-blue',
  PT: 'badge-blue',
  Rulemonger: 'badge-amethyst',
  Judge: 'badge-amethyst',
  Judgekin: 'badge-amethyst',
  DEV: 'badge-slate',
};

export function getRoleClasses(role: Role): string {
  return ROLE_CLASSES[role];
}

// Roles render as their stored value except where the two diverge. The stored
// value "Judgekin" is DISPLAYED AS "Sheriff": renaming the value would mean a
// data migration during a live parallel run, for a badge.
const ROLE_LABELS: Partial<Record<Role, () => string>> = {
  Judgekin: m.role_judgekin,
};

/** The user-facing name of a role — never the raw value. */
export function getRoleLabel(role: Role): string {
  return ROLE_LABELS[role]?.() ?? role;
}

/**
 * Expand filter roles to include related roles.
 * Judge filter includes Judgekin and Rulemonger.
 */
export function expandRolesForFilter(roles: Role[]): Role[] {
  const expanded = new Set(roles);
  if (expanded.has('Judge')) {
    expanded.add('Judgekin');
    expanded.add('Rulemonger');
  }
  return Array.from(expanded);
}
