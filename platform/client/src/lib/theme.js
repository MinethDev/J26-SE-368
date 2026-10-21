// Light / dark theme toggle. The choice is remembered in this browser;
// on the first visit it follows the operating system setting.
const KEY = 'devintel.theme';

export function getTheme() {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // Storage unavailable: fall back to the system setting.
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
}

export function saveTheme(theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // Storage unavailable (private window): the choice lasts until the page reloads.
  }
  applyTheme(theme);
}