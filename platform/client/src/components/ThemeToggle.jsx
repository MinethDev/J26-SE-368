import { useState } from 'react';
import { getTheme, saveTheme } from '../lib/theme.js';
import { IconMoon, IconSun } from './Icons.jsx';

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
      {theme === 'dark' ? <IconSun /> : <IconMoon />}
      <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
    </button>
  );
}