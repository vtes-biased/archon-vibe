import "clsx";
let toasts = [];
const timers = /* @__PURE__ */ new Map();
function generateId() {
  return `toast-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}
function showToast(toast) {
  const id = generateId();
  const duration = toast.duration ?? (toast.type === "error" ? 5e3 : 3e3);
  const newToast = { ...toast, id };
  toasts = [...toasts, newToast];
  if (duration > 0) {
    const timer = setTimeout(
      () => {
        dismissToast(id);
      },
      duration
    );
    timers.set(id, timer);
  }
  return id;
}
function dismissToast(id) {
  const timer = timers.get(id);
  if (timer) {
    clearTimeout(timer);
    timers.delete(id);
  }
  toasts = toasts.filter((t) => t.id !== id);
}
function getToasts() {
  return toasts;
}
export {
  getToasts as g,
  showToast as s
};
//# sourceMappingURL=toast.svelte.js.map
