/**
 * Toast notification store using Svelte 5 runes.
 */

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  action?: { label: string; onClick: () => void };
  duration?: number; // ms, 0 = persistent
}

// Reactive toast state
let toasts = $state<Toast[]>([]);

// Auto-dismiss timers
const timers = new Map<string, ReturnType<typeof setTimeout>>();

/**
 * Generate a unique toast ID.
 */
function generateId(): string {
  return `toast-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/**
 * Show a toast notification.
 */
export function showToast(toast: Omit<Toast, 'id'>): string {
  const id = generateId();
  const duration = toast.duration ?? (toast.type === 'error' ? 5000 : 3000);

  const newToast: Toast = { ...toast, id };
  toasts = [...toasts, newToast];

  // Auto-dismiss if duration > 0
  if (duration > 0) {
    const timer = setTimeout(() => {
      dismissToast(id);
    }, duration);
    timers.set(id, timer);
  }

  return id;
}

/**
 * Dismiss a toast by ID.
 */
export function dismissToast(id: string): void {
  // Clear timer if exists
  const timer = timers.get(id);
  if (timer) {
    clearTimeout(timer);
    timers.delete(id);
  }

  toasts = toasts.filter((t) => t.id !== id);
}

/**
 * Dismiss all toasts.
 */
export function dismissAllToasts(): void {
  // Clear all timers
  timers.forEach((timer) => clearTimeout(timer));
  timers.clear();

  toasts = [];
}

/**
 * Get the current toasts (reactive).
 */
export function getToasts(): Toast[] {
  return toasts;
}
