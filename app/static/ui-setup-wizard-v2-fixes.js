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

  function wrapOpen() {
    const current = window.openSetupWizard;
    if (typeof current !== 'function' || current.__fsV2FinishReset) return;
    const wrapped = async function() {
      const result = await current.apply(this, arguments);
      resetFinishButton();
      applyTheme();
      return result;
    };
    wrapped.__fsV2FinishReset = true;
    window.openSetupWizard = wrapped;
  }

  function boot() {
    addStyles();
    wrapOpen();
    applyTheme();
    resetFinishButton();

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
