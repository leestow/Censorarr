(() => {
  'use strict';

  let folderMode = false;
  let folderTarget = null;
  let folderKind = 'movies';
  let folderParent = null;
  let folderPlatform = 'posix';
  const originalBrowse = browse;
  const originalOpenBrowser = openBrowser;
  const originalApi = api;

  function byId(id) { return document.getElementById(id); }

  function addBrowseButton(inputId, kind) {
    const input = byId(inputId);
    if (!input || input.dataset.folderPickerReady === '1') return;
    input.dataset.folderPickerReady = '1';
    const holder = document.createElement('div');
    holder.className = 'checkrow';
    input.parentNode.insertBefore(holder, input);
    holder.appendChild(input);
    input.style.flex = '1';
    input.style.minWidth = '0';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = 'Browse…';
    btn.addEventListener('click', () => openFolderBrowser(inputId, kind));
    holder.appendChild(btn);
  }

  function prepareBrowserModal() {
    const modal = byId('browserModal');
    if (!modal) return;
    const head = modal.querySelector('.browser-head');
    if (!head || byId('folderPickerSelect')) return;

    const rootBar = document.createElement('span');
    rootBar.id = 'folderPickerRoots';
    rootBar.className = 'toolbar hidden';
    const pathInput = byId('browsePath');
    head.insertBefore(rootBar, pathInput);

    const select = document.createElement('button');
    select.id = 'folderPickerSelect';
    select.type = 'button';
    select.className = 'good hidden';
    select.textContent = 'Select this folder';
    select.addEventListener('click', selectFolder);
    head.appendChild(select);
  }

  function setFolderLabels() {
    const settingsMovie = byId('sRoot');
    const settingsTv = byId('sTvRoot');
    const wizardMovie = byId('wMoviesRoot');
    const wizardTv = byId('wTvRoot');
    for (const [input, label] of [[settingsMovie, 'Movies folder'], [settingsTv, 'TV folder'], [wizardMovie, 'Movies folder'], [wizardTv, 'TV folder']]) {
      const lab = input?.closest('.field')?.querySelector('label');
      if (lab) {
        const help = lab.querySelector('.help-icon');
        lab.childNodes[0].textContent = label + ' ';
        if (help) {
          help.dataset.tip = label.startsWith('Movies')
            ? 'Docker/Synology normally uses /media. Native Windows can use a local drive, mapped drive, or UNC path.'
            : 'Docker/Synology normally uses /tv. Native Windows can use a local drive, mapped drive, or UNC path.';
        }
      }
    }
    const wizardLead = byId('wMoviesRoot')?.closest('.wizard-step')?.querySelector('.wizard-lead');
    if (wizardLead) wizardLead.innerHTML = 'Choose the folders Censorarr can access. Docker/Synology normally uses mounted paths such as <b>/media</b> and <b>/tv</b>. Native Windows can use local drives, mapped drives, or UNC network paths.';
    if (typeof SETTING_HELP !== 'undefined') {
      SETTING_HELP.sRoot = 'Movies library path Censorarr can access. Docker/Synology normally uses /media; native Windows can use a local drive, mapped drive, or UNC path.';
      SETTING_HELP.sTvRoot = 'TV library path Censorarr can access. Docker/Synology normally uses /tv; native Windows can use a local drive, mapped drive, or UNC path.';
    }
  }

  function browserTitle(text) {
    const title = byId('browserModal')?.querySelector('.dialog-head h2');
    if (title) title.textContent = text;
  }

  function browserNote(text) {
    const modal = byId('browserModal');
    const notes = modal?.querySelectorAll('.footer-note');
    if (notes?.length) notes[notes.length - 1].textContent = text;
  }

  function showOriginalQuickButtons(show) {
    const head = byId('browserModal')?.querySelector('.browser-head');
    if (!head) return;
    const buttons = Array.from(head.querySelectorAll(':scope > button'));
    // Original order: Up, Movies, TV Shows, Go. Added Select is last.
    for (const b of buttons.slice(1, 3)) b.classList.toggle('hidden', !show);
  }

  function renderRoots(roots, forceVisible = false) {
    const bar = byId('folderPickerRoots');
    if (!bar) return;
    bar.classList.toggle('hidden', !(folderMode || forceVisible));
    bar.innerHTML = '';
    for (const root of (roots || []).slice(0, 16)) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'small';
      btn.textContent = folderPlatform === 'windows' ? root : (root === '/media' ? 'Movies' : root === '/tv' ? 'TV Shows' : root);
      btn.addEventListener('click', () => folderMode ? folderBrowse(root) : originalBrowse(root));
      bar.appendChild(btn);
    }
  }

  async function folderBrowse(path = '') {
    const r = await originalApi('/api/folders/browse?path=' + encodeURIComponent(path || ''));
    folderPlatform = r.platform || 'posix';
    folderParent = r.parent;
    byId('browsePath').value = r.path || '';
    const select = byId('folderPickerSelect');
    if (select) select.disabled = !r.path;
    renderRoots(r.roots || []);
    const list = byId('browserList');
    list.innerHTML = (r.items || []).map(x =>
      `<div class="entry" data-folder-path="${esc(x.path)}"><span>📁 ${esc(x.name)}</span><span class="muted"></span></div>`
    ).join('') || '<div class="entry muted">No subfolders here. You can select the current folder.</div>';
    list.querySelectorAll('[data-folder-path]').forEach(el => el.addEventListener('click', () => folderBrowse(el.dataset.folderPath)));
  }

  window.openFolderBrowser = async function(targetId, kind = 'movies') {
    prepareBrowserModal();
    folderMode = true;
    folderTarget = targetId;
    folderKind = kind;
    browserTitle('Choose ' + (kind === 'tv' ? 'TV Shows' : 'Movies') + ' folder');
    browserNote('Choose a folder Censorarr can access. On native Windows you can type a UNC network path directly and click Go.');
    showOriginalQuickButtons(false);
    byId('folderPickerSelect')?.classList.remove('hidden');
    byId('folderPickerRoots')?.classList.remove('hidden');
    byId('browserModal').classList.add('open');
    const current = byId(targetId)?.value?.trim() || '';
    try { await folderBrowse(current); }
    catch (_) { await folderBrowse(''); }
  };

  window.browse = async function(path = '') {
    if (!folderMode) return originalBrowse(path);
    try { await folderBrowse(path); }
    catch (e) { alert(e.message); }
  };

  window.browseUp = function() {
    if (!folderMode) {
      if (BROWSE_PARENT) originalBrowse(BROWSE_PARENT);
      return;
    }
    if (folderParent) folderBrowse(folderParent);
    else if (folderPlatform === 'windows') folderBrowse('');
  };

  async function selectFolder() {
    const path = byId('browsePath')?.value?.trim();
    if (!path || !folderTarget) return;
    byId(folderTarget).value = path;
    if (folderTarget === 'sRoot') {
      if (byId('sRadTo')) byId('sRadTo').value = path;
      if (byId('sBazTo')) byId('sBazTo').value = path;
    } else if (folderTarget === 'sTvRoot') {
      if (byId('sSonTo')) byId('sSonTo').value = path;
      if (byId('sBazTvTo')) byId('sBazTvTo').value = path;
    }
    folderMode = false;
    folderTarget = null;
    closeModal('browserModal');
  }

  // Manual Process Media should start from the configured library on native Windows,
  // rather than assuming the Docker-only /media path.
  window.openBrowser = async function(root = '') {
    folderMode = false;
    folderTarget = null;
    prepareBrowserModal();
    browserTitle('Process a specific media file');
    browserNote('Manual processing works for either a movie or an episode and bypasses automatic pause/schedule/subtitle waiting, which is useful for testing.');
    byId('folderPickerSelect')?.classList.add('hidden');
    try {
      const r = await originalApi('/api/media-roots');
      folderPlatform = r.platform || 'posix';
      const available = (r.configured && r.configured.length ? r.configured : r.roots) || [];
      if (!root) root = available[0] || '/media';
      if (folderPlatform === 'windows') {
        showOriginalQuickButtons(false);
        renderRoots(available, true);
      } else {
        showOriginalQuickButtons(true);
        byId('folderPickerRoots')?.classList.add('hidden');
      }
    } catch (_) {
      if (!root) root = '/media';
      showOriginalQuickButtons(true);
      byId('folderPickerRoots')?.classList.add('hidden');
    }
    return originalOpenBrowser(root);
  };

  // Keep every integration mapping destination synchronized with the selected local
  // library root. This matters on native Windows where the target is D:\\Movies, etc.
  api = async function(url, opt = {}) {
    if (url === '/api/settings' && String(opt.method || 'GET').toUpperCase() === 'POST' && opt.body) {
      try {
        const body = JSON.parse(opt.body);
        const movies = body.media_roots?.[0];
        const tv = body.tv?.media_roots?.[0];
        const setTo = (mapping, value) => { if (mapping?.[0] && value) mapping[0].to = value; };
        setTo(body.rating_filter?.plex_path_mappings, movies);
        setTo(body.tv?.rating_filter?.plex_path_mappings, tv);
        setTo(body.arr_integrations?.radarr?.path_mappings, movies);
        setTo(body.arr_integrations?.sonarr?.path_mappings, tv);
        setTo(body.subtitle_assist?.bazarr?.path_mappings, movies);
        setTo(body.subtitle_assist?.bazarr?.tv_path_mappings, tv);
        opt = { ...opt, body: JSON.stringify(body) };
      } catch (_) { /* preserve the original request if it is not JSON */ }
    }
    return originalApi(url, opt);
  };

  prepareBrowserModal();
  addBrowseButton('sRoot', 'movies');
  addBrowseButton('sTvRoot', 'tv');
  addBrowseButton('wMoviesRoot', 'movies');
  addBrowseButton('wTvRoot', 'tv');
  setFolderLabels();
})();
