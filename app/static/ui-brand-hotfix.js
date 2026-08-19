(() => {
  function applyBrand() {
    const logo = document.querySelector('.sidebar-brand img');
    if (logo) {
      logo.src = '/assets/censorarr-logo-wave.svg?v=5';
      logo.alt = 'Censorarr';
      logo.style.background = 'transparent';
    }
    const icons = [...document.querySelectorAll('link[rel~="icon"], link[rel="shortcut icon"]')];
    if (!icons.length) {
      const link = document.createElement('link');
      link.rel = 'icon';
      document.head.appendChild(link);
      icons.push(link);
    }
    for (const link of icons) {
      link.type = 'image/svg+xml';
      link.href = '/assets/censorarr-favicon-wave.svg?v=2';
    }
  }

  function applySidebarAlignment() {
    if (document.getElementById('censorarrSidebarAlignmentFix')) return;
    const style = document.createElement('style');
    style.id = 'censorarrSidebarAlignmentFix';
    style.textContent = `
      /* Collapsible headers must use the exact same icon/text geometry as normal nav rows. */
      .side-nav .fs-nav-group > .nav-group-btn {
        grid-template-columns: 28px 1fr auto !important;
        gap: 8px !important;
        padding: 10px 17px !important;
      }
    `;
    document.head.appendChild(style);
  }

  function apply() {
    applyBrand();
    applySidebarAlignment();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply, {once:true});
  else apply();
  setTimeout(apply, 800);
})();
