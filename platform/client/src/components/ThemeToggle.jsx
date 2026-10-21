import { useState } from 'react';
import { getTheme, saveTheme } from '../lib/theme.js';

// One button that switches between light and dark mode.
export default function ThemeToggle() {
  const [theme, setTheme] = useState(getTheme);
  const next = theme === 'dark' ? 'light' : 'dark';

  const toggle = () => {
    saveTheme(next);
    setTheme(next);
  };

  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      <span aria-hidden="true">{theme === 'dark' ? '☀' : '☾'}</span> {theme === 'dark' ? 'Light mode' : 'Dark mode'}
    </button>
  );
}