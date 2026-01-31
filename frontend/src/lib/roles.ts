import type { Role } from '$lib/types';

export interface RoleConfig {
  bg: string;
  text: string;
}

// Gothic-inspired muted role colors - see DESIGN.md
export const ROLE_COLORS: Record<Role, RoleConfig> = {
  IC: {
    bg: 'bg-purple-900/60',
    text: 'text-purple-200',
  },
  NC: {
    bg: 'bg-blue-900/60',
    text: 'text-blue-200',
  },
  Prince: {
    bg: 'bg-crimson-800/60',
    text: 'text-crimson-200',
  },
  Ethics: {
    bg: 'bg-emerald-900/60',
    text: 'text-emerald-200',
  },
  PTC: {
    bg: 'bg-cyan-900/60',
    text: 'text-cyan-200',
  },
  PT: {
    bg: 'bg-teal-900/60',
    text: 'text-teal-200',
  },
  Rulemonger: {
    bg: 'bg-amber-900/60',
    text: 'text-amber-200',
  },
  Judge: {
    bg: 'bg-indigo-900/60',
    text: 'text-indigo-200',
  },
  Judgekin: {
    bg: 'bg-slate-800/60',
    text: 'text-slate-200',
  },
  DEV: {
    bg: 'bg-lime-900/60',
    text: 'text-lime-200',
  },
};

export function getRoleClasses(role: Role): string {
  const config = ROLE_COLORS[role];
  return `${config.bg} ${config.text}`;
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
