export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  action?: { label: string; onClick: () => void };
  duration?: number; // ms, 0 = persistent
}

let toasts = $state<Toast[]>([]);

const timers = new Map<string, ReturnType<typeof setTimeout>>();

function generateId(): string {
  return `toast-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

export function showToast(toast: Omit<Toast, 'id'>): string {
  const id = generateId();
  const duration = toast.duration ?? (toast.type === 'error' ? 5000 : 3000);

  const newToast: Toast = { ...toast, id };
  toasts = [...toasts, newToast];

  if (duration > 0) {
    const timer = setTimeout(() => {
      dismissToast(id);
    }, duration);
    timers.set(id, timer);
  }

  return id;
}

export function dismissToast(id: string): void {
  const timer = timers.get(id);
  if (timer) {
    clearTimeout(timer);
    timers.delete(id);
  }

  toasts = toasts.filter((t) => t.id !== id);
}


export function getToasts(): Toast[] {
  return toasts;
}
