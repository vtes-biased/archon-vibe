import type { Role } from '$lib/types';
import type { BadgeTone } from '$lib/components/Badge.svelte';

// A role is an IDENTITY badge whose hue IS the label — the colour groups the role family, it does
// not rank or warn. Gothic-jewel families: governance = crimson · judiciary = amethyst · playtest = blue · ethics = fuchsia · dev = slate.
const ROLE_TONES: Record<Role, BadgeTone> = {
  IC: 'crimson',
  NC: 'crimson',
  Prince: 'accent', // crimson uses the accent palette, not the badge one
  Ethics: 'fuchsia',
  PTC: 'blue',
  PT: 'blue',
  Rulemonger: 'amethyst',
  Judge: 'amethyst',
  Sheriff: 'amethyst',
  DEV: 'slate',
};

export function getRoleTone(role: Role): BadgeTone {
  return ROLE_TONES[role];
}

/** Judge filter includes Sheriff and Rulemonger. */
export function expandRolesForFilter(roles: Role[]): Role[] {
  const expanded = new Set(roles);
  if (expanded.has('Judge')) {
    expanded.add('Sheriff');
    expanded.add('Rulemonger');
  }
  return Array.from(expanded);
}
