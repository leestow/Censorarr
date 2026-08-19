(() => {
  function $(id) { return document.getElementById(id); }

  async function request(path, options) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      ...(options || {}),
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data;
  }

  function makePanel() {
    if ($('dialogueEnhancementSection')) return;
    const page = document.querySelector('.settings-page[data-settings="detection"]');
    if (!page) return;

    const section = document.createElement('div');
    section.className = 'section';
    section.id = 'dialogueEnhancementSection';
    section.innerHTML = `
      <h3>Dialogue Enhancement <span class="optional-label">Experimental</span></h3>
      <div class="setting-callout">
        Creates an additional speech-focused stereo audio track while preserving CLEAN and original audio.
        Surround sources emphasize the center/dialogue channel; all sources receive speech EQ, dynamic compression,
        and peak limiting. This first version does not use AI voice separation.
      </div>
      <div class="field">
        <label>Create Dialogue Enhanced track</label>
        <select id="sDialogueEnabled"><option value="false">Disabled</option><option value="true">Enabled</option></select>
      </div>
      <div class="split">
        <div class="field"><label>Enhancement strength</label><select id="sDialogueStrength"><option value="light">Light</option><option value="medium">Medium</option><option value="strong">Strong</option></select></div>
        <div class="field"><label>Track name</label><input id="sDialogueTitle" value="English - DIALOGUE ENHANCED"></div>
      </div>
      <div class="split">
        <div class="field"><label>Language tag</label><input id="sDialogueLanguage" value="eng"></div>
        <div class="field"><label>Audio codec</label><select id="sDialogueCodec"><option value="aac">AAC</option><option value="ac3">AC3</option><option value="eac3">E-AC3</option></select></div>
      </div>
      <div class="split">
        <div class="field"><label>Bitrate</label><select id="sDialogueBitrate"><option value="128k">128k</option><option value="160k">160k</option><option value="192k">192k</option><option value="256k">256k</option><option value="320k">320k</option><option value="384k">384k</option></select></div>
        <div class="field"><label>Replace an existing track with the same name</label><select id="sDialogueReplace"><option value="true">Yes</option><option value="false">No</option></select></div>
      </div>
      <div class="field"><label>Make Dialogue Enhanced the default audio track</label><select id="sDialogueDefault"><option value="false">No — keep CLEAN default</option><option value="true">Yes — Dialogue Enhanced becomes default</option></select></div>
      <div class="footer-note">Medium is the recommended starting point. The enhanced track is stereo for broad Plex/device compatibility.</div>
      <div class="toolbar" style="margin-top:10px"><button class="good" id="saveDialogueEnhancement">Save Dialogue Enhancement</button><span class="footer-note" id="dialogueEnhancementStatus"></span></div>
    `;
    page.appendChild(section);
    $('saveDialogueEnhancement').addEventListener('click', save);
  }

  async function load() {
    makePanel();
    if (!$('dialogueEnhancementSection')) return;
    try {
      const s = await request('/api/dialogue-enhancement/settings');
      $('sDialogueEnabled').value = String(!!s.enabled);
      $('sDialogueStrength').value = s.strength || 'medium';
      $('sDialogueTitle').value = s.title || 'English - DIALOGUE ENHANCED';
      $('sDialogueLanguage').value = s.language || 'eng';
      $('sDialogueCodec').value = s.codec || 'aac';
      const bitrate = s.bitrate || '192k';
      if (![...$('sDialogueBitrate').options].some(o => o.value === bitrate)) {
        const option = document.createElement('option'); option.value = bitrate; option.textContent = bitrate; $('sDialogueBitrate').appendChild(option);
      }
      $('sDialogueBitrate').value = bitrate;
      $('sDialogueReplace').value = String(s.replace_existing !== false);
      $('sDialogueDefault').value = String(!!s.make_default);
      $('dialogueEnhancementStatus').textContent = s.enabled ? 'Enabled for future processed media.' : 'Currently disabled.';
    } catch (err) {
      $('dialogueEnhancementStatus').textContent = `Could not load: ${err.message || err}`;
    }
  }

  async function save() {
    const btn = $('saveDialogueEnhancement');
    btn.disabled = true;
    $('dialogueEnhancementStatus').textContent = 'Saving…';
    try {
      const body = {
        enabled: $('sDialogueEnabled').value === 'true',
        strength: $('sDialogueStrength').value,
        title: $('sDialogueTitle').value.trim(),
        language: $('sDialogueLanguage').value.trim(),
        codec: $('sDialogueCodec').value,
        bitrate: $('sDialogueBitrate').value,
        replace_existing: $('sDialogueReplace').value === 'true',
        make_default: $('sDialogueDefault').value === 'true',
      };
      const result = await request('/api/dialogue-enhancement/settings', { method: 'POST', body: JSON.stringify(body) });
      $('dialogueEnhancementStatus').textContent = result.message || 'Saved.';
    } catch (err) {
      $('dialogueEnhancementStatus').textContent = `Save failed: ${err.message || err}`;
    } finally {
      btn.disabled = false;
    }
  }

  function install() {
    makePanel();
    const original = window.openSettingsNav;
    if (typeof original === 'function' && !original.__dialogueWrapped) {
      const wrapped = async function(section, el) {
        const result = await original(section, el);
        if (section === 'detection') await load();
        return result;
      };
      wrapped.__dialogueWrapped = true;
      window.openSettingsNav = wrapped;
    }
    const detection = document.querySelector('.settings-page[data-settings="detection"].active');
    if (detection) load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();

/* Redesigned UI runtime fixes: shared media metadata cache, approved logo, and compact navigation. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const cache = new Map();
  const inflight = new Map();
  const FRESH_MS = 2 * 60 * 1000;
  const STALE_MS = 30 * 60 * 1000;

  function catalogInfo(input, init={}) {
    let raw = typeof input === 'string' ? input : input?.url;
    if (!raw) return null;
    let url;
    try { url = new URL(raw, location.href); } catch (_) { return null; }
    const method = String(init.method || (typeof input !== 'string' && input?.method) || 'GET').toUpperCase();
    if (method !== 'GET' || url.pathname !== '/api/media-catalog') return null;
    const kind = url.searchParams.get('kind') || 'movies';
    return { key: kind, force: url.searchParams.get('force') === 'true' };
  }

  function responseFrom(entry) {
    return new Response(entry.body, { status: entry.status, statusText: entry.statusText, headers: entry.headers });
  }

  async function fetchCatalog(input, init, key) {
    const response = await nativeFetch(input, init);
    const body = await response.clone().text();
    const entry = {
      body,
      status: response.status,
      statusText: response.statusText,
      headers: [...response.headers.entries()],
      time: Date.now(),
    };
    if (response.ok) cache.set(key, entry);
    return entry;
  }

  window.fetch = async function(input, init={}) {
    const info = catalogInfo(input, init);
    if (!info) return nativeFetch(input, init);

    if (info.force) {
      const entry = await fetchCatalog(input, init, info.key);
      return responseFrom(entry);
    }

    const current = cache.get(info.key);
    const age = current ? Date.now() - current.time : Infinity;
    if (current && age < FRESH_MS) return responseFrom(current);

    if (current && age < STALE_MS) {
      if (!inflight.has(info.key)) {
        const job = fetchCatalog(input, init, info.key).catch(() => null).finally(() => inflight.delete(info.key));
        inflight.set(info.key, job);
      }
      return responseFrom(current);
    }

    if (!inflight.has(info.key)) {
      const job = fetchCatalog(input, init, info.key).finally(() => inflight.delete(info.key));
      inflight.set(info.key, job);
    }
    const entry = await inflight.get(info.key);
    return responseFrom(entry);
  };

  window.CensorarrMediaCache = {
    clear(kind) { if (kind) cache.delete(kind); else cache.clear(); },
    status() { return [...cache.entries()].map(([kind, value]) => ({kind, age_ms: Date.now() - value.time})); },
  };

  function addRuntimeStyle() {
    if (document.getElementById('familyRuntimeStyle')) return;
    const style = document.createElement('style');
    style.id = 'familyRuntimeStyle';
    style.textContent = `
      .side-nav{scrollbar-width:none!important;-ms-overflow-style:none!important}
      .side-nav::-webkit-scrollbar{display:none!important;width:0!important}
      .sidebar-brand{justify-content:flex-start!important;overflow:hidden!important}
      .sidebar-brand img{width:200px!important;height:42px!important;max-height:42px!important;object-fit:contain!important;object-position:left center!important}
      .fs-collapsed .sidebar-brand img{width:200px!important;max-width:none!important;object-fit:contain!important;object-position:left center!important}
      .fs-settings-menu .nav-item.sub{padding-left:44px!important;font-size:12px!important}
    `;
    document.head.appendChild(style);
  }

  function makeButton(label, icon, action, sub=false) {
    const b = document.createElement('button');
    b.className = 'nav-item' + (sub ? ' sub' : '');
    b.dataset.finalAction = action;
    if (sub) b.innerHTML = `<span>${label}</span>`;
    else b.innerHTML = `<span class="nav-icon">${icon}</span><span>${label}</span>`;
    return b;
  }

  function activate(button) {
    document.querySelectorAll('.side-nav .nav-item').forEach(x => x.classList.remove('active'));
    button?.classList.add('active');
  }

  function openHistory(button, filter='') {
    activate(button);
    window.tab?.('library', button);
    setTimeout(() => {
      const f = document.getElementById('historyFilter');
      if (f) { f.value = filter; window.refreshHistory?.(); }
    }, 20);
  }

  function runAction(action, button) {
    if (action === 'overview') { activate(button); return window.tab?.('dashboard', button); }
    if (action === 'queue') {
      activate(button); window.tab?.('dashboard', button);
      return setTimeout(() => document.getElementById('fsInProgress')?.scrollIntoView({behavior:'smooth',block:'start'}), 30);
    }
    if (action === 'libraries') { activate(button); return window.openMediaNav?.('movies', button); }
    if (action === 'rules') { activate(button); return window.openSettingsNav?.('detection', button); }
    if (action === 'profanity') { activate(button); return window.tab?.('profanity', button); }
    if (action === 'integrations') { activate(button); return window.openSetupWizard?.(false); }
    if (action === 'gpu') { activate(button); return window.openSettingsNav?.('whisper', button); }
    if (action === 'history') return openHistory(button);
    if (action === 'logs') { activate(button); return window.openSettingsNav?.('safety', button); }
    if (action.startsWith('settings:')) { activate(button); return window.openSettingsNav?.(action.split(':')[1], button); }
  }

  function rebuildSidebar() {
    const nav = document.querySelector('.side-nav');
    if (!nav || nav.dataset.finalized === '1') return;
    nav.dataset.finalized = '1';
    nav.innerHTML = '';

    const entries = [
      ['Overview','⌂','overview'],
      ['Queue','☷','queue'],
      ['Libraries','□','libraries'],
      ['Processing Rules','☷','rules'],
      ['Profanity List','◇','profanity'],
      ['Integrations','⬡','integrations'],
      ['GPU Worker','⚙','gpu'],
      ['History','◷','history'],
      ['Logs','▤','logs'],
    ];
    entries.forEach(([label,icon,action]) => nav.appendChild(makeButton(label,icon,action)));

    const group = document.createElement('div');
    group.className = 'nav-group fs-settings-menu';
    group.innerHTML = '<button type="button" class="nav-group-btn"><span class="nav-icon">⚙</span><span>Settings</span><span class="chev">▼</span></button>';
    const settings = [
      ['General','general'],['Movies','movies'],['TV Shows','tv'],['Transcription','whisper'],['Detection','detection'],
      ['Subtitles','subtitles'],['Plex','plex'],['Notifications','notifications'],['File Safety & Logs','safety'],['Backup & About','backup']
    ];
    settings.forEach(([label,section]) => group.appendChild(makeButton(label,'',`settings:${section}`,true)));
    nav.appendChild(group);
    group.querySelector('.nav-group-btn').onclick = () => group.classList.toggle('open');

    nav.addEventListener('click', e => {
      const button = e.target.closest('[data-final-action]');
      if (!button) return;
      runAction(button.dataset.finalAction, button);
    });
    nav.querySelector('[data-final-action="overview"]')?.classList.add('active');
  }

  function wireViewAll() {
    const bind = (selector, fn) => {
      const el = document.querySelector(selector);
      if (!el || el.dataset.wired === '1') return;
      el.dataset.wired = '1';
      el.onclick = fn;
    };
    bind('#fsRecent .fs-link', () => openHistory(document.querySelector('[data-final-action="history"]')));
    bind('#fsWaiting .fs-link', () => openHistory(document.querySelector('[data-final-action="history"]'), 'waiting-subtitle'));
    bind('#fsReview .fs-link', () => {
      const b = document.querySelector('[data-final-action="profanity"]');
      activate(b); window.tab?.('reviews', b);
    });
    bind('#fsInProgress .fs-link', () => runAction('queue', document.querySelector('[data-final-action="queue"]')));
  }

  function applyBrand() {
    const img = document.querySelector('.sidebar-brand img');
    if (img && !img.src.includes('censorarr-logo-wave.svg')) img.src = '/assets/censorarr-logo-wave.svg?v=3';
  }

  function applyUi() {
    addRuntimeStyle();
    applyBrand();
    rebuildSidebar();
    wireViewAll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      setTimeout(applyUi, 60);
      setTimeout(wireViewAll, 500);
    });
  } else {
    setTimeout(applyUi, 60);
    setTimeout(wireViewAll, 500);
  }
})();
