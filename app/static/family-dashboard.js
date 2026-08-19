(() => {
  const TIPS = [
    'Enable Dry Run on new libraries to preview changes before applying.',
    'Use Review Mode when you want to approve detections before a CLEAN track is created.',
    'A remote GPU worker can speed up Whisper transcription without moving Censorarr off your NAS.',
    'Bazarr is optional: Censorarr can still use embedded or local text subtitles when available.'
  ];
  let tipIndex = 0;
  let mediaCache = { movies: [], series: [] };

  const q = (s, root=document) => root.querySelector(s);
  const qa = (s, root=document) => [...root.querySelectorAll(s)];
  const text = id => document.getElementById(id)?.textContent?.trim() || '—';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const statusGood = s => ['applied','clean-exists','skipped-clean-exists','no-detections'].includes(String(s||''));
  const statusWaiting = s => ['waiting-subtitle','waiting-rating'].includes(String(s||''));
  const statusReview = s => String(s||'') === 'awaiting-review';
  const itemTitle = x => x?.title || 'Untitled';
  const itemYear = x => x?.year || '';
  const poster = x => x?.poster || '';

  function injectStyles() {
    if (document.getElementById('familyDashboardStyles')) return;
    const style = document.createElement('style');
    style.id = 'familyDashboardStyles';
    style.textContent = `
      html{background:#07131f}html[data-theme=light]{--bg:#07131f;--panel:#0d1d2b;--panel2:#112638;--panel3:#173249;--text:#edf7ff;--muted:#8fa9bd;--line:#1b3b50;--accent:#25d48a;--accent2:#238bf3;--warn:#ffad33;--bad:#ff5f69}
      body{background:radial-gradient(circle at 72% -10%,rgba(16,166,145,.16),transparent 30%),#07131f;color:#edf7ff}
      .app-shell{grid-template-columns:250px minmax(0,1fr)!important}.sidebar{background:linear-gradient(180deg,#072333 0%,#07344a 52%,#082b42 100%)!important;border-right:1px solid #14516b;padding:14px 12px!important}.sidebar-brand{height:70px!important;background:transparent!important;border:0!important;margin:0 4px 14px!important;padding:4px!important}.sidebar-brand img{max-height:58px!important;object-position:left center!important}.side-nav{gap:2px!important}.nav-section{color:#7fa8ba!important;padding:17px 10px 7px!important}.side-nav .nav-item,.nav-group-btn{border:0!important;background:transparent!important;color:#d8e8f2!important;border-radius:7px!important}.side-nav .nav-item:hover,.nav-group-btn:hover{background:rgba(30,151,177,.13)!important}.side-nav .nav-item.active{background:linear-gradient(90deg,#0e8378,#126a86)!important;color:#fff!important;box-shadow:inset 3px 0 0 #36e0ca!important}.nav-icon{color:#62d9ff!important}.nav-count{background:#143e55!important;color:#e3f5ff!important}.nav-group .nav-item.sub{padding-left:44px!important}.sidebar-footer{border-top:1px solid rgba(113,196,222,.13);margin-top:auto!important}.appbar{height:72px!important;background:linear-gradient(90deg,#073d43 0%,#07554d 45%,#087769 100%)!important;border-bottom:1px solid #13847a!important;padding:0 18px!important;box-shadow:0 8px 28px rgba(0,0,0,.18)}
      .appbar>div:first-child{display:none!important}.appbar .right{width:100%!important;display:flex!important;gap:10px!important}.fs-search{height:42px;min-width:380px;flex:1;max-width:640px;background:rgba(3,32,38,.48)!important;border:1px solid rgba(102,234,215,.26)!important;color:#eafcff!important;border-radius:8px!important;padding:0 14px!important}.fs-top-spacer{flex:1}.fs-topbtn{height:40px!important;padding:0 14px!important;border:1px solid rgba(137,239,220,.19)!important;background:rgba(4,37,43,.35)!important;color:#edfdfb!important;border-radius:7px!important;font-weight:700}.fs-topbtn.primary{background:rgba(19,167,136,.42)!important;border-color:#1bb897!important}.fs-update{border-color:#21c58f!important;color:#8df6c6!important}.wrap{padding:12px 18px 22px!important}.pane#dashboardPane>.cards,.pane#dashboardPane>.grid{display:none!important}.fs-dashboard{display:grid;gap:12px}.fs-kpis{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.fs-kpi{min-height:104px;background:linear-gradient(145deg,#0d1c2a,#102436);border:1px solid #173c52;border-radius:8px;padding:14px;display:grid;grid-template-columns:48px 1fr;gap:12px;align-items:center}.fs-kpi-icon{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;font-size:21px;font-weight:900;background:#133c45;color:#4ee5b4}.fs-kpi:nth-child(2) .fs-kpi-icon{background:#321b5a;color:#a47cff}.fs-kpi:nth-child(3) .fs-kpi-icon{background:#102f68;color:#55a8ff}.fs-kpi:nth-child(4) .fs-kpi-icon{background:#123f42;color:#54e0d2}.fs-kpi:nth-child(5) .fs-kpi-icon{background:#173b2b;color:#6ce494}.fs-kpi-label{font-size:12px;color:#a9c0cf}.fs-kpi-value{font-size:25px;font-weight:800;line-height:1.15;margin:3px 0}.fs-kpi-sub{font-size:11px;color:#39dd8b}.fs-main-grid{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(360px,.82fr);gap:12px}.fs-media-panel,.fs-side-card{background:#0c1c2a;border:1px solid #17384d;border-radius:8px;overflow:hidden}.fs-media-section{padding:12px 12px 10px;border-bottom:1px solid #17384d}.fs-media-section:last-child{border-bottom:0}.fs-section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.fs-section-head h2{font-size:16px;margin:0}.fs-link{color:#55b8ff;font-size:12px;cursor:pointer}.fs-row{display:grid;grid-template-columns:repeat(6,minmax(98px,1fr));gap:10px}.fs-row.small{grid-template-columns:repeat(6,minmax(78px,1fr))}.fs-poster-card{min-width:0;cursor:pointer}.fs-poster{position:relative;aspect-ratio:2/3;border-radius:6px;overflow:hidden;background:linear-gradient(145deg,#173044,#0a1722);box-shadow:0 4px 16px rgba(0,0,0,.22)}.fs-poster img{width:100%;height:100%;object-fit:cover;display:block}.fs-poster-placeholder{width:100%;height:100%;display:grid;place-items:center;font-size:30px;color:#4f7388}.fs-chip{position:absolute;top:7px;left:7px;padding:3px 7px;border-radius:5px;font-size:10px;font-weight:800;background:#1aaa68;color:white}.fs-chip.wait{background:#d88612}.fs-chip.review{background:#7b47d9}.fs-card-title{margin-top:7px;font-size:12px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fs-card-sub{font-size:10px;color:#8199aa;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fs-progress-ring{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:68px;height:68px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(#35d98e var(--p),#277cff var(--p),rgba(2,12,18,.72) 0);box-shadow:0 0 0 5px rgba(4,18,24,.45)}.fs-progress-ring::after{content:'';position:absolute;inset:6px;background:#07131fdd;border-radius:50%}.fs-progress-ring span{position:relative;z-index:1;font-weight:800;font-size:14px}.fs-side{display:grid;gap:10px;align-content:start}.fs-side-card{padding:13px}.fs-side-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}.fs-side-title h2{margin:0;font-size:16px}.fs-worker-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px 20px}.fs-stat{display:flex;justify-content:space-between;gap:12px;padding:7px 0;border-bottom:1px solid #17384d;font-size:12px}.fs-stat b{font-weight:700}.fs-online{color:#50e899}.fs-meter{height:6px;background:#173247;border-radius:999px;overflow:hidden;margin:5px 0 8px}.fs-meter>span{display:block;height:100%;background:linear-gradient(90deg,#18d189,#52e8bb);border-radius:999px}.fs-integrations{display:grid;grid-template-columns:1fr 1fr;gap:7px}.fs-int{border:1px solid #17384d;border-radius:6px;padding:9px 10px;display:flex;align-items:center;gap:8px;background:#0e2030}.fs-int-icon{width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:#122d3f;font-weight:900;color:#7dcaff}.fs-int-name{font-size:12px;font-weight:700}.fs-int-state{font-size:10px;color:#42da8a}.fs-history{width:100%;border-collapse:collapse}.fs-history th,.fs-history td{padding:7px 5px;border-bottom:1px solid #17384d;font-size:11px}.fs-history th{color:#829bab;text-transform:none;letter-spacing:0;background:transparent;position:static}.fs-success{display:inline-block;background:#143d2a;color:#65e99c;padding:2px 7px;border-radius:4px}.fs-tipbar{height:52px;background:#0c1d2c;border:1px solid #17384d;border-radius:8px;display:flex;align-items:center;gap:10px;padding:0 16px}.fs-tiptext{font-size:12px;flex:1}.fs-tipdots{display:flex;gap:8px}.fs-tipdot{width:8px;height:8px;border-radius:50%;background:#607788}.fs-tipdot.active{background:#24d18a}.fs-tipnav{border:0!important;background:transparent!important;padding:4px 7px!important;color:#cbe1ee!important}.fs-legacy{display:none!important}
      .fs-sidebar-collapse{position:absolute;top:21px;right:-41px;z-index:40;width:32px;height:32px;border:1px solid #1b5267!important;border-radius:7px!important;background:#09222f!important;color:#dff7ff!important}.app-shell.fs-collapsed{grid-template-columns:72px minmax(0,1fr)!important}.app-shell.fs-collapsed .sidebar{padding-left:8px!important;padding-right:8px!important}.app-shell.fs-collapsed .sidebar-brand img{object-fit:cover;object-position:left;width:48px!important;max-width:48px!important}.app-shell.fs-collapsed .nav-item span:not(.nav-icon):not(.nav-count),.app-shell.fs-collapsed .nav-group-btn span:not(.nav-icon),.app-shell.fs-collapsed .nav-section,.app-shell.fs-collapsed .sidebar-footer{display:none!important}.app-shell.fs-collapsed .side-nav .nav-item,.app-shell.fs-collapsed .nav-group-btn{grid-template-columns:1fr!important;justify-items:center!important;padding:10px 4px!important}.app-shell.fs-collapsed .nav-icon{font-size:18px}.app-shell.fs-collapsed .nav-group .nav-item.sub{padding-left:4px!important}.app-shell.fs-collapsed .nav-group .nav-item.sub::before{content:'•';color:#5ccfea}.app-shell.fs-collapsed .fs-sidebar-collapse{right:-41px}
      @media(max-width:1200px){.fs-kpis{grid-template-columns:repeat(3,1fr)}.fs-main-grid{grid-template-columns:1fr}.fs-row{grid-template-columns:repeat(4,1fr)}}
      @media(max-width:760px){.app-shell{display:block!important}.sidebar{position:relative!important;height:auto!important}.fs-sidebar-collapse{display:none}.appbar{position:relative!important}.fs-search{min-width:0!important}.fs-kpis{grid-template-columns:1fr 1fr}.fs-row,.fs-row.small{grid-template-columns:repeat(2,1fr)}}
    `;
    document.head.appendChild(style);
  }

  function buildTopbar() {
    const appbar = q('.appbar');
    if (!appbar) return;
    const right = q('.right', appbar);
    if (!right) return;
    right.innerHTML = `
      <input id="fsGlobalSearch" class="fs-search" type="text" placeholder="Search movies, shows, artists, albums...">
      <span class="fs-top-spacer"></span>
      <button class="fs-topbtn primary" id="fsScanBtn">◉ &nbsp; Scan Library</button>
      <button class="fs-topbtn" id="fsSettingsBtn">⚙ &nbsp; Settings</button>
      <button class="fs-topbtn" id="fsHelpBtn">? &nbsp; Help</button>
      <button class="fs-topbtn fs-update" id="fsUpdateBtn">⇩ &nbsp; Checking…</button>`;
    q('#fsScanBtn').onclick = () => window.scanNow?.();
    q('#fsSettingsBtn').onclick = () => window.openSettingsNav?.('general', q('.side-nav .nav-item'));
    q('#fsHelpBtn').onclick = () => window.openSetupWizard?.(false);
    q('#fsGlobalSearch').addEventListener('keydown', e => {
      if (e.key !== 'Enter') return;
      const value = e.currentTarget.value.trim();
      const movieBtn = qa('.side-nav button').find(b => b.textContent.trim().startsWith('Movies'));
      window.openMediaNav?.('movies', movieBtn);
      setTimeout(() => { const input = document.getElementById('mediaSearch'); if (input) { input.value = value; window.renderMedia?.(); input.focus(); } }, 80);
    });
    q('#fsUpdateBtn').onclick = async () => {
      if (window.CensorarrUpdater?.check) await window.CensorarrUpdater.check(true);
    };
  }

  function rebuildSidebar() {
    const nav = q('.side-nav');
    const sidebar = q('.sidebar');
    const shell = q('.app-shell');
    if (!nav || !sidebar || !shell) return;
    const button = (label, icon, action, count='') => `<button class="nav-item" data-fs-action="${action}"><span class="nav-icon">${icon}</span><span>${label}</span>${count ? `<span class="nav-count" id="${count}"></span>` : ''}</button>`;
    nav.innerHTML = `
      ${button('Overview','⌂','dashboard')}
      <div class="nav-section">Media</div>
      ${button('All Media','▦','all-media')}
      ${button('Movies','▤','movies')}
      ${button('TV Shows','▣','series')}
      <div class="nav-section">Processing</div>
      ${button('In Progress','◴','in-progress','fsCountProgress')}
      ${button('Waiting','◷','waiting','fsCountWaiting')}
      ${button('Needs Review','▧','review','fsCountReview')}
      ${button('Completed','☑','completed')}
      ${button('Failed','⊗','failed','fsCountFailed')}
      ${button('Dry Runs','♙','dry-run')}
      <div class="nav-section">System</div>
      <div class="nav-group open" id="fsSettingsGroup">
        <button type="button" class="nav-group-btn"><span class="nav-icon">⚙</span><span>Settings</span><span class="chev">▼</span></button>
        <button class="nav-item sub" data-fs-action="queue"><span>Queue</span><span class="nav-count" id="fsCountQueue"></span></button>
        <button class="nav-item sub" data-fs-action="workers"><span>Workers</span></button>
        <button class="nav-item sub" data-fs-action="integrations"><span>Integrations</span></button>
        <button class="nav-item sub" data-fs-action="health"><span>System Health</span></button>
      </div>`;
    const groupBtn = q('#fsSettingsGroup .nav-group-btn');
    groupBtn.onclick = () => q('#fsSettingsGroup').classList.toggle('open');
    nav.addEventListener('click', e => {
      const b = e.target.closest('[data-fs-action]');
      if (!b) return;
      qa('.side-nav .nav-item').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      runSidebarAction(b.dataset.fsAction, b);
    });
    q('[data-fs-action="dashboard"]')?.classList.add('active');
    let collapse = q('.fs-sidebar-collapse');
    if (!collapse) {
      collapse = document.createElement('button');
      collapse.className = 'fs-sidebar-collapse';
      collapse.textContent = '«';
      collapse.title = 'Collapse sidebar';
      sidebar.appendChild(collapse);
    }
    collapse.onclick = () => {
      const collapsed = shell.classList.toggle('fs-collapsed');
      collapse.textContent = collapsed ? '»' : '«';
      localStorage.setItem('censorarr-sidebar-collapsed', collapsed ? '1' : '0');
    };
    if (localStorage.getItem('censorarr-sidebar-collapsed') === '1') { shell.classList.add('fs-collapsed'); collapse.textContent = '»'; }
  }

  function historyFilter(value, button) {
    const original = qa('.side-nav button').find(x => x.dataset.title === 'History');
    window.tab?.('library', original || button);
    setTimeout(() => {
      const select = document.getElementById('historyFilter');
      if (select) { select.value = value; window.refreshHistory?.(); }
    }, 40);
  }

  function runSidebarAction(action, button) {
    if (action === 'dashboard') return window.tab?.('dashboard', button);
    if (action === 'all-media' || action === 'movies') return window.openMediaNav?.('movies', button);
    if (action === 'series') return window.openMediaNav?.('series', button);
    if (action === 'review') return window.tab?.('reviews', button);
    if (action === 'failed') return window.tab?.('failures', button);
    if (action === 'in-progress') { window.tab?.('dashboard', button); return document.getElementById('fsInProgress')?.scrollIntoView({behavior:'smooth'}); }
    if (action === 'waiting') return historyFilter('waiting-subtitle', button);
    if (action === 'completed') return historyFilter('applied', button);
    if (action === 'dry-run') return historyFilter('dry-run', button);
    if (action === 'queue') { window.tab?.('dashboard', button); return document.getElementById('fsInProgress')?.scrollIntoView({behavior:'smooth'}); }
    if (action === 'workers') return window.openSettingsNav?.('whisper', button);
    if (action === 'integrations') return window.openSetupWizard?.(false);
    if (action === 'health') { window.tab?.('dashboard', button); return document.getElementById('fsWorkerCard')?.scrollIntoView({behavior:'smooth'}); }
  }

  function buildDashboard() {
    const pane = document.getElementById('dashboardPane');
    if (!pane || document.getElementById('fsDashboard')) return;
    const legacy = document.createElement('div');
    legacy.className = 'fs-legacy';
    legacy.id = 'fsLegacyDashboard';
    [...pane.children].forEach(x => legacy.appendChild(x));
    pane.appendChild(legacy);
    const dash = document.createElement('div');
    dash.id = 'fsDashboard';
    dash.className = 'fs-dashboard';
    dash.innerHTML = `
      <div class="fs-kpis">
        ${kpi('✓','Total Processed','fsKpiTotal','Media tracked')}
        ${kpi('♫','Clean Tracks Created','fsKpiClean','CLEAN audio tracks')}
        ${kpi('⚙','Jobs In Progress','fsKpiJobs','Active processing')}
        ${kpi('▤','Queue','fsKpiQueue','Waiting to process')}
        ${kpi('♟','Worker Status','fsKpiWorkers','Transcription worker')}
      </div>
      <div class="fs-main-grid">
        <div class="fs-media-panel">
          ${mediaSection('Recently Processed','fsRecent')}
          ${mediaSection('In Progress','fsInProgress')}
          <div style="display:grid;grid-template-columns:1fr .62fr">
            ${mediaSection('Waiting for Subtitles','fsWaiting','small')}
            ${mediaSection('Needs Review','fsReview','small')}
          </div>
        </div>
        <div class="fs-side">
          <div class="fs-side-card" id="fsWorkerCard">
            <div class="fs-side-title"><h2>⚙ Worker & Transcription</h2><span class="fs-link" data-go="workers">Open Panel</span></div>
            <div class="fs-worker-grid">
              <div>
                <div class="fs-stat"><span>Model</span><b id="fsWorkerModel">—</b></div>
                <div class="fs-stat"><span>Mode</span><b id="fsWorkerMode">—</b></div>
                <div class="fs-stat"><span>Device</span><b id="fsWorkerDevice">Remote / Local</b></div>
                <div class="fs-stat"><span>Current job</span><b id="fsWorkerJob">—</b></div>
              </div>
              <div>
                <div class="fs-stat"><span>Status</span><b class="fs-online" id="fsWorkerState">—</b></div>
                <div class="fs-stat"><span>GPU progress</span><b id="fsWorkerProgress">—</b></div><div class="fs-meter"><span id="fsWorkerMeter" style="width:0%"></span></div>
                <div class="fs-stat"><span>GPU ETA</span><b id="fsWorkerEta">—</b></div>
                <div class="fs-stat"><span>Movie position</span><b id="fsWorkerPosition">—</b></div>
              </div>
            </div>
          </div>
          <div class="fs-side-card">
            <div class="fs-side-title"><h2>⌘ Integrations Status</h2><span class="fs-link" data-go="integrations">View all</span></div>
            <div class="fs-integrations" id="fsIntegrations"></div>
          </div>
          <div class="fs-side-card">
            <div class="fs-side-title"><h2>◷ Recent History</h2><span class="fs-link" data-go="history">View all</span></div>
            <table class="fs-history"><thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Finished</th></tr></thead><tbody id="fsHistoryBody"></tbody></table>
          </div>
        </div>
      </div>
      <div class="fs-tipbar"><span>💡</span><div class="fs-tiptext" id="fsTip"></div><div class="fs-tipdots" id="fsTipDots"></div><button class="fs-tipnav" id="fsTipPrev">‹</button><button class="fs-tipnav" id="fsTipNext">›</button></div>`;
    pane.insertBefore(dash, legacy);
    qa('[data-go="workers"]', dash).forEach(x => x.onclick = () => window.openSettingsNav?.('whisper', q('[data-fs-action="workers"]')));
    qa('[data-go="integrations"]', dash).forEach(x => x.onclick = () => window.openSetupWizard?.(false));
    qa('[data-go="history"]', dash).forEach(x => x.onclick = () => window.tab?.('library', q('[data-fs-action="completed"]')));
    q('#fsTipPrev').onclick = () => setTip(tipIndex - 1);
    q('#fsTipNext').onclick = () => setTip(tipIndex + 1);
    setTip(0);
  }

  function kpi(icon,label,id,sub){ return `<div class="fs-kpi"><div class="fs-kpi-icon">${icon}</div><div><div class="fs-kpi-label">${label}</div><div class="fs-kpi-value" id="${id}">—</div><div class="fs-kpi-sub">${sub}</div></div></div>`; }
  function mediaSection(title,id,size=''){ return `<div class="fs-media-section" id="${id}"><div class="fs-section-head"><h2>${title}</h2><span class="fs-link">View all</span></div><div class="fs-row ${size}" data-row></div></div>`; }

  function setTip(index) {
    tipIndex = (index + TIPS.length) % TIPS.length;
    const tip = q('#fsTip'); if (tip) tip.textContent = `Tip: ${TIPS[tipIndex]}`;
    const dots = q('#fsTipDots'); if (dots) dots.innerHTML = TIPS.map((_,i)=>`<span class="fs-tipdot ${i===tipIndex?'active':''}"></span>`).join('');
  }

  function mediaCard(x, opts={}) {
    const img = poster(x) ? `<img src="${esc(poster(x))}" loading="lazy" onerror="this.style.display='none'">` : `<div class="fs-poster-placeholder">${opts.icon || '🎬'}</div>`;
    const chip = opts.chip ? `<span class="fs-chip ${opts.chipClass||''}">${esc(opts.chip)}</span>` : '';
    const progress = opts.progress != null ? `<div class="fs-progress-ring" style="--p:${Math.max(0,Math.min(100,Number(opts.progress)))}%"><span>${Math.round(Number(opts.progress))}%</span></div>` : '';
    const kind = x?.kind || (x?.episode_file_count != null ? 'TV Show' : 'Movie');
    const sub = [itemYear(x), kind].filter(Boolean).join(' • ');
    return `<div class="fs-poster-card" data-id="${esc(x?.id ?? '')}" data-kind="${kind==='TV Show'?'series':'movie'}"><div class="fs-poster">${img}${chip}${progress}</div><div class="fs-card-title" title="${esc(itemTitle(x))}">${esc(itemTitle(x))}</div><div class="fs-card-sub">${esc(sub)}</div></div>`;
  }

  async function loadDashboardMedia() {
    try {
      const [m,s] = await Promise.all([
        fetch('/api/media-catalog?kind=movies').then(r=>r.ok?r.json():({items:[]})),
        fetch('/api/media-catalog?kind=series').then(r=>r.ok?r.json():({items:[]}))
      ]);
      mediaCache.movies = (m.items||[]).map(x=>({...x,kind:'Movie'}));
      mediaCache.series = (s.items||[]).map(x=>({...x,kind:'TV Show'}));
      renderMediaRows();
    } catch (_) { renderMediaRows(); }
  }

  function currentProgress() {
    const raw = document.getElementById('overallProgressText')?.textContent || '';
    const n = Number(raw.replace('%',''));
    return Number.isFinite(n) ? n : 0;
  }

  function currentName() { return document.getElementById('current')?.textContent?.trim() || ''; }

  function renderMediaRows() {
    const all = [...mediaCache.movies,...mediaCache.series];
    const recent = all.filter(x => statusGood(x.censorarr_status)).slice(0,6);
    const waiting = all.filter(x => statusWaiting(x.censorarr_status)).slice(0,6);
    const review = all.filter(x => statusReview(x.censorarr_status)).slice(0,3);
    const cur = currentName().toLowerCase();
    let active = all.filter(x => cur && (String(x.media_path||x.path||'').toLowerCase().includes(cur) || itemTitle(x).toLowerCase().includes(cur))).slice(0,1);
    const fill = all.filter(x => !statusGood(x.censorarr_status) && !statusWaiting(x.censorarr_status) && !statusReview(x.censorarr_status));
    active = active.concat(fill.filter(x=>!active.includes(x)).slice(0,Math.max(0,6-active.length)));
    renderRow('fsRecent', recent.length?recent:all.slice(0,6), x=>mediaCard(x,{chip:statusGood(x.censorarr_status)?'CLEAN':''}));
    renderRow('fsInProgress', active.slice(0,6), (x,i)=>mediaCard(x,{progress:i===0&&cur?currentProgress():0}));
    renderRow('fsWaiting', waiting.length?waiting:all.slice(0,6), x=>mediaCard(x,{chip:'Waiting',chipClass:'wait'}));
    renderRow('fsReview', review.length?review:all.slice(0,3), x=>mediaCard(x,{chip:'Review',chipClass:'review'}));
    qa('.fs-poster-card').forEach(card => card.onclick = () => {
      const kind = card.dataset.kind; const id = Number(card.dataset.id); if (id) window.openMediaDetail?.(kind,id);
    });
  }

  function renderRow(sectionId, items, renderer) {
    const row = q(`#${sectionId} [data-row]`); if (!row) return;
    row.innerHTML = items.length ? items.map(renderer).join('') : `<div class="fs-card-sub" style="padding:12px">No matching media yet.</div>`;
  }

  async function renderIntegrations() {
    const box = q('#fsIntegrations'); if (!box) return;
    let settings = {};
    try { settings = await fetch('/api/settings').then(r=>r.ok?r.json():{}); } catch (_) {}
    const arr = settings.arr_integrations || {}, sub = settings.subtitle_assist || {}, rf=settings.rating_filter||{}, tr=settings.tv?.rating_filter||{};
    const entries = [
      ['Sonarr',!!arr.sonarr?.enabled,'S'],['Radarr',!!arr.radarr?.enabled,'R'],['Plex',!!(rf.plex_url||tr.plex_url),'P'],['Bazarr',!!sub.bazarr?.enabled,'B'],['GPU Worker',String(settings.whisper?.backend||'local')!=='local','G'],['Subtitles',sub.enabled!==false,'CC']
    ];
    box.innerHTML = entries.map(([name,on,icon])=>`<div class="fs-int"><div class="fs-int-icon">${icon}</div><div><div class="fs-int-name">${name}</div><div class="fs-int-state" style="${on?'':'color:#7c92a2'}">${on?'Configured':'Optional'}</div></div></div>`).join('');
  }

  async function renderHistory() {
    const body = q('#fsHistoryBody'); if (!body) return;
    let rows = [];
    try {
      const r = await fetch('/api/history').then(x=>x.ok?x.json():[]);
      rows = Array.isArray(r) ? r : (r.items || r.history || []);
    } catch (_) {}
    if (!rows.length) {
      rows = [...mediaCache.movies.filter(x=>statusGood(x.censorarr_status)),...mediaCache.series.filter(x=>x.censorarr_cleaned)].slice(0,5).map(x=>({movie:itemTitle(x),status:'applied',time:x.censorarr_time,type:x.kind}));
    }
    body.innerHTML = rows.slice(0,5).map(r=>`<tr><td>${esc(r.movie||r.title||r.name||'Media')}</td><td>${esc(r.type||'Media')}</td><td><span class="fs-success">Success</span></td><td>${r.time?new Date(Number(r.time)*1000).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'}):'—'}</td></tr>`).join('') || `<tr><td colspan="4" style="color:#7890a1">No recent history.</td></tr>`;
  }

  function syncLive() {
    const total=text('total'), clean=text('cleaned'), waiting=text('waiting'), current=currentName(), state=text('gpuState');
    const set=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v};
    set('fsKpiTotal',total); set('fsKpiClean',clean); set('fsKpiJobs',current && !/No media/i.test(current)?'1':'0'); set('fsKpiQueue',waiting); set('fsKpiWorkers',/online|idle|working|busy/i.test(state)?'Online':state);
    set('fsWorkerModel',text('gpuModel')); set('fsWorkerMode',/GPU/i.test(state)?'GPU (remote)':'Whisper'); set('fsWorkerState',state); set('fsWorkerProgress',text('gpuProgress')); set('fsWorkerEta',text('gpuEta')); set('fsWorkerPosition',text('gpuPosition')); set('fsWorkerJob',text('gpuJob'));
    const p=Number((text('gpuProgress').match(/[\d.]+/)||[0])[0]); const meter=q('#fsWorkerMeter'); if(meter) meter.style.width=Math.max(0,Math.min(100,p||0))+'%';
    const cnt=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v&&v!=='0'?v:''}; cnt('fsCountWaiting',waiting); cnt('fsCountFailed',text('errors')); cnt('fsCountQueue',waiting); cnt('fsCountProgress',current && !/No media/i.test(current)?'1':''); cnt('fsCountReview',document.getElementById('reviewNavCount')?.textContent||'');
    renderMediaRows();
  }

  async function updatePill() {
    const b=q('#fsUpdateBtn'); if (!b) return;
    try {
      const s=await fetch('/api/update/status').then(r=>r.ok?r.json():null);
      if (s?.update_available) { b.innerHTML='⇩ &nbsp; Update Available'; b.style.borderColor='#ffb33b'; b.style.color='#ffd28b'; }
      else { b.innerHTML='✓ &nbsp; Up to Date'; }
    } catch (_) { b.innerHTML='↻ &nbsp; Check Updates'; }
  }

  function boot() {
    if (!q('.app-shell')) return;
    injectStyles();
    document.documentElement.dataset.theme='dark';
    rebuildSidebar();
    buildTopbar();
    buildDashboard();
    loadDashboardMedia();
    renderIntegrations();
    renderHistory();
    updatePill();
    syncLive();
    setInterval(syncLive, 1800);
    setInterval(()=>setTip(tipIndex+1), 12000);
    setInterval(updatePill, 15*60*1000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 0));
  else setTimeout(boot, 0);
})();