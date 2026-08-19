(() => {
  const q = (s, root=document) => root.querySelector(s);
  const qa = (s, root=document) => [...root.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  const HELP_TOPICS = [
    {
      id: 'getting-started', icon: '⌂', title: 'Getting Started', subtitle: 'Setup, first scan, and the dashboard',
      body: `<h2>Getting Started</h2><p>Censorarr creates a separate CLEAN audio track while preserving the original media streams. The quickest path is to finish the Setup Wizard, confirm your Movies and TV folders, connect any optional services you use, and then run a library scan.</p><div class="fs-help-callout"><b>Recommended first run</b><span>Use Dry Run if you want to inspect detections before Censorarr changes a media file. When you are ready, switch Processing Mode to Apply.</span></div><h3>Dashboard</h3><p>The Overview page shows recently processed media, current work, subtitle waits, review items, worker status, and recent history. The artwork and metadata come from Radarr/Sonarr when configured; local folders still work without them.</p><div class="fs-help-actions"><button data-help-action="setup">Run Setup Wizard</button><button data-help-action="general">General Settings</button></div>`
    },
    {
      id: 'libraries', icon: '▦', title: 'Libraries', subtitle: 'All Media, Movies, and TV Shows',
      body: `<h2>Libraries</h2><p>Use <b>Libraries → All Media</b> for a combined view, or open Movies and TV Shows separately. Censorarr keeps metadata in the browser so returning to these pages should be nearly instant after the first load.</p><h3>Metadata</h3><p>Radarr and Sonarr add posters, titles, years, overviews, and richer file details. The Refresh Metadata button bypasses the browser cache when you specifically want a fresh catalog.</p><div class="fs-help-callout"><b>If artwork is slow</b><span>Normal navigation should use cached data. Use Refresh Metadata only when you know Radarr/Sonarr changed and you want to force a refresh.</span></div>`
    },
    {
      id: 'processing', icon: '☷', title: 'Processing Rules', subtitle: 'How CLEAN audio gets created',
      body: `<h2>Processing Rules</h2><p>Processing controls detection severity, precision mute timing, rescue behavior, CLEAN track naming, and whether Censorarr waits for review before applying changes.</p><h3>CLEAN track behavior</h3><p>Censorarr preserves the original audio and adds or replaces the dedicated CLEAN track. Reprocessing is designed to replace the previous CLEAN track instead of stacking duplicates.</p><div class="fs-help-actions"><button data-help-action="detection">Open Processing Rules</button></div>`
    },
    {
      id: 'profanity', icon: '◇', title: 'Profanity List', subtitle: 'Built-in words, custom rules, and exceptions',
      body: `<h2>Profanity List</h2><p>The Profanity List is where you enable or disable built-in entries, add custom words or patterns, adjust severity, and create permanent exceptions for known false positives.</p><p>The global minimum severity in Detection settings determines which enabled levels are actually muted.</p><div class="fs-help-actions"><button data-help-action="profanity">Open Profanity List</button></div>`
    },
    {
      id: 'gpu', icon: '⚙', title: 'GPU Worker', subtitle: 'Remote transcription, progress, and live logs',
      body: `<h2>GPU Worker</h2><p>The GPU Worker page is the operational view: current job, progress bars, GPU status, ETA, and the live worker log. Configuration belongs under <b>Settings → Transcription</b>.</p><div class="fs-help-callout"><b>Why two locations?</b><span>GPU Worker is for watching what the worker is doing. Settings → Transcription is for changing models, backend mode, URL, token, timeout, and fallback behavior.</span></div><div class="fs-help-actions"><button data-help-action="gpu">Open GPU Worker</button><button data-help-action="transcription">Transcription Settings</button></div>`
    },
    {
      id: 'integrations', icon: '⬡', title: 'Connecting Services', subtitle: 'Plex, Radarr, Sonarr, and Bazarr',
      body: `<h2>Connecting Services</h2><p>Censorarr can run standalone. Integrations are optional enhancements:</p><ul><li><b>Plex</b> — ratings, activity checks, and library refresh behavior.</li><li><b>Radarr</b> — movie metadata and posters.</li><li><b>Sonarr</b> — TV metadata, series artwork, and episode information.</li><li><b>Bazarr</b> — optional subtitle assistance and missing-subtitle requests.</li></ul><p>These settings live in their related Settings pages rather than occupying a separate main-sidebar destination.</p><div class="fs-help-actions"><button data-help-action="movies-settings">Radarr / Movies</button><button data-help-action="tv-settings">Sonarr / TV</button><button data-help-action="subtitles">Bazarr / Subtitles</button><button data-help-action="plex">Plex</button></div>`
    },
    {
      id: 'logs', icon: '▤', title: 'Live Logs', subtitle: 'Censorarr and GPU worker logs',
      body: `<h2>Live Logs</h2><p>The Logs page uses Censorarr's original operational dashboard so you can see the live log alongside current processing progress. Switch between the Censorarr and GPU Worker logs from that page.</p><div class="fs-help-actions"><button data-help-action="logs">Open Live Logs</button></div>`
    },
    {
      id: 'troubleshooting', icon: '?', title: 'Troubleshooting', subtitle: 'Common problems and where to look',
      body: `<h2>Troubleshooting</h2><h3>Connection error</h3><p>Open Settings for the affected service and use its Test button. Check the URL, API key/token, and Docker path mappings.</p><h3>Media metadata is slow</h3><p>Returning to Movies/TV should use the browser metadata cache. A forced metadata refresh can still take longer because Censorarr must ask Radarr/Sonarr/Bazarr for fresh data.</p><h3>Worker is not progressing</h3><p>Open GPU Worker and inspect the progress fields and live GPU log. If the remote worker is unavailable, check Settings → Transcription and whether local fallback is enabled.</p><h3>File did not process</h3><p>Check Live Logs, History, and the Failure Center. Path mapping and filesystem permissions are the most useful first checks.</p>`
    },
    {
      id: 'updates', icon: '↻', title: 'Updates', subtitle: 'Version status and update controls',
      body: `<h2>Updates</h2><p>The status control in the top-right shows whether Censorarr is up to date. When a supported update is available, clicking it opens the update flow. Backup and update controls also live under Settings → Backup & About.</p><div class="fs-help-actions"><button data-help-action="backup">Backup & About</button><button data-help-action="check-update">Check for Updates</button></div>`
    }
  ];

  function addStyles() {
    if (q('#fsPolishStyles')) return;
    const style = document.createElement('style');
    style.id = 'fsPolishStyles';
    style.textContent = `
      .sidebar-brand{background:transparent!important;border:0!important;box-shadow:none!important}
      .sidebar-brand img{background:transparent!important;width:205px!important;height:44px!important;max-height:44px!important;object-fit:contain!important;object-position:left center!important}
      .side-nav{scrollbar-width:none!important;-ms-overflow-style:none!important}
      .side-nav::-webkit-scrollbar{display:none!important;width:0!important;height:0!important}
      .fs-nav-group>.nav-group-btn{width:100%!important;display:grid!important;grid-template-columns:26px 1fr auto!important;align-items:center!important;gap:9px!important;text-align:left!important;padding:10px 11px!important}
      .fs-nav-group .nav-item.sub{display:none!important;padding-left:46px!important;font-size:12px!important}
      .fs-nav-group.open .nav-item.sub{display:grid!important}
      .fs-nav-group .chev{transition:transform .16s}.fs-nav-group.open .chev{transform:rotate(180deg)}
      .fs-top-theme{min-width:42px!important;padding:0 11px!important;font-size:18px!important}
      .wrap.fs-content-light{--bg:#f3f7fb;--panel:#ffffff;--panel2:#f6f9fc;--panel3:#eaf1f7;--text:#142435;--muted:#647b8e;--line:#d6e2eb;--accent:#15966a;--accent2:#337eea;--warn:#a96d00;--bad:#cf4040;background:#f3f7fb!important;color:#142435!important;min-height:calc(100vh - 72px)}
      .wrap.fs-content-light .fs-kpi,.wrap.fs-content-light .fs-media-panel,.wrap.fs-content-light .fs-side-card,.wrap.fs-content-light .fs-tipbar{background:#fff!important;border-color:#d7e3ec!important;color:#142435!important}
      .wrap.fs-content-light .fs-kpi-label,.wrap.fs-content-light .fs-card-sub,.wrap.fs-content-light .fs-history th{color:#6d8292!important}
      .wrap.fs-content-light .fs-int{background:#f7fafc!important;border-color:#d9e5ed!important;color:#142435!important}
      .wrap.fs-content-light .fs-stat,.wrap.fs-content-light .fs-media-section,.wrap.fs-content-light .fs-history td,.wrap.fs-content-light .fs-history th{border-color:#dce6ed!important}
      .wrap.fs-content-light .fs-meter{background:#e5edf3!important}
      .wrap.fs-content-light .panel,.wrap.fs-content-light .section,.wrap.fs-content-light .media-card,.wrap.fs-content-light .table-wrap{box-shadow:none!important}
      .wrap.fs-content-light .empty-state{color:#6d8292!important}
      #dashboardPane.fs-ops-mode #fsDashboard{display:none!important}
      #dashboardPane.fs-ops-mode #fsLegacyDashboard{display:block!important}
      #dashboardPane:not(.fs-ops-mode) #fsLegacyDashboard{display:none!important}
      .fs-help-shell{display:grid;grid-template-columns:280px minmax(0,1fr);gap:14px;min-height:680px}
      .fs-help-nav,.fs-help-article{background:var(--panel);border:1px solid var(--line);border-radius:9px}
      .fs-help-nav{padding:14px;align-self:start;position:sticky;top:86px}
      .fs-help-brand{display:flex;align-items:center;gap:10px;margin-bottom:12px}.fs-help-brand img{width:34px;height:34px}.fs-help-brand h2{margin:0;font-size:18px}.fs-help-brand span{display:block;color:var(--muted);font-size:11px}
      .fs-help-search{width:100%;min-width:0!important;margin-bottom:10px}
      .fs-help-topic{width:100%;border:0!important;background:transparent!important;display:grid!important;grid-template-columns:26px 1fr!important;text-align:left!important;gap:8px!important;padding:9px!important;border-radius:6px!important;margin:2px 0!important}
      .fs-help-topic:hover{background:var(--panel2)!important}.fs-help-topic.active{background:color-mix(in srgb,var(--accent2) 16%,var(--panel2))!important;box-shadow:inset 3px 0 0 var(--accent2)}
      .fs-help-topic b{display:block;font-size:12px}.fs-help-topic small{display:block;color:var(--muted);font-size:10px;margin-top:2px}
      .fs-help-article{padding:26px 30px;line-height:1.65}.fs-help-article h2{font-size:26px;margin:0 0 8px}.fs-help-article h3{font-size:16px;margin:24px 0 8px}.fs-help-article p,.fs-help-article li{color:color-mix(in srgb,var(--text) 82%,var(--muted));max-width:900px}.fs-help-article ul{padding-left:20px}
      .fs-help-callout{display:grid;gap:4px;border:1px solid color-mix(in srgb,var(--accent2) 35%,var(--line));background:color-mix(in srgb,var(--accent2) 8%,var(--panel2));padding:13px 15px;border-radius:7px;margin:17px 0}.fs-help-callout span{color:var(--muted)}
      .fs-help-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}.fs-help-actions button{background:color-mix(in srgb,var(--accent2) 13%,var(--panel2));border-color:color-mix(in srgb,var(--accent2) 35%,var(--line))}
      .fs-all-head{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin-bottom:12px}.fs-all-head input{min-width:300px!important}.fs-all-summary{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
      .fs-service-svg{width:22px;height:22px;display:block}
      @media(max-width:900px){.fs-help-shell{grid-template-columns:1fr}.fs-help-nav{position:static}.fs-help-topics{display:grid;grid-template-columns:repeat(2,1fr)}}
    `;
    document.head.appendChild(style);
  }

  function setFavicon() {
    qa('link[rel~="icon"],link[rel="shortcut icon"]').forEach(link => {
      link.type = 'image/svg+xml';
      link.href = '/assets/censorarr-favicon-wave.svg?v=1';
    });
    if (!q('link[rel~="icon"]')) {
      const link = document.createElement('link');
      link.rel = 'icon'; link.type = 'image/svg+xml'; link.href = '/assets/censorarr-favicon-wave.svg?v=1';
      document.head.appendChild(link);
    }
  }

  function setLogo() {
    const img = q('.sidebar-brand img');
    if (img) {
      img.src = '/assets/censorarr-logo-wave.svg?v=4';
      img.alt = 'Censorarr';
    }
  }

  function activate(button) {
    qa('.side-nav .nav-item').forEach(x => x.classList.remove('active'));
    button?.classList.add('active');
  }

  function makeNavButton(label, icon, action, sub=false) {
    const b = document.createElement('button');
    b.className = 'nav-item' + (sub ? ' sub' : '');
    b.dataset.polishAction = action;
    b.innerHTML = sub ? `<span>${label}</span>` : `<span class="nav-icon">${icon}</span><span>${label}</span>`;
    return b;
  }

  function makeGroup(label, icon, className, children) {
    const group = document.createElement('div');
    group.className = `nav-group fs-nav-group ${className}`;
    group.innerHTML = `<button type="button" class="nav-group-btn"><span class="nav-icon">${icon}</span><span>${label}</span><span class="chev">▼</span></button>`;
    children.forEach(child => group.appendChild(makeNavButton(child[0], '', child[1], true)));
    group.querySelector('.nav-group-btn').onclick = () => {
      const opening = !group.classList.contains('open');
      qa('.fs-nav-group').forEach(g => { if (g !== group) g.classList.remove('open'); });
      group.classList.toggle('open', opening);
    };
    return group;
  }

  function ensureDashboardMode(mode='overview') {
    const pane = q('#dashboardPane');
    if (!pane) return;
    if (mode === 'overview') pane.classList.remove('fs-ops-mode');
    else pane.classList.add('fs-ops-mode');
  }

  function showOnlyPane(id) {
    qa('.pane').forEach(p => p.classList.remove('active'));
    q('#' + id)?.classList.add('active');
  }

  function showOverview(button) {
    activate(button);
    ensureDashboardMode('overview');
    window.tab?.('dashboard', button);
    const title = q('#pageTitle'), sub = q('#pageSubtitle');
    if (title) title.textContent = 'Dashboard';
    if (sub) sub.textContent = 'Automated clean audio for your media library';
  }

  function showOperations(mode, button) {
    activate(button);
    showOnlyPane('dashboardPane');
    ensureDashboardMode(mode);
    const title = q('#pageTitle'), sub = q('#pageSubtitle');
    if (mode === 'gpu') {
      if (title) title.textContent = 'GPU Worker';
      if (sub) sub.textContent = 'Live transcription progress, worker status, and GPU log';
      window.setLogMode?.('gpu');
    } else {
      if (title) title.textContent = 'Live Logs';
      if (sub) sub.textContent = 'Censorarr processing log and current job progress';
      window.setLogMode?.('plex');
      setTimeout(() => q('#log')?.scrollIntoView({behavior:'smooth',block:'center'}), 80);
    }
  }

  function openHistoryAll(button) {
    const filter = q('#historyFilter');
    if (filter) filter.value = '';
    activate(button);
    window.tab?.('library', button);
    if (filter) filter.value = '';
    window.refreshHistory?.();
  }

  function openSettings(section, button) {
    q('.fs-settings-group')?.classList.add('open');
    activate(button);
    window.openSettingsNav?.(section, button);
  }

  function ensureAllMediaPane() {
    if (q('#allMediaPane')) return;
    const pane = document.createElement('section');
    pane.id = 'allMediaPane'; pane.className = 'pane';
    pane.innerHTML = `<div class="fs-all-head"><input id="fsAllSearch" placeholder="Search all media…"><span class="spacer"></span><button id="fsAllRefresh">Refresh metadata</button></div><div id="fsAllSummary" class="fs-all-summary"></div><div id="fsAllGrid" class="media-grid"><div class="empty-state">Loading media…</div></div>`;
    q('.wrap')?.appendChild(pane);
    q('#fsAllSearch')?.addEventListener('input', renderAllMedia);
    q('#fsAllRefresh')?.addEventListener('click', () => loadAllMedia(true));
  }

  let allMediaItems = [];
  async function loadAllMedia(force=false) {
    ensureAllMediaPane();
    q('#fsAllGrid').innerHTML = '<div class="empty-state">Loading media…</div>';
    try {
      const suffix = force ? '&force=true' : '';
      const [movies, series] = await Promise.all([
        fetch('/api/media-catalog?kind=movies' + suffix).then(r => r.json()),
        fetch('/api/media-catalog?kind=series' + suffix).then(r => r.json())
      ]);
      allMediaItems = [
        ...(movies.items || []).map(x => ({...x, _kind:'movie'})),
        ...(series.items || []).map(x => ({...x, _kind:'series'}))
      ];
      renderAllMedia();
    } catch (err) {
      q('#fsAllGrid').innerHTML = `<div class="empty-state">Could not load media: ${esc(err.message || err)}</div>`;
    }
  }

  function mediaCardHtml(x) {
    const kindLabel = x._kind === 'series' ? 'TV Show' : 'Movie';
    const poster = x.poster ? `<img class="poster" src="${esc(x.poster)}" loading="lazy">` : `<div class="poster placeholder">${x._kind === 'series' ? '📺' : '🎬'}</div>`;
    const state = x._kind === 'series'
      ? ((Number(x.censorarr_cleaned)||0) ? `${Number(x.censorarr_cleaned)} CLEAN` : 'TV Show')
      : String(x.censorarr_status || 'unprocessed').replaceAll('-', ' ');
    return `<div class="media-card" data-all-kind="${x._kind}" data-all-id="${Number(x.id)}">${poster}<div class="media-card-body"><div class="media-title" title="${esc(x.title)}">${esc(x.title)} <span class="media-year">${esc(x.year || '')}</span></div><div class="media-meta"><span class="badge">${kindLabel}</span><span class="badge">${esc(state)}</span></div><div class="media-sub">${esc(x.path || x.media_path || '')}</div></div></div>`;
  }

  function renderAllMedia() {
    const search = (q('#fsAllSearch')?.value || '').trim().toLowerCase();
    const rows = allMediaItems.filter(x => !search || String(x.title || '').toLowerCase().includes(search));
    const movies = rows.filter(x => x._kind === 'movie').length;
    const series = rows.filter(x => x._kind === 'series').length;
    const clean = rows.filter(x => x._kind === 'movie' && ['applied','clean-exists','skipped-clean-exists'].includes(x.censorarr_status)).length;
    q('#fsAllSummary').innerHTML = `<span class="summary-chip"><b>${rows.length}</b> total</span><span class="summary-chip"><b>${movies}</b> movies</span><span class="summary-chip"><b>${series}</b> TV shows</span><span class="summary-chip"><b>${clean}</b> CLEAN movies</span>`;
    q('#fsAllGrid').innerHTML = rows.length ? rows.map(mediaCardHtml).join('') : '<div class="empty-state">No media matches this search.</div>';
    qa('#fsAllGrid .media-card').forEach(card => card.onclick = () => {
      const kind = card.dataset.allKind;
      const id = Number(card.dataset.allId);
      const target = q(`[data-polish-action="library:${kind === 'series' ? 'series' : 'movies'}"]`);
      window.openMediaNav?.(kind === 'series' ? 'series' : 'movies', target);
      setTimeout(() => window.openMediaDetail?.(kind, id), 60);
    });
  }

  function showAllMedia(button) {
    activate(button);
    ensureDashboardMode('overview');
    ensureAllMediaPane();
    showOnlyPane('allMediaPane');
    const title = q('#pageTitle'), sub = q('#pageSubtitle');
    if (title) title.textContent = 'All Media';
    if (sub) sub.textContent = 'Movies and TV shows in one library view';
    loadAllMedia(false);
  }

  function runAction(action, button) {
    if (action === 'overview') return showOverview(button);
    if (action === 'queue') {
      showOverview(button);
      return setTimeout(() => q('#fsInProgress')?.scrollIntoView({behavior:'smooth',block:'start'}), 40);
    }
    if (action === 'library:all') return showAllMedia(button);
    if (action === 'library:movies') { activate(button); ensureDashboardMode('overview'); return window.openMediaNav?.('movies', button); }
    if (action === 'library:series') { activate(button); ensureDashboardMode('overview'); return window.openMediaNav?.('series', button); }
    if (action === 'rules') { activate(button); return window.openSettingsNav?.('detection', button); }
    if (action === 'profanity') { activate(button); return window.tab?.('profanity', button); }
    if (action === 'gpu') return showOperations('gpu', button);
    if (action === 'history') return openHistoryAll(button);
    if (action === 'logs') return showOperations('logs', button);
    if (action.startsWith('settings:')) return openSettings(action.split(':')[1], button);
  }

  function rebuildSidebar() {
    const nav = q('.side-nav');
    if (!nav || nav.dataset.polishVersion === '2') return;
    nav.dataset.polishVersion = '2';
    nav.innerHTML = '';
    nav.appendChild(makeNavButton('Overview','⌂','overview'));
    nav.appendChild(makeNavButton('Queue','☷','queue'));
    nav.appendChild(makeGroup('Libraries','□','fs-library-group',[
      ['All Media','library:all'],['Movies','library:movies'],['TV Shows','library:series']
    ]));
    nav.appendChild(makeNavButton('Processing Rules','☷','rules'));
    nav.appendChild(makeNavButton('Profanity List','◇','profanity'));
    nav.appendChild(makeNavButton('GPU Worker','⚙','gpu'));
    nav.appendChild(makeNavButton('History','◷','history'));
    nav.appendChild(makeNavButton('Logs','▤','logs'));
    nav.appendChild(makeGroup('Settings','⚙','fs-settings-group',[
      ['General','settings:general'],['Movies','settings:movies'],['TV Shows','settings:tv'],['Transcription','settings:whisper'],['Detection','settings:detection'],['Subtitles','settings:subtitles'],['Plex','settings:plex'],['Notifications','settings:notifications'],['File Safety & Logs','settings:safety'],['Backup & About','settings:backup']
    ]));
    nav.addEventListener('click', e => {
      const button = e.target.closest('[data-polish-action]');
      if (button) runAction(button.dataset.polishAction, button);
    });
    nav.querySelector('[data-polish-action="overview"]')?.classList.add('active');
  }

  function applyContentTheme(mode) {
    const wrap = q('.wrap'); if (!wrap) return;
    const light = mode === 'light';
    wrap.classList.toggle('fs-content-light', light);
    localStorage.setItem('censorarr-content-theme', light ? 'light' : 'dark');
    const b = q('#fsContentThemeBtn');
    if (b) { b.textContent = light ? '☾' : '☀'; b.title = light ? 'Use dark content theme' : 'Use light content theme'; }
  }

  function wireTopbar() {
    const settings = q('#fsSettingsBtn');
    if (settings) settings.onclick = () => {
      const button = q('[data-polish-action="settings:general"]');
      q('.fs-settings-group')?.classList.add('open');
      openSettings('general', button);
    };
    const help = q('#fsHelpBtn');
    if (help) help.onclick = () => showHelp();
    if (!q('#fsContentThemeBtn') && settings?.parentElement) {
      const b = document.createElement('button');
      b.id = 'fsContentThemeBtn'; b.className = 'fs-topbtn fs-top-theme';
      settings.parentElement.insertBefore(b, settings);
      b.onclick = () => applyContentTheme(q('.wrap')?.classList.contains('fs-content-light') ? 'dark' : 'light');
    }
    applyContentTheme(localStorage.getItem('censorarr-content-theme') || 'dark');
  }

  function helpTopicList(filter='') {
    const value = filter.trim().toLowerCase();
    return HELP_TOPICS.filter(t => !value || `${t.title} ${t.subtitle} ${t.body.replace(/<[^>]+>/g,' ')}`.toLowerCase().includes(value));
  }

  function ensureHelpPane() {
    if (q('#helpPane')) return;
    const pane = document.createElement('section'); pane.id = 'helpPane'; pane.className = 'pane';
    pane.innerHTML = `<div class="fs-help-shell"><aside class="fs-help-nav"><div class="fs-help-brand"><img src="/assets/censorarr-favicon-wave.svg?v=1"><div><h2>Censorarr Wiki</h2><span>Help built into the app</span></div></div><input id="fsHelpSearch" class="fs-help-search" placeholder="Search the wiki…"><div id="fsHelpTopics" class="fs-help-topics"></div></aside><article id="fsHelpArticle" class="fs-help-article"></article></div>`;
    q('.wrap')?.appendChild(pane);
    q('#fsHelpSearch')?.addEventListener('input', e => renderHelpTopics(e.target.value));
    renderHelpTopics('');
    renderHelpArticle('getting-started');
  }

  function renderHelpTopics(filter='') {
    const list = q('#fsHelpTopics'); if (!list) return;
    const topics = helpTopicList(filter);
    list.innerHTML = topics.length ? topics.map(t => `<button class="fs-help-topic" data-help-topic="${t.id}"><span>${t.icon}</span><span><b>${esc(t.title)}</b><small>${esc(t.subtitle)}</small></span></button>`).join('') : '<div class="empty-state">No help topics match.</div>';
    qa('[data-help-topic]', list).forEach(b => b.onclick = () => renderHelpArticle(b.dataset.helpTopic));
  }

  function renderHelpArticle(id) {
    const topic = HELP_TOPICS.find(t => t.id === id) || HELP_TOPICS[0];
    qa('[data-help-topic]').forEach(b => b.classList.toggle('active', b.dataset.helpTopic === topic.id));
    const article = q('#fsHelpArticle'); if (!article) return;
    article.innerHTML = topic.body;
    qa('[data-help-action]', article).forEach(b => b.onclick = () => helpAction(b.dataset.helpAction));
  }

  function helpAction(action) {
    if (action === 'setup') return window.openSetupWizard?.(false);
    if (action === 'general') return openSettings('general', q('[data-polish-action="settings:general"]'));
    if (action === 'detection') return openSettings('detection', q('[data-polish-action="settings:detection"]'));
    if (action === 'profanity') return runAction('profanity', q('[data-polish-action="profanity"]'));
    if (action === 'gpu') return showOperations('gpu', q('[data-polish-action="gpu"]'));
    if (action === 'transcription') return openSettings('whisper', q('[data-polish-action="settings:whisper"]'));
    if (action === 'logs') return showOperations('logs', q('[data-polish-action="logs"]'));
    if (action === 'movies-settings') return openSettings('movies', q('[data-polish-action="settings:movies"]'));
    if (action === 'tv-settings') return openSettings('tv', q('[data-polish-action="settings:tv"]'));
    if (action === 'subtitles') return openSettings('subtitles', q('[data-polish-action="settings:subtitles"]'));
    if (action === 'plex') return openSettings('plex', q('[data-polish-action="settings:plex"]'));
    if (action === 'backup') return openSettings('backup', q('[data-polish-action="settings:backup"]'));
    if (action === 'check-update') return window.CensorarrUpdater?.check?.(true);
  }

  function showHelp(topic='getting-started') {
    ensureHelpPane();
    showOnlyPane('helpPane');
    qa('.side-nav .nav-item').forEach(x => x.classList.remove('active'));
    const title = q('#pageTitle'), sub = q('#pageSubtitle');
    if (title) title.textContent = 'Help & Wiki';
    if (sub) sub.textContent = 'Censorarr documentation without leaving the app';
    renderHelpArticle(topic);
  }

  function wireDashboardLinks() {
    const worker = q('#fsWorkerOpen');
    if (worker) worker.onclick = () => showOperations('gpu', q('[data-polish-action="gpu"]'));
    const hist = q('#fsHistOpen');
    if (hist) hist.onclick = () => openHistoryAll(q('[data-polish-action="history"]'));
    const recent = q('#fsRecent .fs-link');
    if (recent) recent.onclick = () => openHistoryAll(q('[data-polish-action="history"]'));
  }

  function serviceSvg(name) {
    const key = String(name || '').toLowerCase();
    if (key === 'plex') return `<svg class="fs-service-svg" viewBox="0 0 24 24"><path fill="#e5a00d" d="M8 3h4.8L19 12l-6.2 9H8l6.2-9z"/><path fill="#fff2c4" d="M5 3h3.2l6.1 9-6.1 9H5l6.2-9z" opacity=".55"/></svg>`;
    if (key === 'sonarr') return `<svg class="fs-service-svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="#35a8e0" stroke-width="2.5"/><circle cx="12" cy="12" r="4" fill="none" stroke="#bfeaff" stroke-width="2"/><path d="M12 3v5M12 16v5M3 12h5M16 12h5" stroke="#35a8e0" stroke-width="1.6"/></svg>`;
    if (key === 'radarr') return `<svg class="fs-service-svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="#f5c542"/><path d="M12 5l5 4-2 7H9L7 9z" fill="#fff"/><circle cx="12" cy="12" r="2.3" fill="#182532"/></svg>`;
    if (key === 'bazarr') return `<svg class="fs-service-svg" viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="5" fill="#12191f" stroke="#e9f3f8" stroke-width="1.5"/><path d="M7 9h10M7 13h7M7 17h5" stroke="#f2f7fa" stroke-width="1.7" stroke-linecap="round"/></svg>`;
    if (key.includes('gpu')) return `<svg class="fs-service-svg" viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="14" rx="3" fill="#29b765"/><path d="M8 9h8v6H8zM2 9h2M2 15h2M20 9h2M20 15h2" stroke="#eafff1" stroke-width="1.5"/></svg>`;
    return `<svg class="fs-service-svg" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="4" fill="#2d7fc5"/><path d="M7 10h10M7 14h7" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>`;
  }

  function applyServiceIcons() {
    qa('#fsIntegrations .fs-int').forEach(card => {
      const name = q('.fs-int-name', card)?.textContent || '';
      const icon = q('.fs-int-icon', card);
      if (icon) icon.innerHTML = serviceSvg(name);
    });
  }

  function observeIntegrationCard() {
    const box = q('#fsIntegrations'); if (!box || box.dataset.iconObserver === '1') return;
    box.dataset.iconObserver = '1';
    new MutationObserver(() => applyServiceIcons()).observe(box, {childList:true,subtree:true});
    applyServiceIcons();
  }

  function boot() {
    addStyles();
    setFavicon();
    setLogo();
    rebuildSidebar();
    wireTopbar();
    wireDashboardLinks();
    observeIntegrationCard();
    ensureHelpPane();
    setTimeout(() => { setLogo(); wireTopbar(); wireDashboardLinks(); applyServiceIcons(); }, 700);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 120));
  else setTimeout(boot, 120);
})();
