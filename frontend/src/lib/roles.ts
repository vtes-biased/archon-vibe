import type { Role } from '$lib/types';

// Gothic-inspired muted role colors - see DESIGN.md
// Uses semantic badge-* classes from app.css for light/dark mode support
const ROLE_CLASSES: Record<Role, string> = {
  IC: 'badge-purple',
  NC: 'badge-blue',
  Prince: 'bg-crimson-800/60 text-crimson-200', // crimson uses custom palette
  Ethics: 'badge-emerald',
  PTC: 'badge-cyan',
  PT: 'badge-teal',
  Rulemonger: 'badge-amber',
  Judge: 'badge-indigo',
  Judgekin: 'badge-slate',
  DEV: 'badge-lime',
};

export function getRoleClasses(role: Role): string {
  return ROLE_CLASSES[role];
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
