import type { Role } from '$lib/types';
import type { BadgeTone } from '$lib/components/Badge.svelte';
import * as m from '$lib/paraglide/messages.js';

// A role is an IDENTITY badge whose hue IS the label — the colour groups the
// role family, it does not rank or warn. Gothic-jewel families: governance =
// crimson · judiciary = amethyst · playtest = blue · ethics = fuchsia · dev = slate.
const ROLE_TONES: Record<Role, BadgeTone> = {
  IC: 'crimson',
  NC: 'crimson',
  Prince: 'accent', // crimson uses the accent palette, not the badge one
  Ethics: 'fuchsia',
  PTC: 'blue',
  PT: 'blue',
  Rulemonger: 'amethyst',
  Judge: 'amethyst',
  Judgekin: 'amethyst',
  DEV: 'slate',
};

export function getRoleTone(role: Role): BadgeTone {
  return ROLE_TONES[role];
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
