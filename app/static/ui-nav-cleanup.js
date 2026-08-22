(() => {
  const q = (s, root=document) => root.querySelector(s);
  const qa = (s, root=document) => [...root.querySelectorAll(s)];

  function addStyles() {
    if (q('#fsNavCleanupStyles')) return;
    const style = document.createElement('style');
    style.id = 'fsNavCleanupStyles';
    style.textContent = `
      /* Logs is a dedicated log viewer, not a second copy of GPU Worker. */
      #fsOperationsPane.fs-nav-logs .fs-ops-toolbar,
      #fsOperationsPane.fs-nav-logs .fs-nav-status-grid,
      #fsOperationsPane.fs-nav-logs .fs-nav-queue-panel{display:none!important}
      #fsOperationsPane.fs-nav-logs .fs-nav-bottom-grid{grid-template-columns:minmax(0,1fr)!important}
      #fsOperationsPane.fs-nav-logs .fs-nav-log-panel{grid-column:1/-1!important}

      /* GPU Worker is worker-focused. Its log is always the GPU log, so the source picker is noise. */
      #fsOperationsPane.fs-nav-gpu .fs-ops-segment{display:none!important}
    `;
    document.head.appendChild(style);
  }

  function removeDuplicateDetectionNav() {
    /* Processing Rules is the public navigation entry for the detection settings page. */
    qa('[data-polish-action="settings:detection"]').forEach(el => el.remove());
    qa('[data-final-action="settings:detection"]').forEach(el => el.remove());
  }

  function tagOperationsLayout() {
    const pane = q('#fsOperationsPane');
    if (!pane) return null;
    const grids = qa(':scope > .fs-ops-grid', pane);
    grids[0]?.classList.add('fs-nav-status-grid');
    grids[1]?.classList.add('fs-nav-bottom-grid');
    if (grids[1]) {
      const panels = qa(':scope > .fs-ops-panel', grids[1]);
      panels[0]?.classList.add('fs-nav-log-panel');
      panels[1]?.classList.add('fs-nav-queue-panel');
    }
    return pane;
  }

  function currentOperationsMode() {
    if (q('[data-polish-action="gpu"].active,[data-final-action="gpu"].active')) return 'gpu';
    if (q('[data-polish-action="logs"].active,[data-final-action="logs"].active')) return 'logs';
    const title = q('#pageTitle')?.textContent?.trim().toLowerCase() || '';
    if (title === 'gpu worker') return 'gpu';
    if (title === 'live logs' || title === 'logs') return 'logs';
    return '';
  }

  function applyOperationsMode() {
    const pane = tagOperationsLayout();
    if (!pane || !pane.classList.contains('active')) return;
    const mode = currentOperationsMode();
    pane.classList.toggle('fs-nav-gpu', mode === 'gpu');
    pane.classList.toggle('fs-nav-logs', mode === 'logs');

    const logHeading = q('.fs-nav-log-panel .fs-ops-log-head h2');
    const localButton = q('#fsOpsLogLocal');
    const gpuButton = q('#fsOpsLogGpu');

    if (mode === 'gpu') {
      if (logHeading) logHeading.textContent = 'GPU Worker Log';
      if (gpuButton && !gpuButton.classList.contains('active')) gpuButton.click();
    } else if (mode === 'logs') {
      if (logHeading) logHeading.textContent = 'Live Logs';
      if (localButton && !localButton.classList.contains('active')) localButton.click();
    }
  }

  function normalizeProcessingRules() {
    const detection = q('.settings-page[data-settings="detection"].active');
    if (!detection) return;
    const title = q('#pageTitle');
    const subtitle = q('#pageSubtitle');
    if (title) title.textContent = 'Processing Rules';
    if (subtitle) subtitle.textContent = 'Profanity detection, mute timing, rescue behavior, and CLEAN audio output';
  }

  function apply() {
    addStyles();
    removeDuplicateDetectionNav();
    tagOperationsLayout();
    applyOperationsMode();
    normalizeProcessingRules();
  }

  function boot() {
    apply();

    /* Existing navigation handlers run earlier in the event path. Re-apply after they finish. */
    document.addEventListener('click', () => setTimeout(apply, 0), true);

    const title = q('#pageTitle');
    if (title) new MutationObserver(apply).observe(title, {childList:true, characterData:true, subtree:true});
    const nav = q('.side-nav');
    if (nav) new MutationObserver(apply).observe(nav, {childList:true, subtree:true, attributes:true, attributeFilter:['class']});

    /* Covers asynchronous dashboard/settings rebuilds without depending on their implementation. */
    setInterval(apply, 1500);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 400));
  else setTimeout(boot, 400);
})();
