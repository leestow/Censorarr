(() => {
  /* Persistent stale-while-revalidate media metadata cache.
   *
   * The Overview and Media pages share the same Movies/TV catalog requests. Keep the
   * last known-good non-empty catalog in browser storage so both can paint immediately
   * after the first successful load. Never preserve a transient empty Arr response.
   */
  const upstreamFetch = window.fetch.bind(window);
  const PREFIX = 'censorarr-media-catalog-v3:';
  const OLD_PREFIXES = ['censorarr-media-catalog-v2:'];
  const inflight = new Map();
  const MAX_SAVED_AGE_MS = 7 * 24 * 60 * 60 * 1000;

  function catalogInfo(input, init={}) {
    const raw = typeof input === 'string' ? input : input?.url;
    if (!raw) return null;
    let url;
    try { url = new URL(raw, location.href); } catch (_) { return null; }
    const method = String(init.method || (typeof input !== 'string' && input?.method) || 'GET').toUpperCase();
    if (method !== 'GET' || url.pathname !== '/api/media-catalog') return null;
    return {kind:url.searchParams.get('kind') || 'movies', force:url.searchParams.get('force') === 'true'};
  }

  function fastUrl(kind, force=false) {
    return `/api/media-catalog-fast?kind=${encodeURIComponent(kind)}${force ? '&force=true' : ''}`;
  }
  function canonicalUrl(kind) {
    return `/api/media-catalog?kind=${encodeURIComponent(kind)}&force=true`;
  }
  function key(kind) { return PREFIX + kind; }

  function validData(data) {
    return !!(data && Array.isArray(data.items) && data.items.length > 0);
  }
  function validBody(body) {
    try { return validData(JSON.parse(body)); } catch (_) { return false; }
  }

  function clearOldCaches() {
    try {
      for (const prefix of OLD_PREFIXES) {
        for (const kind of ['movies','series']) localStorage.removeItem(prefix + kind);
      }
    } catch (_) {}
  }

  function readSaved(kind) {
    try {
      const raw = localStorage.getItem(key(kind));
      if (!raw) return null;
      const entry = JSON.parse(raw);
      if (!entry || typeof entry.body !== 'string' || !entry.time || !validBody(entry.body)) {
        localStorage.removeItem(key(kind));
        return null;
      }
      if (Date.now() - Number(entry.time) > MAX_SAVED_AGE_MS) {
        localStorage.removeItem(key(kind));
        return null;
      }
      return entry;
    } catch (_) {
      try { localStorage.removeItem(key(kind)); } catch (_) {}
      return null;
    }
  }

  function responseFrom(entry) {
    return new Response(entry.body, {
      status:Number(entry.status || 200),
      statusText:entry.statusText || 'OK',
      headers:entry.headers || [['content-type','application/json']],
    });
  }

  async function entryFromResponse(response) {
    if (!response?.ok) return null;
    try {
      const body = await response.clone().text();
      if (!validBody(body)) return null;
      return {
        body,
        status:response.status,
        statusText:response.statusText,
        headers:[...response.headers.entries()],
        time:Date.now(),
      };
    } catch (_) { return null; }
  }

  async function saveIfGood(kind, response) {
    const entry = await entryFromResponse(response);
    if (!entry) return false;
    try { localStorage.setItem(key(kind), JSON.stringify(entry)); } catch (_) {}
    return true;
  }

  async function fetchKnownGood(kind, force=false) {
    // Prefer the persistent /config snapshot. If it has not been seeded yet or rejects
    // an empty response, immediately fall back to the original canonical endpoint.
    try {
      const fast = await upstreamFetch(fastUrl(kind, force), {credentials:'same-origin'});
      if (fast.ok) {
        const good = await saveIfGood(kind, fast);
        if (good) return fast;
      }
    } catch (_) {}

    const canonical = await upstreamFetch(canonicalUrl(kind), {credentials:'same-origin'});
    await saveIfGood(kind, canonical);
    return canonical;
  }

  function refreshInBackground(kind) {
    if (inflight.has(kind)) return;
    const job = fetchKnownGood(kind, false)
      .then(response => {
        if (response?.ok) window.dispatchEvent(new CustomEvent('censorarr-metadata-refreshed', {detail:{kind}}));
      })
      .catch(err => console.debug(`Censorarr ${kind} metadata refresh failed:`, err))
      .finally(() => inflight.delete(kind));
    inflight.set(kind, job);
  }

  clearOldCaches();

  window.fetch = async function(input, init={}) {
    const info = catalogInfo(input, init);
    if (!info) return upstreamFetch(input, init);

    // Explicit Refresh Metadata always waits for a real fresh catalog.
    if (info.force) return fetchKnownGood(info.kind, true);

    const saved = readSaved(info.kind);
    if (saved) {
      // Both Overview and Media pages get the same immediate catalog. Refresh silently.
      refreshInBackground(info.kind);
      return responseFrom(saved);
    }

    // No browser snapshot yet: use the persistent server snapshot if available, otherwise
    // seed from the canonical catalog. Only this first successful load should be slow.
    return fetchKnownGood(info.kind, false);
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
        return {kind,cached:!!entry,age_ms:entry ? Date.now()-Number(entry.time) : null};
      });
    },
  };
})();
