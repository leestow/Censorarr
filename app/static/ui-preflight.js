(() => {
  // ui-polish decorates the integration cards after the legacy dashboard renders them.
  // Its first implementation observed the card subtree and then rewrote that same subtree,
  // which could recursively trigger itself and peg the browser main thread. Keep normal
  // MutationObserver behavior everywhere else, but suppress that one self-observing target.
  if (window.__censorarrSafeMutationObserver || !window.MutationObserver) return;
  const NativeMutationObserver = window.MutationObserver;

  function SafeMutationObserver(callback) {
    const observer = new NativeMutationObserver(callback);
    const nativeObserve = observer.observe.bind(observer);
    observer.observe = function(target, options) {
      if (target && target.id === 'fsIntegrations') return;
      return nativeObserve(target, options);
    };
    return observer;
  }

  SafeMutationObserver.prototype = NativeMutationObserver.prototype;
  window.MutationObserver = SafeMutationObserver;
  window.__censorarrSafeMutationObserver = true;
})();
