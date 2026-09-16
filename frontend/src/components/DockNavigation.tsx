interface DockNavigationProps {
  currentTab: string
  onTabChange: (tab: string) => void
}

export default function DockNavigation({ currentTab, onTabChange }: DockNavigationProps) {
  return (
    <nav className="dock" data-od-id="bottom-navigation" aria-label="Primary navigation">
      {/* Home is merged with Scan in the new flow, but we can keep the tab for now or map it to scan */}
      <button 
        className={`dock-item ${currentTab === 'home' ? 'active' : ''}`} 
        onClick={() => onTabChange('home')}
      >
        <span className="dock-icon">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
            <path d="M3 6h18M3 12h12M3 18h18" />
            <circle cx="20" cy="12" r="2.5" />
            <path d="M20 9V7M20 17v-2" />
          </svg>
        </span>
        QUEUE
      </button>
      
      <button 
        className={`dock-item ${currentTab === 'scan' || currentTab === 'processing' || currentTab === 'result' ? 'active' : ''}`} 
        onClick={() => {
          if (currentTab === 'scan') {
            window.dispatchEvent(new Event('trigger-camera-capture'));
          } else {
            onTabChange('scan');
          }
        }}
      >
        <span className="dock-icon">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
            <path d="M4 7V5a1 1 0 0 1 1-1h2M17 4h2a1 1 0 0 1 1 1v2M20 17v2a1 1 0 0 1-1 1h-2M7 20H5a1 1 0 0 1-1-1v-2M7 12h10M12 7v10" />
          </svg>
        </span>
        SCAN
      </button>

      <button 
        className={`dock-item ${currentTab === 'history' ? 'active' : ''}`} 
        onClick={() => onTabChange('history')}
      >
        <span className="dock-icon">
          <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <rect x="14" y="14" width="7" height="7" rx="1" />
          </svg>
        </span>
        LISTS
      </button>
    </nav>
  )
}
