(() => {
  const q = (s, root=document) => root.querySelector(s);
  const fmtDur = seconds => {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return '—';
    const s = Math.round(value);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return (h ? `${h}h ` : '') + (m ? `${m}m ` : '') + (!h ? `${x}s` : '');
  };
  const tc = seconds => {
    const value = Math.max(0, Math.floor(Number(seconds) || 0));
    const h = Math.floor(value / 3600), m = Math.floor((value % 3600) / 60), s = value % 60;
    return [h,m,s].map(v => String(v).padStart(2,'0')).join(':');
  };
  const base = path => String(path || '').replace(/\\/g,'/').split('/').pop() || '—';

  function ensureLegacyCompatibility() {
    // The original refresh() still writes these counters. The redesigned sidebar no longer
    // displays them, but removing the DOM nodes made refresh() throw and falsely report
    // "Connection error" even when /api/status succeeded.
    for (const id of ['reviewNavCount','failureNavCount']) {
      if (document.getElementById(id)) continue;
      const span = document.createElement('span');
      span.id = id;
      span.hidden = true;
      span.setAttribute('aria-hidden','true');
      document.body.appendChild(span);
    }
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function setFooter(status) {
    const overall = document.getElementById('overall');
    const dot = document.getElementById('dot');
    if (!overall || !dot || !status) return;
    const hb = status.heartbeat || {};
    const st = String(hb.status || 'unknown');
    let label;
    if (!status.worker_alive) label = 'Worker stopped';
    else if (status.paused) label = 'Paused';
    else if (st === 'blocked') label = 'Waiting';
    else if (st === 'permissions-error') label = 'Media permission problem';
    else if (st === 'remote-gpu') label = 'GPU processing';
    else if (st === 'idle') label = 'Connected';
    else label = st.replaceAll('-', ' ');
    overall.textContent = label;
    dot.className = 'dot ' + (!status.worker_alive || st === 'fatal' || st === 'permissions-error' ? 'bad' : (status.paused || st === 'blocked' ? 'warn' : 'good'));
  }

  function progressFrom(status, gpu) {
    const hb = status?.heartbeat || {};
    const cur = gpu?.current_job && typeof gpu.current_job === 'object' ? gpu.current_job : null;
    if (cur && cur.progress != null && Number.isFinite(Number(cur.progress))) {
      return { value: Number(cur.progress), label: 'GPU progress', source: 'gpu', cur, hb };
    }
    if (hb.status === 'remote-gpu') {
      const raw = hb.stage_progress ?? hb.progress ?? hb.overall_progress;
      if (raw != null && Number.isFinite(Number(raw))) return { value:Number(raw), label:'GPU progress', source:'heartbeat-gpu', cur, hb };
    }
    if (hb.current) {
      const raw = hb.overall_progress ?? hb.stage_progress ?? hb.progress;
      if (raw != null && Number.isFinite(Number(raw))) return { value:Number(raw), label:'Job progress', source:'job', cur, hb };
    }
    return { value:0, label:'GPU progress', source:'idle', cur, hb };
  }

  function renderWorker(status, gpu) {
    const hb = status?.heartbeat || {};
    const cur = gpu?.current_job && typeof gpu.current_job === 'object' ? gpu.current_job : null;
    const online = !!gpu?.enabled && !!gpu?.ok;
    const p = progressFrom(status, gpu);
    const value = Math.max(0, Math.min(100, Number(p.value) || 0));

    setText('fsWorkerModel', cur?.model || gpu?.default_model || hb.remote_model || '—');
    setText('fsWorkerMode', online ? 'GPU (remote)' : (gpu?.enabled ? 'GPU unavailable' : 'Local / CPU'));
    setText('fsWorkerState', cur ? (cur.stage || 'Working') : (online ? 'Online / idle' : (gpu?.enabled ? 'Offline' : 'Disabled')));
    setText('fsWorkerJob', hb.current ? base(hb.current) : (cur?.job_id ? String(cur.job_id).slice(0,8) : '—'));
    setText('fsWorkerProgress', (cur || hb.current) ? `${value.toFixed(value % 1 ? 1 : 0)}%` : '—');

    const progressLabel = document.getElementById('fsWorkerProgress')?.closest('.fs-stat')?.querySelector('span');
    if (progressLabel) progressLabel.textContent = p.label;

    const position = cur?.position_seconds ?? hb.gpu_position_seconds;
    const duration = cur?.duration_seconds ?? hb.gpu_duration_seconds;
    setText('fsWorkerPosition', position != null ? `${tc(position)}${duration ? ` / ${tc(duration)}` : ''}` : '—');

    const eta = cur?.eta_seconds ?? hb.gpu_eta_seconds;
    setText('fsWorkerEta', eta != null ? fmtDur(eta) : '—');

    const meter = document.getElementById('fsWorkerMeter');
    if (meter) meter.style.width = `${value}%`;

    // Keep the original operational page in sync too. These fields are used by the old
    // GPU/log page and by any older runtime code that still expects them.
    if (document.getElementById('gpuProgress')) document.getElementById('gpuProgress').textContent = cur && cur.progress != null ? `${Number(cur.progress).toFixed(1)}%` : '—';
    if (document.getElementById('gpuPosition')) document.getElementById('gpuPosition').textContent = position != null ? `${tc(position)}${duration ? ` / ${tc(duration)}` : ''}` : '—';
    if (document.getElementById('gpuEta')) document.getElementById('gpuEta').textContent = eta != null ? fmtDur(eta) : '—';
    if (document.getElementById('gpuModel')) document.getElementById('gpuModel').textContent = cur?.model || gpu?.default_model || '—';
    if (document.getElementById('gpuJob')) document.getElementById('gpuJob').textContent = cur?.job_id ? String(cur.job_id).slice(0,8) : '—';
    if (document.getElementById('gpuState')) document.getElementById('gpuState').textContent = cur ? (cur.stage || 'Working') : (online ? 'Online / idle' : 'Offline');
  }

  let running = false;
  async function poll() {
    if (running) return;
    running = true;
    try {
      ensureLegacyCompatibility();
      const [statusResult, gpuResult] = await Promise.allSettled([
        fetch('/api/status', {credentials:'same-origin', cache:'no-store'}).then(r => { if (!r.ok) throw new Error(`status ${r.status}`); return r.json(); }),
        fetch('/api/integrations/asr/status', {credentials:'same-origin', cache:'no-store'}).then(r => { if (!r.ok) throw new Error(`gpu ${r.status}`); return r.json(); })
      ]);
      const status = statusResult.status === 'fulfilled' ? statusResult.value : null;
      const gpu = gpuResult.status === 'fulfilled' ? gpuResult.value : null;
      if (status) setFooter(status);
      if (status || gpu) renderWorker(status, gpu);
    } catch (err) {
      console.debug('Censorarr live UI poll failed', err);
    } finally {
      running = false;
    }
  }

  function boot() {
    ensureLegacyCompatibility();
    poll();
    setInterval(poll, 2000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 250));
  else setTimeout(boot, 250);
})();
