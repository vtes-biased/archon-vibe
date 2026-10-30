export function dialogPanel(node: HTMLElement, onClose?: () => void) {
  let close = onClose;
  let pressedInside = false;
  if (!node.hasAttribute('tabindex')) node.tabIndex = -1;
  node.focus();

  function onkeydown(e: KeyboardEvent) {
    if (e.key !== 'Escape') return;
    e.stopPropagation();
    close?.();
  }

  function onpointerdown(e: PointerEvent) {
    pressedInside = node.contains(e.target as Node);
  }

  function onclick(e: MouseEvent) {
    if (pressedInside && !node.contains(e.target as Node)) e.stopPropagation();
    pressedInside = false;
  }

  node.addEventListener('keydown', onkeydown);
  window.addEventListener('pointerdown', onpointerdown, true);
  window.addEventListener('click', onclick, true);
  return {
    update(next?: () => void) {
      close = next;
    },
    destroy() {
      node.removeEventListener('keydown', onkeydown);
      window.removeEventListener('pointerdown', onpointerdown, true);
      window.removeEventListener('click', onclick, true);
    },
  };
}
