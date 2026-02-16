type ThemePref = 'light' | 'dark' | 'system';

let pref = $state<ThemePref>(
  (typeof localStorage !== 'undefined' && localStorage.getItem('theme') as ThemePref) || 'system'
);

// Keep in sync with the inline anti-FOUC script in app.html
function apply(p: ThemePref) {
  const isLight =
    p === 'light' || (p === 'system' && matchMedia('(prefers-color-scheme: light)').matches);
  document.documentElement.classList.toggle('light', isLight);
  document.querySelector('meta[name="theme-color"]')
    ?.setAttribute('content', isLight ? '#A40F2D' : '#DC143C');
}

// Listen for OS theme changes when pref is 'system'
if (typeof window !== 'undefined') {
  matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (pref === 'system') apply('system');
  });
}

export function getTheme(): ThemePref {
  return pref;
}

export function cycleTheme() {
  const next: ThemePref = pref === 'system' ? 'light' : pref === 'light' ? 'dark' : 'system';
  pref = next;
  localStorage.setItem('theme', next);
  apply(next);
}

export function initTheme() {
  apply(pref);
}
