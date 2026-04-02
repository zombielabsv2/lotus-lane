/**
 * Shared bottom navigation for The Lotus Lane.
 * Include via <script src="/lotus-lane/nav.js"></script> or relative path.
 * Auto-detects current page and highlights the active tab.
 */
(function() {
  // Determine base path (handles both root and subdirectory pages)
  const path = window.location.pathname;
  const isDecoder = path.includes('/decoder');
  const isSubscribe = path.includes('subscribe');
  const isStrips = !isDecoder && !isSubscribe;

  // Base path for links (handle decoder subdirectory)
  const base = isDecoder ? '../' : '';

  const nav = document.createElement('nav');
  nav.id = 'lotus-nav';
  nav.innerHTML = `
    <a href="${base}index.html" class="${isStrips ? 'active' : ''}">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
      <span>Strips</span>
    </a>
    <a href="${base}decoder/index.html" class="${isDecoder ? 'active' : ''}">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
      <span>Gosho Decoder</span>
    </a>
    <a href="${base}subscribe.html" class="${isSubscribe ? 'active' : ''}">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
      <span>Daimoku Daily</span>
    </a>
  `;

  const style = document.createElement('style');
  style.textContent = `
    #lotus-nav {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      gap: 0;
      background: white;
      border-top: 1px solid #e8e4de;
      padding: 0.4rem 0 max(0.4rem, env(safe-area-inset-bottom));
      z-index: 1000;
      box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
    }
    #lotus-nav a {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.2rem;
      padding: 0.3rem 1.5rem;
      text-decoration: none;
      color: #999;
      font-size: 0.7rem;
      font-family: 'Segoe UI', system-ui, sans-serif;
      transition: color 0.2s;
      min-width: 80px;
    }
    #lotus-nav a:hover { color: #c0392b; }
    #lotus-nav a.active { color: #c0392b; font-weight: 600; }
    #lotus-nav a.active svg { stroke: #c0392b; }
    /* Add padding to body so content isn't hidden behind nav */
    body { padding-bottom: 70px !important; }
  `;

  document.head.appendChild(style);
  document.body.appendChild(nav);
})();
