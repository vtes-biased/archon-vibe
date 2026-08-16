import type { User, Role } from '$lib/types';
import { expandRolesForFilter } from './roles';
import { normalizeSearch } from './utils';

export interface DisplayFilters {
  country?: string;
  roles?: Role[];
  nameSearch?: string;
  hasPastSanctions?: boolean;
  currentlySanctioned?: boolean;
  // Official-only sponsor-management filters (coopted_by / vekn_id), applied client-side in loadUsers
  // — deliberately NOT in matchesCurrentFilters, which stays a coarse refresh gate.
  sponsor?: 'mine' | 'none';
  noVekn?: boolean;
}

interface PaginationContext {
  currentPage: number;
  pageSize: number;
  firstVisibleName?: string;
  lastVisibleName?: string;
}

class DisplayContext {
  private filters: DisplayFilters = {};
  private pagination: PaginationContext = {
    currentPage: 1,
    pageSize: 250,
  };

  setFilters(
    country?: string,
    roles?: Role[],
    nameSearch?: string,
    hasPastSanctions?: boolean,
    currentlySanctioned?: boolean,
    sponsor?: 'mine' | 'none',
    noVekn?: boolean
  ): void {
    this.filters = {
      country: country && country !== 'all' ? country : undefined,
      roles: roles && roles.length > 0 ? [...roles] : undefined, // Convert Svelte proxy
      nameSearch: nameSearch && nameSearch.trim() ? normalizeSearch(nameSearch.trim()) : undefined,
      hasPastSanctions: hasPastSanctions || undefined,
      currentlySanctioned: currentlySanctioned || undefined,
      sponsor: sponsor || undefined,
      noVekn: noVekn || undefined,
    };
    // Boundaries aren't reset here — they'll be updated by loadUsers(). Keeping stale boundaries
    // briefly is fine, better than triggering excessive refreshes.
    this.pagination.currentPage = 1;
  }

  setPagination(currentPage: number, pageSize: number, visibleUsers: User[]): void {
    this.pagination = {
      currentPage,
      pageSize,
      firstVisibleName: visibleUsers[0]?.name,
      lastVisibleName: visibleUsers[visibleUsers.length - 1]?.name,
    };
  }

  getFilters(): DisplayFilters {
    return { ...this.filters };
  }

  matchesCurrentFilters(user: User): boolean {
    const { country, roles, nameSearch } = this.filters;

    if (country && user.country !== country) {
      return false;
    }

    if (roles && roles.length > 0) {
      const plainRoles = [...roles]; // Convert potential Svelte proxy to plain array
      const expandedRoles = expandRolesForFilter(plainRoles);
      const hasMatchingRole = expandedRoles.some(role => user.roles.includes(role));
      if (!hasMatchingRole) {
        return false;
      }
    }

    if (nameSearch) {
      const nameNorm = normalizeSearch(user.name);
      const words = nameNorm.split(/\s+/);
      const matchesName = words.some(word => word.startsWith(nameSearch));
      if (!matchesName) {
        return false;
      }
    }

    // Always refresh on page 1 (any matching user could affect the display).
    if (this.pagination.currentPage === 1) {
      return true;
    }

    if (!this.pagination.firstVisibleName || !this.pagination.lastVisibleName) {
      return true;
    }

    const userName = user.name;
    const { firstVisibleName, lastVisibleName } = this.pagination;

    return (
      userName.localeCompare(firstVisibleName) >= 0 &&
      userName.localeCompare(lastVisibleName) <= 0
    );
  }
}

export const displayContext = new DisplayContext();

