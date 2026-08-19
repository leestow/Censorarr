(() => {
  const detailCache = new Map();
  let detailRequest = 0;

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
      .fs-detail-loading-hint {
        display:inline-flex;align-items:center;gap:6px;margin-left:6px;
      }
    `;
    document.head.appendChild(style);
  }

  function catalogItem(kind, id) {
    const wanted = Number(id);
    const catalogKind = kind === 'series' ? 'series' : 'movies';
    const currentKind = kind === 'series' ? 'series' : 'movies';

    try {
      if (typeof MEDIA_ITEMS !== 'undefined' && Array.isArray(MEDIA_ITEMS) && typeof MEDIA_KIND !== 'undefined' && MEDIA_KIND === currentKind) {
        const live = MEDIA_ITEMS.find(x => Number(x?.id) === wanted);
        if (live) return live;
      }
    } catch (_) {}

    try {
      const raw = localStorage.getItem('censorarr-media-catalog-v3:' + catalogKind);
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
      kind: 'movie', source: item.source || 'catalog-cache', id: Number(id),
      title: item.title || 'Movie', year: item.year, poster: item.poster || '', fanart: item.fanart || '',
      overview: item.overview || '', runtime: item.runtime || null,
      certification: item.certification || item.rating || '', genres: Array.isArray(item.genres) ? item.genres : [],
      monitored: item.monitored !== false,
      path: exactFile || item.path || '', media_path: '', has_file: item.has_file !== false,
      size: item.size, quality: item.quality || '', censorarr_status: item.censorarr_status || 'unprocessed',
      censorarr_time: item.censorarr_time, rating: item.rating || item.certification || '', detections: item.detections,
      report: item.report || null, radarr_url: item.radarr_url || '', tracks: {audio: [], subtitles: []},
      _cached_preview: true,
    };
  }

  function previewSeriesDetail(item, id) {
    if (!item) return null;
    const total = Number(item.episode_file_count ?? item.episode_count ?? 0) || 0;
    return {
      kind: 'series', source: item.source || 'catalog-cache', id: Number(id),
      title: item.title || 'TV Show', year: item.year, poster: item.poster || '', fanart: item.fanart || '',
      overview: item.overview || '', runtime: item.runtime || null, certification: item.certification || '',
      genres: Array.isArray(item.genres) ? item.genres : [], network: item.network || '', status: item.status || '',
      monitored: item.monitored !== false, path: item.path || '', sonarr_url: item.sonarr_url || '',
      episode_file_count: item.episode_file_count, episode_count: item.episode_count,
      episodes: [],
      summary: {
        cleaned: Number(item.censorarr_cleaned || 0),
        no_profanity: Number(item.censorarr_no_profanity || 0),
        failed: Number(item.censorarr_failed || 0),
        total,
      },
      episodes_deferred: true,
      _cached_preview: true,
    };
  }

  function cachedPreview(kind, saved) {
    if (!saved?.data) return null;
    const d = saved.data;
    if (kind === 'movie') {
      return {...d, path: d.media_path || d.path || '', media_path: '', tracks: {audio: [], subtitles: []}, _cached_preview: true};
    }
    return {...d, episodes: [], episodes_deferred: true, _cached_preview: true};
  }

  function paintDetail(kind, d) {
    const title = document.getElementById('pageTitle');
    const subtitle = document.getElementById('pageSubtitle');
    if (title) title.textContent = d.title || 'Media details';
    if (subtitle) subtitle.textContent = kind === 'series' ? 'Episode processing status' : 'Movie processing status';
    if (kind === 'series') {
      if (typeof window.renderSeriesDetailPage === 'function') window.renderSeriesDetailPage(d);
    } else if (typeof window.renderMovieDetailPage === 'function') {
      window.renderMovieDetailPage(d);
    }
  }

  function showLoadingHint(kind) {
    const root = document.getElementById('mediaDetail');
    if (!root || document.getElementById('fsMediaDetailLoadingHint')) return;
    const hint = document.createElement('span');
    hint.id = 'fsMediaDetailLoadingHint';
    hint.className = 'badge fs-detail-loading-hint';
    hint.textContent = kind === 'series' ? 'Loading episodes…' : 'Loading file details…';

    const actions = root.querySelector('.detail-actions');
    if (actions) {
      actions.appendChild(hint);
      return;
    }
    const hero = root.querySelector('.detail-hero');
    if (hero) hero.insertAdjacentElement('afterend', hint);
    else root.prepend(hint);
  }

  function showRefreshWarning(kind, message) {
    const root = document.getElementById('mediaDetail');
    if (!root || root.querySelector('.fs-detail-refresh-warning')) return;
    const warning = document.createElement('div');
    warning.className = 'warning fs-detail-refresh-warning';
    warning.style.marginTop = '12px';
    warning.textContent = kind === 'series'
      ? 'Could not refresh the episode list. Showing cached TV metadata. ' + message
      : 'Could not refresh full movie details. Showing cached metadata. ' + message;
    root.appendChild(warning);
  }

  async function fetchDetailWithFallback(kind, id) {
    try {
      return await api('/api/media-detail-fast?kind=' + encodeURIComponent(kind) + '&id=' + Number(id));
    } catch (fastError) {
      // A mixed/stale deployment should never leave Details dead. Fall back to the
      // canonical endpoint if the fast route is unavailable or temporarily unhealthy.
      try {
        return await api('/api/media-detail?kind=' + encodeURIComponent(kind) + '&id=' + Number(id));
      } catch (normalError) {
        normalError.fastDetailError = fastError;
        throw normalError;
      }
    }
  }

  function installFastMediaDetails() {
    const original = window.openMediaDetail;
    if (typeof original !== 'function' || original.__censorarrFastMediaDetails) return;

    const wrapped = async function(kind, id) {
      if (kind !== 'movie' && kind !== 'series') return original.apply(this, arguments);

      const requestId = ++detailRequest;
      const listView = document.getElementById('mediaListView');
      const detailView = document.getElementById('mediaDetailView');
      const detailRoot = document.getElementById('mediaDetail');
      if (listView) listView.style.display = 'none';
      if (detailView) detailView.classList.add('active');

      const cacheKey = kind + ':' + Number(id);
      const saved = detailCache.get(cacheKey);
      const savedFresh = saved && Date.now() - Number(saved.time || 0) < 10 * 60 * 1000;
      const preview = savedFresh
        ? cachedPreview(kind, saved)
        : (kind === 'series' ? previewSeriesDetail(catalogItem(kind, id), id) : previewMovieDetail(catalogItem(kind, id), id));
      let painted = false;

      if (preview) {
        paintDetail(kind, preview);
        painted = true;
        showLoadingHint(kind);
      } else if (detailRoot) {
        detailRoot.innerHTML = '<div class="empty-state">Loading details…</div>';
      }

      try {
        const fast = await fetchDetailWithFallback(kind, id);
        if (requestId !== detailRequest || !detailView?.classList.contains('active')) return fast;

        if (kind === 'movie') {
          detailCache.set(cacheKey, {time: Date.now(), data: fast});
          paintDetail(kind, fast);
          return fast;
        }

        // TV's fast payload intentionally has no episode rows. Paint/refresh the show-level
        // metadata immediately, then fetch the full episode list in the background.
        paintDetail(kind, fast);
        showLoadingHint(kind);

        let full;
        try {
          full = await api('/api/media-detail?kind=series&id=' + Number(id));
        } catch (episodeError) {
          if (requestId === detailRequest && detailView?.classList.contains('active')) {
            showRefreshWarning(kind, episodeError?.message || String(episodeError));
          }
          return fast;
        }

        detailCache.set(cacheKey, {time: Date.now(), data: full});
        if (requestId !== detailRequest || !detailView?.classList.contains('active')) return full;
        paintDetail(kind, full);
        return full;
      } catch (e) {
        if (requestId !== detailRequest || !detailView?.classList.contains('active')) return;
        const message = e?.message || String(e);
        if (painted) {
          showRefreshWarning(kind, message);
        } else if (detailRoot) {
          const safe = String(message).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
          detailRoot.innerHTML = `<button class="detail-back" onclick="backToMedia()">← Back</button><div class="warning">Could not load details: ${safe}</div>`;
        }
      }
    };

    wrapped.__censorarrFastMediaDetails = true;
    window.openMediaDetail = wrapped;
  }

  function apply() {
    applyBrand();
    applySidebarAlignment();
    installFastMediaDetails();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', apply, {once:true});
  else apply();
  setTimeout(apply, 800);
  setTimeout(apply, 1800);
})();
