/**
 * Shared navigation for The Lotus Lane.
 * Adds top header links + sticky bottom tab bar across all pages.
 */
(function() {
  const path = window.location.pathname;
  const isDecoder = path.includes('/decoder');
  const isSubscribe = path.includes('subscribe');
  const isIkeda = path.includes('/ikeda');
  const isListicle = path.includes('/listicles');
  const isWisdom = path.includes('/wisdom');
  const isStrips = !isDecoder && !isSubscribe && !isIkeda && !isListicle && !isWisdom;
  const isStripPage = path.includes('/strips/');

  // Determine base path for links
  let base = '';
  if (isDecoder) base = '../';
  if (isIkeda) base = '../';
  if (isListicle) base = '../';
  if (isWisdom) base = '../';
  if (isStripPage) base = '../';

  // --- TOP NAV (inline links below header) ---
  const topNav = document.createElement('div');
  topNav.id = 'lotus-top-nav';
  topNav.innerHTML = `
    <a href="${base}index.html" class="${isStrips ? 'active' : ''}">Stories</a>
    <span class="sep">|</span>
    <a href="${base}wisdom/" class="${path.includes('/wisdom') ? 'active' : ''}">Life Challenges</a>
    <span class="sep">|</span>
    <a href="${base}ikeda/index.html" class="${isIkeda ? 'active' : ''}">Wisdom Library</a>
    <span class="sep">|</span>
    <a href="${base}listicles/" class="${isListicle ? 'active' : ''}">Listicles</a>
    <span class="sep">|</span>
    <a href="${base}decoder/index.html" class="${isDecoder ? 'active' : ''}">Letters on Life</a>
    <span class="sep">|</span>
    <a href="${base}subscribe.html" class="${isSubscribe ? 'active' : ''}">Daily Wisdom</a>
  `;

  // Insert after the header element
  const header = document.querySelector('header');
  if (header && header.nextSibling) {
    header.parentNode.insertBefore(topNav, header.nextSibling);
  } else {
    document.body.prepend(topNav);
  }

  // --- BOTTOM NAV (sticky tab bar) ---
  const bottomNav = document.createElement('nav');
  bottomNav.id = 'lotus-bottom-nav';
  bottomNav.innerHTML = `
    <a href="${base}index.html" class="${isStrips ? 'active' : ''}">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
      <span>Stories</span>
    </a>
    <a href="${base}wisdom/" class="${path.includes('/wisdom') ? 'active' : ''}">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
      <span>Struggles</span>
    </a>
    <a href="${base}ikeda/index.html" class="${isIkeda ? 'active' : ''}">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
      <span>Wisdom</span>
    </a>
    <a href="${base}decoder/index.html" class="${isDecoder ? 'active' : ''}">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
      <span>Letters</span>
    </a>
    <a href="${base}subscribe.html" class="${isSubscribe ? 'active' : ''}">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
      <span>Daily</span>
    </a>
  `;

  document.body.appendChild(bottomNav);

  // --- STYLES ---
  const style = document.createElement('style');
  style.textContent = `
    #lotus-top-nav {
      display: flex;
      justify-content: center;
      align-items: center;
      gap: 0.6rem;
      padding: 0.6rem 1rem;
      background: #f5f2ed;
      border-bottom: 1px solid #e8e4de;
      font-size: 0.85rem;
      font-family: 'Segoe UI', system-ui, sans-serif;
    }
    #lotus-top-nav a {
      text-decoration: none;
      color: #888;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      transition: color 0.2s;
    }
    #lotus-top-nav a:hover { color: #c0392b; }
    #lotus-top-nav a.active { color: #c0392b; font-weight: 600; }
    #lotus-top-nav .sep { color: #ddd; font-size: 0.75rem; }

    #lotus-bottom-nav {
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
    #lotus-bottom-nav a {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.15rem;
      padding: 0.3rem 1rem;
      text-decoration: none;
      color: #999;
      font-size: 0.65rem;
      font-family: 'Segoe UI', system-ui, sans-serif;
      transition: color 0.2s;
      min-width: 60px;
    }
    #lotus-bottom-nav a:hover { color: #c0392b; }
    #lotus-bottom-nav a.active { color: #c0392b; font-weight: 600; }
    #lotus-bottom-nav a.active svg { stroke: #c0392b; }

    body { padding-bottom: 60px !important; }

    @media (max-width: 600px) {
      #lotus-top-nav { font-size: 0.78rem; gap: 0.3rem; }
      #lotus-top-nav a { padding: 0.2rem 0.3rem; }
      #lotus-bottom-nav a { padding: 0.3rem 0.6rem; min-width: 50px; }
    }
  `;

  document.head.appendChild(style);
})();
