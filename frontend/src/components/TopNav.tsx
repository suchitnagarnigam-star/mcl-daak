import { useEffect, useState } from 'react';
import mclLogo from '../assets/mcl-logo.png';

export default function TopNav() {
  const [isDark, setIsDark] = useState(() => {
    // Check local storage or system preference on mount
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('mcl-theme');
      if (stored) return stored === 'dark';
      return window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    return false;
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('mcl-theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('mcl-theme', 'light');
    }
  }, [isDark]);

  const toggleTheme = () => setIsDark(!isDark);

  return (
    <header className="topnav" data-od-id="header">
      <div className="topnav-inner">
        <div className="brand" data-od-id="brand">
          <span className="brand-mark">
            <img src={mclLogo} alt="MCL Logo" width="36" height="36" style={{ objectFit: 'contain' }} />
          </span>
          <span>MCL DAAK<small>Municipal Corporation Ludhiana</small></span>
        </div>
        <div className="topnav-actions" style={{ marginLeft: 'auto' }}>
          <button type="button" className="theme-toggle" aria-label="Toggle theme" onClick={toggleTheme} style={{ 
            width: '40px', height: '40px', borderRadius: '50%', border: '1px solid var(--border)', 
            background: 'var(--bg)', display: 'grid', placeItems: 'center', color: 'var(--fg)', cursor: 'pointer' 
          }}>
            {isDark ? (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="5" />
                <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  )
}
