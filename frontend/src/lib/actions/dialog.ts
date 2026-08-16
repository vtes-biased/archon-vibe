/** Binds Escape to the element that actually holds focus, not the backdrop — the previous pattern's
 * stopPropagation on the panel meant the keydown never reached a backdrop-bound handler. Sets tabindex="-1" when missing, since an unfocusable panel defeats this silently. */
export function dialogPanel(node: HTMLElement, onClose?: () => void) {
  let close = onClose;
  if (!node.hasAttribute('tabindex')) node.tabIndex = -1;
  node.focus();

  function onkeydown(e: KeyboardEvent) {
    if (e.key !== 'Escape') return;
    e.stopPropagation();
    close?.();
  }

  node.addEventListener('keydown', onkeydown);
  return {
    update(next?: () => void) {
      close = next;
    },
    destroy() {
      node.removeEventListener('keydown', onkeydown);
    },
  };
}
