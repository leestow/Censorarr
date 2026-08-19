(() => {
  const movieDetailCache = new Map();
  let movieDetailRequest = 0;

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

  function catalogMovie(id) {
    const wanted = Number(id);
    try {
      if (typeof MEDIA_ITEMS !== 'undefined' && Array.isArray(MEDIA_ITEMS)) {
        const live = MEDIA_ITEMS.find(x => Number(x?.id) === wanted);
        if (live) return live;
      }
    } catch (_) {}

    // The persistent metadata cache already makes Movies/Overview instant. Reuse that
    // same known-good catalog when Details is opened from another page or after a reload.
    try {
      const raw = localStorage.getItem('censorarr-media-catalog-v3:movies');
      if (!raw) return null;
      const entry = JSON.parse(raw);
      const payload = JSON.parse(entry?.body || '{}');
      return (payload?.items || []).find(x => Number(x?.id) === wanted) || null;
    } catch (_) {
      return null;
    }
  }

  function previewMovieDetail(item, id) {
    if (!item) return null;
    const exactFile = String(item.media_path || '');
    return {
      kind: 'movie',
      source: item.source || 'catalog-cache',
      id: Number(id),
      title: item.title || 'Movie',
      year: item.year,
      poster: item.poster || '',
      fanart: item.fanart || '',
      overview: item.overview || '',
      runtime: item.runtime || null,
      certification: item.certification || item.rating || '',
      genres: Array.isArray(item.genres) ? item.genres : [],
      monitored: item.monitored !== false,
      // Keep media_path blank on this first paint. The protected Audio Tracks hook uses
      // media_path as its signal to ffprobe; we only want that once the fast detail payload
      // arrives, not twice during the cached preview + refresh sequence.
      path: exactFile || item.path || '',
      media_path: '',
      has_file: item.has_file !== false,
      size: item.size,
      quality: item.quality || '',
      censorarr_status: item.censorarr_status || 'unprocessed',
      censorarr_time: item.censorarr_time,
      rating: item.rating || item.certification || '',
      detections: item.detections,
      report: item.report || null,
      radarr_url: item.radarr_url || '',
      tracks: {audio: [], subtitles: []},
      _cached_preview: true,
    };
  }

  function cachedFullPreview(saved) {
    if (!saved?.data) return null;
    const d = saved.data;
    return {
      ...d,
      path: d.media_path || d.path || '',
      media_path: '',
      tracks: {audio: [], subtitles: []},
      _cached_preview: true,
    };
  }

  function showPreviewHint() {
    const root = document.getElementById('mediaDetail');
    if (!root || document.getElementById('fsMovieDetailPreviewHint')) return;
    const actions = root.querySelector('.detail-actions');
    if (!actions) return;
    const hint = document.createElement('span');
    hint.id = 'fsMovieDetailPreviewHint';
    hint.className = 'badge';
    hint.textContent = 'Loading file details…';
    actions.appendChild(hint);
  }

  function showRefreshWarning(message) {
    const root = document.getElementById('mediaDetail');
    if (!root || root.querySelector('.fs-detail-refresh-warning')) return;
    const warning = document.createElement('div');
    warning.className = 'warning fs-detail-refresh-warning';
    warning.style.marginTop = '12px';
    warning.textContent = 'Could not refresh full movie details. Showing cached metadata. ' + message;
    root.appendChild(warning);
  }

  function installFastMovieDetails() {
    const original = window.openMediaDetail;
    if (typeof original !== 'function' || original.__censorarrFastMovieDetails) return;

    const wrapped = async function(kind, id) {
      if (kind !== 'movie') return original.apply(this, arguments);

      const requestId = ++movieDetailRequest;
      const listView = document.getElementById('mediaListView');
      const detailView = document.getElementById('mediaDetailView');
      const detailRoot = document.getElementById('mediaDetail');
      if (listView) listView.style.display = 'none';
      if (detailView) detailView.classList.add('active');

      const cacheKey = String(Number(id));
      const saved = movieDetailCache.get(cacheKey);
      const savedFresh = saved && Date.now() - Number(saved.time || 0) < 10 * 60 * 1000;
      const preview = savedFresh ? cachedFullPreview(saved) : previewMovieDetail(catalogMovie(id), id);
      let painted = false;

      if (preview && typeof window.renderMovieDetailPage === 'function') {
        const title = document.getElementById('pageTitle');
        const subtitle = document.getElementById('pageSubtitle');
        if (title) title.textContent = preview.title || 'Media details';
        if (subtitle) subtitle.textContent = 'Movie processing status';
        window.renderMovieDetailPage(preview);
        painted = true;
        showPreviewHint();
      } else if (detailRoot) {
        detailRoot.innerHTML = '<div class="empty-state">Loading details…</div>';
      }

      try {
        // This endpoint is backed by the same persistent Movies catalog and intentionally
        // does NOT ffprobe the MKV. Audio Tracks performs the one protected stream probe
        // independently after this fast payload paints.
        const d = await api('/api/media-detail-fast?kind=movie&id=' + Number(id));
        movieDetailCache.set(cacheKey, {time: Date.now(), data: d});

        if (requestId !== movieDetailRequest || !detailView?.classList.contains('active')) return d;
        const title = document.getElementById('pageTitle');
        const subtitle = document.getElementById('pageSubtitle');
        if (title) title.textContent = d.title || 'Media details';
        if (subtitle) subtitle.textContent = 'Movie processing status';
        if (typeof window.renderMovieDetailPage === 'function') window.renderMovieDetailPage(d);
        return d;
      } catch (e) {
        if (requestId !== movieDetailRequest || !detailView?.classList.contains('active')) return;
        const message = e?.message || String(e);
        if (painted) {
          showRefreshWarning(message);
        } else if (detailRoot) {
          detailRoot.innerHTML = `<button class="detail-back" onclick="backToMedia()">← Back</button><div class="warning">Could not load details: ${String(message).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}</div>`;
        }
      }
    };

    wrapped.__censorarrFastMovieDetails = true;
    window.openMediaDetail = wrapped;
  }

  function apply() {
    applyBrand();
    applySidebarAlignment();
    installFastMovieDetails();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply, {once:true});
  else apply();
  setTimeout(apply, 800);
  setTimeout(apply, 1800);
})();
