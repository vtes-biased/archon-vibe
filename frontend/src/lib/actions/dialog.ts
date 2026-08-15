/**
 * Focus a dialog panel on mount and close it on Escape.
 *
 * Both halves belong together. The pattern this replaces put the Escape check on
 * the backdrop and an unconditional `e.stopPropagation()` on the panel, so the
 * keydown died on the panel and never reached the handler — and where nothing
 * focused the panel at all, it fired on `<body>` and missed the backdrop too.
 * Binding Escape to the element that actually holds focus makes it work in both
 * cases, and keeps a panel's own `stopPropagation` (which stops keystrokes
 * leaking to the page behind) harmless: same-element listeners all still run.
 *
 * Applies `tabindex="-1"` when the markup hasn't, since an unfocusable panel
 * silently defeats the whole thing.
 */
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
