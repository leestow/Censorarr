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

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', applyBrand, {once:true});
  else applyBrand();
  setTimeout(applyBrand, 800);
})();
