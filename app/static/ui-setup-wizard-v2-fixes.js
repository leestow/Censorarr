(() => {
  'use strict';
  if (window.__censorarrSetupWizardV2Fixes) return;
  window.__censorarrSetupWizardV2Fixes = true;

  const $ = id => document.getElementById(id);
  const q = sel => document.querySelector(sel);

  function addStyles() {
    if ($('fsWizardV2DaylightStyles')) return;
    const style = document.createElement('style');
    style.id = 'fsWizardV2DaylightStyles';
    style.textContent = `
      /* Daylight follows Censorarr's content theme. Keep the wizard header and step rail
         dark, just like the app keeps its top bar and sidebar unchanged. */
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
        showFinishStatus(complete.message || 'Setup complete. Your changes were saved.');
        try { WIZARD_FIRST_RUN = false; } catch (_) {}
        setTimeout(() => {
          const modal = $('setupModal');
          modal?.classList.remove('open','fs-v2-open');
          if (legacyButton) legacyButton.disabled = false;
          if (v2Button) v2Button.disabled = false;
          try { window.loadSettings?.(); } catch (_) {}
          try { window.refresh?.(); } catch (_) {}
          try { window.refreshGpuStatus?.(); } catch (_) {}
        }, 450);
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

    // Review mode is retired from the family-safe overview. Keep the hidden DOM node
    // available to older render/wiring code so it cannot break the other dashboard rows.
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

    const modal = $('setupModal');
    if (modal) {
      new MutationObserver(() => {
        if (modal.classList.contains('open')) resetFinishButton();
        applyTheme();
      }).observe(modal, {attributes:true, attributeFilter:['class']});
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 20), {once:true});
  else setTimeout(boot, 20);
})();