/**
 * Display context tracker for filter-aware sync updates.
 * 
 * Maintains awareness of current display filters, pagination, and visible range
 * so we can determine if incoming sync updates are relevant to the current view.
 */

import type { User, Role } from '$lib/types';
import { expandRolesForFilter } from './roles';

export interface DisplayFilters {
  country?: string;
  roles?: Role[];
  nameSearch?: string;
  hasPastSanctions?: boolean;
  currentlySanctioned?: boolean;
}

interface PaginationContext {
  currentPage: number;
  pageSize: number;
  // Track the name boundaries of currently displayed users
  // Users are sorted alphabetically by name
  firstVisibleName?: string;
  lastVisibleName?: string;
}

class DisplayContext {
  private filters: DisplayFilters = {};
  private pagination: PaginationContext = {
    currentPage: 1,
    pageSize: 250,
  };

  /**
   * Update the current display filters.
   */
  setFilters(
    country?: string,
    roles?: Role[],
    nameSearch?: string,
    hasPastSanctions?: boolean,
    currentlySanctioned?: boolean
  ): void {
    this.filters = {
      country: country && country !== 'all' ? country : undefined,
      roles: roles && roles.length > 0 ? [...roles] : undefined, // Convert Svelte proxy
      nameSearch: nameSearch && nameSearch.trim() ? nameSearch.trim().toLowerCase() : undefined,
      hasPastSanctions: hasPastSanctions || undefined,
      currentlySanctioned: currentlySanctioned || undefined,
    };
    // Reset page to 1 when filters change
    // Note: We don't reset boundaries here - they'll be updated by loadUsers()
    // Keeping stale boundaries briefly is fine, better than triggering excessive refreshes
    this.pagination.currentPage = 1;
  }

  /**
   * Update pagination context with currently visible users.
   */
  setPagination(currentPage: number, pageSize: number, visibleUsers: User[]): void {
    this.pagination = {
      currentPage,
      pageSize,
      firstVisibleName: visibleUsers[0]?.name,
      lastVisibleName: visibleUsers[visibleUsers.length - 1]?.name,
    };
  }

  /**
   * Get the current display filters.
   */
  getFilters(): DisplayFilters {
    return { ...this.filters };
  }

  /**
   * Check if a user matches the current display context (filters + pagination).
   *
   * Returns true if the user update should trigger a display refresh.
   * Takes into account both filter criteria and pagination/ordering.
   */
  matchesCurrentFilters(user: User): boolean {
    const { country, roles, nameSearch } = this.filters;

    // First check filter criteria
    // Check country filter
    if (country && user.country !== country) {
      return false;
    }

    // Check roles filter (user must have at least one of the selected roles)
    // Expand roles (e.g., Judge includes Judgekin)
    if (roles && roles.length > 0) {
      const plainRoles = [...roles]; // Convert potential Svelte proxy to plain array
      const expandedRoles = expandRolesForFilter(plainRoles);
      const hasMatchingRole = expandedRoles.some(role => user.roles.includes(role));
      if (!hasMatchingRole) {
        return false;
      }
    }

    // Check name search filter (prefix match on any word)
    if (nameSearch) {
      const nameLower = user.name.toLowerCase();
      const words = nameLower.split(/\s+/);
      const matchesName = words.some(word => word.startsWith(nameSearch));
      if (!matchesName) {
        return false;
      }
    }

    // User matches filter criteria
    // Always refresh on page 1 (any matching user could affect the display)
    if (this.pagination.currentPage === 1) {
      return true;
    }

    // On later pages: only skip refresh if we have clear boundaries and user is outside them
    if (!this.pagination.firstVisibleName || !this.pagination.lastVisibleName) {
      return true;
    }

    // Users are sorted alphabetically by name
    const userName = user.name;
    const { firstVisibleName, lastVisibleName } = this.pagination;

    // Only refresh if user falls within current page boundaries
    return (
      userName.localeCompare(firstVisibleName) >= 0 &&
      userName.localeCompare(lastVisibleName) <= 0
    );
  }

  /**
   * Check if any filters are currently active.
   */
  hasActiveFilters(): boolean {
    return !!(
      this.filters.country ||
      (this.filters.roles && this.filters.roles.length > 0) ||
      this.filters.nameSearch ||
      this.filters.hasPastSanctions ||
      this.filters.currentlySanctioned
    );
  }
}

// Singleton instance
export const displayContext = new DisplayContext();

