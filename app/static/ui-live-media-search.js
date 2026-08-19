(() => {
  const SEARCH_ID = 'mediaSearch';
  const GRID_ID = 'mediaGrid';
  const HIDDEN_CLASS = 'fs-live-search-hidden';

  function normalize(value) {
    return String(value || '').trim().toLocaleLowerCase();
  }

  function ensureStyle() {
    if (document.getElementById('fsLiveMediaSearchStyle')) return;
    const style = document.createElement('style');
    style.id = 'fsLiveMediaSearchStyle';
    style.textContent = `.${HIDDEN_CLASS}{display:none!important}`;
    document.head.appendChild(style);
  }

  function filterVisibleCards() {
    const input = document.getElementById(SEARCH_ID);
    const grid = document.getElementById(GRID_ID);
    if (!input || !grid) return;

    const query = normalize(input.value);
    const cards = [...grid.querySelectorAll('.media-card')];
    if (!cards.length) return;

    for (const card of cards) {
      const haystack = normalize(card.textContent);
      card.classList.toggle(HIDDEN_CLASS, !!query && !haystack.includes(query));
    }
  }

  function bind() {
    ensureStyle();
    const input = document.getElementById(SEARCH_ID);
    const grid = document.getElementById(GRID_ID);
    if (!input || !grid) return false;

    if (input.dataset.fsLiveSearch !== '1') {
      input.dataset.fsLiveSearch = '1';
      input.setAttribute('autocomplete', 'off');
      input.addEventListener('input', () => {
        // Keep the app's normal render/filter logic in sync, but also apply a local
        // DOM filter immediately so results disappear as each character is typed.
        try {
          if (typeof window.renderMedia === 'function') window.renderMedia();
        } catch (_) {}
        requestAnimationFrame(filterVisibleCards);
      }, { passive: true });
    }

    if (grid.dataset.fsLiveSearchObserver !== '1') {
      grid.dataset.fsLiveSearchObserver = '1';
      new MutationObserver(() => requestAnimationFrame(filterVisibleCards))
        .observe(grid, { childList: true, subtree: false });
    }

    filterVisibleCards();
    return true;
  }

  function boot() {
    if (bind()) return;
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      if (bind() || tries >= 40) clearInterval(timer);
    }, 250);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
