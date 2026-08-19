(() => {
  /*
   * Keep the last successful Movies/TV catalog in browser storage so a full page
   * reload can paint the redesigned Overview immediately. The older runtime cache
   * is memory-only and disappears on every reload.
   *
   * This is stale-while-revalidate by design: cached metadata is returned at once,
   * while a real request refreshes the saved copy quietly in the background. Live
   * processing/progress still comes from the normal status endpoints and is never
   * served from this cache.
   */
  const upstreamFetch = window.fetch.bind(window);
  const PREFIX = 'censorarr-media-catalog-v2:';
  const inflight = new Map();
  const MAX_SAVED_AGE_MS = 7 * 24 * 60 * 60 * 1000;

  function catalogInfo(input, init={}) {
    const raw = typeof input === 'string' ? input : input?.url;
    if (!raw) return null;
    let url;
    try { url = new URL(raw, location.href); } catch (_) { return null; }
    const method = String(init.method || (typeof input !== 'string' && input?.method) || 'GET').toUpperCase();
    if (method !== 'GET' || url.pathname !== '/api/media-catalog') return null;
    return {
      kind: url.searchParams.get('kind') || 'movies',
      force: url.searchParams.get('force') === 'true',
    };
  }

  function key(kind) { return PREFIX + kind; }

  function readSaved(kind) {
    try {
      const raw = localStorage.getItem(key(kind));
      if (!raw) return null;
      const entry = JSON.parse(raw);
      if (!entry || typeof entry.body !== 'string' || !entry.time) return null;
      if (Date.now() - Number(entry.time) > MAX_SAVED_AGE_MS) {
        localStorage.removeItem(key(kind));
        return null;
      }
      return entry;
    } catch (_) {
      return null;
    }
  }

  function responseFrom(entry) {
    return new Response(entry.body, {
      status: Number(entry.status || 200),
      statusText: entry.statusText || 'OK',
      headers: entry.headers || [['content-type', 'application/json']],
    });
  }

  async function saveResponse(kind, response) {
    if (!response?.ok) return response;
    try {
      const body = await response.clone().text();
      const entry = {
        body,
        status: response.status,
        statusText: response.statusText,
        headers: [...response.headers.entries()],
        time: Date.now(),
      };
      localStorage.setItem(key(kind), JSON.stringify(entry));
    } catch (err) {
      // Storage can be disabled or full. Never let caching break normal browsing.
      console.debug('Censorarr persistent metadata cache unavailable:', err);
    }
    return response;
  }

  function refreshInBackground(input, init, kind) {
    if (inflight.has(kind)) return;
    const job = upstreamFetch(input, init)
      .then(response => saveResponse(kind, response))
      .then(() => window.dispatchEvent(new CustomEvent('censorarr-metadata-refreshed', {detail:{kind}})))
      .catch(err => console.debug(`Censorarr ${kind} metadata refresh failed:`, err))
      .finally(() => inflight.delete(kind));
    inflight.set(kind, job);
  }

  window.fetch = async function(input, init={}) {
    const info = catalogInfo(input, init);
    if (!info) return upstreamFetch(input, init);

    // Explicit Refresh Metadata always waits for the real service and then replaces
    // the persistent snapshot with the fresh response.
    if (info.force) {
      const response = await upstreamFetch(input, init);
      await saveResponse(info.kind, response);
      return response;
    }

    const saved = readSaved(info.kind);
    if (saved) {
      refreshInBackground(input, init, info.kind);
      return responseFrom(saved);
    }

    // First visit on this browser/device has nothing to paint yet, so seed the cache
    // from the normal request. Every later reload can use this saved snapshot.
    const response = await upstreamFetch(input, init);
    await saveResponse(info.kind, response);
    return response;
  };

  window.CensorarrPersistentMediaCache = {
    clear(kind) {
      try {
        if (kind) localStorage.removeItem(key(kind));
        else ['movies','series'].forEach(x => localStorage.removeItem(key(x)));
      } catch (_) {}
    },
    status() {
      return ['movies','series'].map(kind => {
        const entry = readSaved(kind);
        return {kind, cached: !!entry, age_ms: entry ? Date.now() - Number(entry.time) : null};
      });
    },
  };
})();
