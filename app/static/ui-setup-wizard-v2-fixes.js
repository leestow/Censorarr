(() => {
  'use strict';
  if (window.__censorarrSetupWizardV2Fixes) return;
  window.__censorarrSetupWizardV2Fixes = true;

  const $ = id => document.getElementById(id);
  const q = (sel, root=document) => root.querySelector(sel);
  const qa = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  function addStyles() {
    if ($('fsWizardV2DaylightStyles')) return;
    const style = document.createElement('style');
    style.id = 'fsWizardV2DaylightStyles';
    style.textContent = `
      .settings-page[data-settings="general"].fs-general-organized:not(.active){display:none!important}
      .settings-page[data-settings="general"].fs-general-organized.active{display:grid!important}

      #setupModal.fs-v2-daylight>.dialog.setup-dialog{background:#f3f7fb!important;border-color:#cbdde7!important}
      #setupModal.fs-v2-daylight .fs-v2-shell{background:#f3f7fb!important;color:#142435!important}
      #setupModal.fs-v2-daylight .fs-v2-body{background:#f3f7fb!important;color:#142435!important}
      #setupModal.fs-v2-daylight .fs-v2-body h2{color:#142435!important}
      #setupModal.fs-v2-daylight .fs-v2-lead{color:#657d8e!important}
      #setupModal.fs-v2-daylight .fs-v2-side{background:#edf4f8!important;border-left-color:#d2e0e8!important;color:#142435!important}
      #setupModal.fs-v2-daylight .fs-v2-side-card,
      #setupModal.fs-v2-daylight .fs-v2-question,
      #setupModal.fs-v2-daylight .fs-v2-section,
      #setupModal.fs-v2-daylight .fs-v2-review>div{background:#fff!important;border-color:#d5e2ea!important;color:#142435!important}
      #setupModal.fs-v2-daylight .fs-v2-side-card h3,
      #setupModal.fs-v2-daylight .fs-v2-section h3,
      #setupModal.fs-v2-daylight .fs-v2-review b,
      #setupModal.fs-v2-daylight .fs-v2-question-text{color:#142435!important}
      #setupModal.fs-v2-daylight .fs-v2-summary,
      #setupModal.fs-v2-daylight .fs-v2-section p,
      #setupModal.fs-v2-daylight .fs-v2-review span,
      #setupModal.fs-v2-daylight .fs-v2-field label{color:#687f90!important}
      #setupModal.fs-v2-daylight .fs-v2-qnum{border-color:#c4d5df!important;color:#657f90!important;background:#f5f9fb!important}
      #setupModal.fs-v2-daylight .fs-v2-options button{background:#f4f8fb!important;color:#405d70!important;border-color:#c9d9e3!important}
      #setupModal.fs-v2-daylight .fs-v2-options button.active{background:#dff6f1!important;color:#08685f!important;border-color:#25bcae!important}
      #setupModal.fs-v2-daylight .fs-v2-input{background:#fff!important;color:#142435!important;border-color:#c7d8e2!important}
      #setupModal.fs-v2-daylight .fs-v2-input:focus{border-color:#337eea!important;box-shadow:0 0 0 2px rgba(51,126,234,.10)!important}
      #setupModal.fs-v2-daylight .fs-v2-callout{background:#eef7f7!important;color:#4e6878!important}
      #setupModal.fs-v2-daylight .fs-v2-callout.good{background:#edf9f3!important}
      #setupModal.fs-v2-daylight .fs-v2-callout.warn{background:#fff8e8!important}
      #setupModal.fs-v2-daylight .fs-v2-guide{border-top-color:#d7e3ea!important}
      #setupModal.fs-v2-daylight .fs-v2-guide ol{color:#587181!important}
      #setupModal.fs-v2-daylight .fs-v2-foot{background:#f8fbfd!important;border-top-color:#d3e1e9!important}
      #setupModal.fs-v2-daylight .fs-v2-back{background:#fff!important;color:#29485d!important;border-color:#c7d9e3!important}
      #setupModal.fs-v2-daylight .fs-v2-notice{color:#17865d!important}
      #setupModal.fs-v2-daylight .fs-v2-notice.bad{color:#c83e3e!important}

      .fs-v2-services-grid{display:grid;grid-template-columns:repeat(4,minmax(185px,1fr));gap:12px;margin:14px 0}
      .fs-v2-service-card{margin:0!important;padding:14px!important;display:flex;flex-direction:column;min-width:0;background:linear-gradient(145deg,#0a2433,#091c29)!important;border:1px solid #24485b!important;box-shadow:0 8px 24px rgba(0,0,0,.16)}
      .fs-v2-service-head{display:grid;grid-template-columns:42px minmax(0,1fr) auto;gap:10px;align-items:center;margin-bottom:12px}
      .fs-v2-service-logo{width:42px;height:42px;border-radius:9px;display:grid;place-items:center;background:#0d3041;border:1px solid #285265;padding:6px}
      .fs-v2-service-logo img{display:block;max-width:100%;max-height:100%;object-fit:contain}
      .fs-v2-service-title{font-size:14px;font-weight:850;color:#f0f8fb;line-height:1.2}
      .fs-v2-service-sub{margin-top:2px;font-size:9px;color:#88a7b5}
      .fs-v2-service-badge{font-size:9px;font-weight:800;padding:4px 7px;border-radius:5px;color:#80d8a6;background:#123d2c;border:1px solid #235d42;white-space:nowrap}
      .fs-v2-service-badge.skipped{color:#9bb0ba;background:#142b36;border-color:#31505d}
      .fs-v2-service-badge.connected{color:#b8f2ca;background:#174b31;border-color:#2c7750}
      .fs-v2-service-card>h3,.fs-v2-service-card>p{display:none!important}
      .fs-v2-service-card .fs-v2-grid2{grid-template-columns:1fr!important;gap:9px!important}
      .fs-v2-service-card .fs-v2-field label{font-size:9px!important}
      .fs-v2-service-card .fs-v2-input{height:34px!important;font-size:10px!important}
      .fs-v2-service-card .fs-v2-test{display:grid;grid-template-columns:1fr;gap:5px;margin-top:auto;padding-top:10px}
      .fs-v2-service-card .fs-v2-test button{width:100%;background:#1856be!important;border-color:#2c72de!important;color:#fff!important;font-weight:800}
      .fs-v2-service-card .fs-v2-status{margin:0;min-height:14px;line-height:1.3}
      .fs-v2-service-skipped-copy{margin:auto 0;color:#8da6b2;font-size:10px;line-height:1.5}
      .fs-v2-service-guides{border:1px solid #1d4556;border-radius:8px;overflow:hidden;margin-top:12px}
      .fs-v2-service-guides .fs-v2-guide{margin:0!important;padding:0!important;border:0!important;border-bottom:1px solid #1d4556!important;background:#09202d}
      .fs-v2-service-guides .fs-v2-guide:last-child{border-bottom:0!important}
      .fs-v2-service-guides .fs-v2-guide summary{padding:11px 13px!important;display:flex;align-items:center;gap:8px;color:#72b6ff!important}
      .fs-v2-service-guides .fs-v2-guide ol,.fs-v2-service-guides .fs-v2-guide img{margin-left:13px;margin-right:13px}
      .fs-v2-service-guides .fs-v2-guide img{margin-bottom:13px;max-width:calc(100% - 26px)}
      #setupModal.fs-v2-daylight .fs-v2-service-card{background:#fff!important;border-color:#ccdce6!important;box-shadow:0 5px 18px rgba(41,67,84,.08)!important}
      #setupModal.fs-v2-daylight .fs-v2-service-logo{background:#f3f7fa!important;border-color:#d3e1e9!important}
      #setupModal.fs-v2-daylight .fs-v2-service-title{color:#142435!important}
      #setupModal.fs-v2-daylight .fs-v2-service-sub{color:#6d8392!important}
      #setupModal.fs-v2-daylight .fs-v2-service-guides{border-color:#d4e1e9!important}
      #setupModal.fs-v2-daylight .fs-v2-service-guides .fs-v2-guide{background:#fff!important;border-color:#d4e1e9!important}
      @media(max-width:1250px){.fs-v2-services-grid{grid-template-columns:repeat(2,minmax(220px,1fr))}}
      @media(max-width:760px){.fs-v2-services-grid{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function isDaylight() {
    const wrap = q('.wrap');
    if (wrap?.classList.contains('fs-content-light')) return true;
    return localStorage.getItem('censorarr-content-theme') === 'light';
  }

  function applyTheme() {
    const modal = $('setupModal');
    if (modal) modal.classList.toggle('fs-v2-daylight', isDaylight());
  }

  function resetFinishButton() {
    const modal = $('setupModal');
    const button = $('fsWizardV2Finish');
    if (modal?.classList.contains('open') && button) button.disabled = false;
  }

  function showFinishStatus(message, bad=false) {
    const legacy = $('wFinishStatus');
    if (legacy) {
      legacy.textContent = bad ? `Could not finish setup: ${message}` : message;
      legacy.style.color = bad ? 'var(--bad)' : 'var(--accent)';
    }
    const visible = $('fsWizardV2Notice');
    if (visible) {
      visible.textContent = bad ? `Could not finish setup: ${message}` : message;
      visible.classList.toggle('bad', bad);
    }
  }

  async function jsonRequest(path, options={}) {
    const response = await fetch(path, {
      credentials: 'same-origin',
      headers: {'Content-Type':'application/json'},
      ...options
    });
    let data = {};
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    return data;
  }

  function sameBool(a,b) { return !!a === !!b; }

  function verifyCoreSettings(expected, saved) {
    const mismatches = [];
    const check = (label, ok) => { if (!ok) mismatches.push(label); };
    check('existing-library processing', sameBool(expected.process_existing, saved.process_existing));
    check('TV library', sameBool(expected.tv?.enabled, saved.tv?.enabled));
    check('movie rating policy', sameBool(expected.rating_filter?.enabled, saved.rating_filter?.enabled));
    check('TV rating policy', sameBool(expected.tv?.rating_filter?.enabled, saved.tv?.rating_filter?.enabled));
    check('transcription backend', String(expected.whisper?.backend || '') === String(saved.whisper?.backend || ''));
    check('Plex playback pause', sameBool(expected.plex_activity?.pause_when_streaming, saved.plex_activity?.pause_when_streaming));
    check('Radarr', sameBool(expected.arr_integrations?.radarr?.enabled, saved.arr_integrations?.radarr?.enabled));
    check('Sonarr', sameBool(expected.arr_integrations?.sonarr?.enabled, saved.arr_integrations?.sonarr?.enabled));
    check('Bazarr', sameBool(expected.subtitle_assist?.bazarr?.enabled, saved.subtitle_assist?.bazarr?.enabled));
    if (mismatches.length) throw new Error(`Saved settings did not verify: ${mismatches.join(', ')}`);
  }

  async function refreshAudioFeatureUi() {
    const state = await jsonRequest('/api/dialogue-enhancement/settings', {cache:'no-store'});
    const profanity = state.profanity_censoring_enabled !== false;
    const dialogue = !!state.enabled;
    qa('.fsProfanityToggle').forEach(x => { x.checked = profanity; });
    qa('.fsDialogueToggle').forEach(x => { x.checked = dialogue; });
    qa('[data-feature-card="profanity"]').forEach(card => {
      card.classList.toggle('on', profanity);
      const stateEl = q('.fs-feature-state', card);
      if (stateEl) stateEl.textContent = profanity ? 'ON' : 'OFF';
    });
    qa('[data-feature-card="dialogue"]').forEach(card => {
      card.classList.toggle('on', dialogue);
      const stateEl = q('.fs-feature-state', card);
      if (stateEl) stateEl.textContent = dialogue ? 'ON' : 'OFF';
    });
    const oldDialogue = $('sDialogueEnabled');
    if (oldDialogue) oldDialogue.value = String(dialogue);
    qa('.fs-feature-save-state').forEach(x => {
      x.textContent = 'Updated from Setup Wizard.';
      x.classList.add('good');
      x.classList.remove('bad');
    });
  }

  const SERVICE_META = {
    Plex:   {kind:'plex',   logo:'/assets/plex.svg',   desc:'Media server'},
    Radarr: {kind:'radarr', logo:'/assets/radarr.svg', desc:'Movie management'},
    Sonarr: {kind:'sonarr', logo:'/assets/sonarr.svg', desc:'TV management'},
    Bazarr: {kind:'bazarr', logo:'/assets/bazarr.svg', desc:'Subtitle management'}
  };

  function updateServiceBadge(card) {
    const badge = q('.fs-v2-service-badge', card);
    if (!badge) return;
    const text = q('.fs-v2-status', card)?.textContent?.trim() || '';
    if (/connected|responding|test complete/i.test(text)) {
      badge.textContent = 'Connected';
      badge.classList.add('connected');
      badge.classList.remove('skipped');
      return;
    }
    if (card.dataset.serviceSkipped === '1') {
      badge.textContent = 'Skipped';
      badge.classList.add('skipped');
      badge.classList.remove('connected');
      return;
    }
    const url = q('input[data-mirror$="Url"]', card)?.value?.trim();
    badge.textContent = url ? 'Configured' : 'Needs setup';
    badge.classList.remove('skipped','connected');
  }

  function decoratePremiumServices() {
    const body = $('fsWizardV2Body');
    if (!body || q('.fs-v2-services-grid', body)) return;
    const heading = q('h2', body)?.textContent?.trim().toLowerCase();
    if (heading !== 'connect your media services') return;

    const sections = qa(':scope > .fs-v2-section', body).filter(section => SERVICE_META[q('h3', section)?.textContent?.trim()]);
    if (!sections.length) return;

    const grid = document.createElement('div');
    grid.className = 'fs-v2-services-grid';
    const guides = document.createElement('div');
    guides.className = 'fs-v2-service-guides';

    for (const section of sections) {
      const title = q('h3', section)?.textContent?.trim();
      const meta = SERVICE_META[title];
      if (!meta) continue;
      const skipped = /Skipped based on your Usage answers/i.test(section.textContent || '');
      section.classList.add('fs-v2-service-card');
      section.dataset.serviceKind = meta.kind;
      section.dataset.serviceSkipped = skipped ? '1' : '0';

      const head = document.createElement('div');
      head.className = 'fs-v2-service-head';
      head.innerHTML = `<div class="fs-v2-service-logo"><img src="${meta.logo}" alt=""></div><div><div class="fs-v2-service-title">${title}</div><div class="fs-v2-service-sub">${meta.desc}</div></div><span class="fs-v2-service-badge"></span>`;
      section.prepend(head);

      if (skipped) {
        const p = q(':scope > p', section);
        const copy = document.createElement('div');
        copy.className = 'fs-v2-service-skipped-copy';
        copy.textContent = 'Skipped based on your Usage answers. You can enable it later from Settings.';
        if (p) p.insertAdjacentElement('afterend', copy); else section.appendChild(copy);
      }

      const guide = q(':scope > .fs-v2-guide', section);
      if (guide) {
        const summary = q('summary', guide);
        if (summary) summary.textContent = `${title} — show me exactly where to get this`;
        guides.appendChild(guide);
      }

      const status = q('.fs-v2-status', section);
      if (status) new MutationObserver(() => updateServiceBadge(section)).observe(status, {childList:true,subtree:true,characterData:true});
      qa('input', section).forEach(input => input.addEventListener('input', () => updateServiceBadge(section)));
      updateServiceBadge(section);
      grid.appendChild(section);
    }

    const lead = q('.fs-v2-lead', body);
    if (lead) lead.insertAdjacentElement('afterend', grid); else body.prepend(grid);
    if (guides.children.length) grid.insertAdjacentElement('afterend', guides);
  }

  function installVerifiedFinish() {
    if (window.finishSetupWizard?.__fsVerifiedSave) return;
    const replacement = async function() {
      const legacyButton = $('wizardFinish');
      const v2Button = $('fsWizardV2Finish');
      if (legacyButton) legacyButton.disabled = true;
      if (v2Button) v2Button.disabled = true;
      showFinishStatus('Saving setup and verifying changes…');
      try {
        if (typeof window.wizardCoreBody !== 'function') throw new Error('Setup settings builder is unavailable.');
        const body = window.wizardCoreBody();
        await jsonRequest('/api/settings', {method:'POST', body:JSON.stringify(body)});
        const saved = await jsonRequest('/api/settings', {cache:'no-store'});
        verifyCoreSettings(body, saved);
        const preflight = await jsonRequest('/api/system/preflight', {cache:'no-store'});
        if (!preflight.ok) {
          const message = (preflight.errors || []).join(' · ') || 'Censorarr cannot access the configured media folders.';
          throw new Error(message);
        }
        const complete = await jsonRequest('/api/setup/complete', {method:'POST', body:'{}'});
        await refreshAudioFeatureUi();
        showFinishStatus(complete.message || 'Setup complete. Your changes were saved.');
        try { WIZARD_FIRST_RUN = false; } catch (_) {}
        setTimeout(async () => {
          const modal = $('setupModal');
          modal?.classList.remove('open','fs-v2-open');
          if (legacyButton) legacyButton.disabled = false;
          if (v2Button) v2Button.disabled = false;
          try { await window.loadSettings?.(); } catch (_) {}
          try { await refreshAudioFeatureUi(); } catch (_) {}
          try { window.refresh?.(); } catch (_) {}
          try { window.refreshGpuStatus?.(); } catch (_) {}
        }, 350);
        return complete;
      } catch (err) {
        if (legacyButton) legacyButton.disabled = false;
        if (v2Button) v2Button.disabled = false;
        showFinishStatus(err.message || String(err), true);
        throw err;
      }
    };
    replacement.__fsVerifiedSave = true;
    window.finishSetupWizard = replacement;
  }

  function wrapOpen() {
    const current = window.openSetupWizard;
    if (typeof current !== 'function' || current.__fsV2FinishReset) return;
    const wrapped = async function() {
      const result = await current.apply(this, arguments);
      resetFinishButton();
      applyTheme();
      installVerifiedFinish();
      setTimeout(decoratePremiumServices, 0);
      return result;
    };
    wrapped.__fsV2FinishReset = true;
    window.openSetupWizard = wrapped;
  }

  function applyOverviewLayout() {
    const panel = q('#fsDashboard .fs-media-panel');
    const inProgress = $('fsInProgress');
    const waiting = $('fsWaiting');
    const recent = $('fsRecent');
    const review = $('fsReview');
    if (!panel || !inProgress || !waiting || !recent) return false;

    const reviewWrap = review?.parentElement;
    panel.insertBefore(inProgress, panel.firstChild);
    inProgress.insertAdjacentElement('afterend', waiting);
    waiting.insertAdjacentElement('afterend', recent);
    waiting.querySelector('.fs-row')?.classList.remove('small');
    if (reviewWrap && reviewWrap !== panel) reviewWrap.style.display = 'none';
    return true;
  }

  function boot() {
    addStyles();
    installVerifiedFinish();
    wrapOpen();
    applyTheme();
    resetFinishButton();
    applyOverviewLayout();
    setTimeout(applyOverviewLayout, 500);
    setTimeout(applyOverviewLayout, 1400);
    setTimeout(applyOverviewLayout, 3000);

    const wrap = q('.wrap');
    if (wrap) new MutationObserver(applyTheme).observe(wrap, {attributes:true, attributeFilter:['class']});

    const body = $('fsWizardV2Body');
    if (body) {
      new MutationObserver(() => setTimeout(decoratePremiumServices, 0)).observe(body, {childList:true,subtree:false});
      setTimeout(decoratePremiumServices, 0);
    }

    const modal = $('setupModal');
    if (modal) {
      new MutationObserver(() => {
        if (modal.classList.contains('open')) resetFinishButton();
        applyTheme();
        setTimeout(decoratePremiumServices, 0);
      }).observe(modal, {attributes:true, attributeFilter:['class']});
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 20), {once:true});
  else setTimeout(boot, 20);
})();