(() => {
  const q = (s, root=document) => root.querySelector(s);
  const qa = (s, root=document) => [...root.querySelectorAll(s)];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmtDur = seconds => {
    const value = Number(seconds);
    if (!Number.isFinite(value) || value < 0) return '—';
    const s = Math.round(value), h = Math.floor(s/3600), m = Math.floor((s%3600)/60), x = s%60;
    return (h ? `${h}h ` : '') + (m ? `${m}m ` : '') + (!h ? `${x}s` : '');
  };
  const tc = seconds => {
    const v = Math.max(0, Math.floor(Number(seconds)||0));
    const h=Math.floor(v/3600),m=Math.floor((v%3600)/60),s=v%60;
    return [h,m,s].map(n=>String(n).padStart(2,'0')).join(':');
  };
  const basename = path => String(path||'').replace(/\\/g,'/').split('/').pop() || '—';
  const human = value => String(value||'').replaceAll('-',' ').replace(/\b\w/g,c=>c.toUpperCase());

  let latestStatus = null;
  let latestGpu = null;
  let polling = false;
  let opsLogMode = 'plex';
  let opsLogBusy = false;

  function addStyles() {
    if (q('#fsFinalFixStyles')) return;
    const style = document.createElement('style');
    style.id = 'fsFinalFixStyles';
    style.textContent = `
      /* Keep the collapse chevron inside the sidebar, clear of the search box. */
      .fs-sidebar-collapse{top:78px!important;right:8px!important;width:25px!important;height:25px!important;z-index:30!important;padding:0!important;font-size:11px!important}
      .app-shell.fs-collapsed .fs-sidebar-collapse{right:8px!important}

      /* Current filename belongs on the operational page, not the compact worker card. */
      .fs-worker-current-job-row{display:none!important}

      /* Make poster progress rings readable on the light content theme. */
      .wrap.fs-content-light .fs-progress-ring{
        background:conic-gradient(#19bd7f 0 var(--p),rgba(28,57,78,.18) var(--p) 100%)!important;
        box-shadow:0 0 0 4px rgba(255,255,255,.78),0 4px 18px rgba(26,54,74,.24)!important
      }
      .wrap.fs-content-light .fs-progress-ring::after{background:rgba(255,255,255,.95)!important;box-shadow:inset 0 0 0 1px #d7e4ec!important}
      .wrap.fs-content-light .fs-progress-ring span{color:#123047!important;text-shadow:none!important}

      /* Dry Run is no longer part of the family-safe UI. Keep legacy controls in the DOM only
         because the old settings script still references their IDs. */
      #dry{display:none!important}

      /* Dedicated operational page used by GPU Worker, Logs, and In Progress -> View all. */
      #fsOperationsPane{display:none}
      #fsOperationsPane.active{display:block}
      .fs-ops-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
      .fs-ops-toolbar .spacer{flex:1}
      .fs-ops-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(330px,.65fr);gap:12px;margin-bottom:12px}
      .fs-ops-panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:15px;color:var(--text)}
      .fs-ops-panel h2{font-size:16px;margin:0 0 12px}
      .fs-ops-current{font-size:18px;font-weight:780;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:7px}
      .fs-ops-meta{display:flex;gap:8px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-bottom:12px}
      .fs-ops-bar-label{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:12px;margin-top:10px}
      .fs-ops-bar{height:10px;background:var(--panel3);border-radius:999px;overflow:hidden;margin-top:5px}
      .fs-ops-bar>span{display:block;height:100%;width:0;background:linear-gradient(90deg,#238bf3,#25d48a);border-radius:999px;transition:width .25s}
      .fs-ops-stats{display:grid;grid-template-columns:1fr 1fr;column-gap:18px}
      .fs-ops-stat{display:flex;justify-content:space-between;gap:10px;padding:8px 0;border-bottom:1px solid var(--line);font-size:12px}
      .fs-ops-stat b{font-weight:760;text-align:right;max-width:190px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .fs-ops-good{color:#25d48a!important}
      .fs-ops-log-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px}
      .fs-ops-log-head h2{margin:0;margin-right:auto}
      .fs-ops-segment{display:flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
      .fs-ops-segment button{border:0!important;border-right:1px solid var(--line)!important;border-radius:0!important;background:var(--panel2)!important;padding:7px 10px!important}
      .fs-ops-segment button:last-child{border-right:0!important}
      .fs-ops-segment button.active{background:color-mix(in srgb,var(--accent2) 22%,var(--panel2))!important}
      .fs-ops-log{height:390px;overflow:auto;white-space:pre-wrap;background:#060a0f;color:#c9d9e7;border:1px solid #1d2b39;border-radius:7px;padding:11px;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
      .fs-ops-queue{display:grid;gap:0}
      .fs-ops-queue-row{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid var(--line);padding:8px 0;font-size:12px}
      .fs-ops-queue-row span:first-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:78%}
      .fs-dashboard .fs-poster-card{cursor:pointer}
      .fs-dashboard .fs-poster-card:hover .fs-poster{outline:2px solid color-mix(in srgb,var(--accent2) 60%,transparent);outline-offset:2px}
      @media(max-width:950px){.fs-ops-grid{grid-template-columns:1fr}.fs-ops-stats{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function apiJson(path, options={}) {
    return fetch(path, {credentials:'same-origin', ...options}).then(async r => {
      let data={}; try{data=await r.json()}catch(_){ }
      if(!r.ok) throw new Error(data.detail||data.error||`HTTP ${r.status}`);
      return data;
    });
  }

  function setText(id, value) { const el=q('#'+id); if(el) el.textContent=value; }
  function setWidth(id, value) { const el=q('#'+id); if(el) el.style.width=`${Math.max(0,Math.min(100,Number(value)||0))}%`; }

  function makeShadow(id, tag='span') {
    if (document.getElementById(id)) return;
    const el=document.createElement(tag); el.id=id; el.hidden=true; el.setAttribute('aria-hidden','true'); document.body.appendChild(el);
  }
  function moveId(oldId,newId,tag='span') {
    if(q('#'+newId)) return true;
    const el=q('#'+oldId); if(!el) return false;
    el.id=newId; makeShadow(oldId,tag); return true;
  }

  function stabilizeWorkerCard() {
    // updater.js and ui-live-fix.js both used the same visible IDs. Give the visible card private
    // IDs and leave invisible compatibility targets behind, so only this live poll controls it.
    [
      ['fsWorkerModel','fsLiveWorkerModel'],['fsWorkerMode','fsLiveWorkerMode'],
      ['fsWorkerState','fsLiveWorkerState'],['fsWorkerProgress','fsLiveWorkerProgress'],
      ['fsWorkerEta','fsLiveWorkerEta'],['fsWorkerPosition','fsLiveWorkerPosition'],
      ['fsWorkerMeter','fsLiveWorkerMeter'],['fsKpiWorkers','fsLiveKpiWorkers']
    ].forEach(([a,b])=>moveId(a,b));
    const job=q('#fsWorkerJob'); if(job) job.closest('.fs-stat')?.classList.add('fs-worker-current-job-row');
  }

  function workerStatValue(label) {
    const rows=qa('#fsWorkerCard .fs-stat');
    const row=rows.find(r=>q('span',r)?.textContent?.trim()===label);
    return row ? q('b',row) : null;
  }

  function progressSource(status,gpu) {
    const hb=status?.heartbeat||{};
    const cur=gpu?.current_job && typeof gpu.current_job==='object' ? gpu.current_job : null;
    if(cur && Number.isFinite(Number(cur.progress))) return {value:Number(cur.progress),label:'GPU progress',cur,hb};
    const raw=hb.overall_progress ?? hb.stage_progress ?? hb.progress;
    if(hb.current && Number.isFinite(Number(raw))) return {value:Number(raw),label:'Job progress',cur,hb};
    return {value:0,label:'GPU progress',cur,hb};
  }

  function renderWorkerCard(status,gpu) {
    stabilizeWorkerCard();
    const hb=status?.heartbeat||{}, cur=gpu?.current_job && typeof gpu.current_job==='object' ? gpu.current_job : null;
    const online=!!gpu?.enabled && !!gpu?.ok;
    const p=progressSource(status,gpu), value=Math.max(0,Math.min(100,Number(p.value)||0));
    const appStage=String(hb.status||'idle');
    const state=cur ? human(cur.stage||'transcribing') : (hb.current ? human(appStage) : (online?'Online / idle':gpu?.enabled?'Offline':'Disabled'));

    setText('fsLiveWorkerModel',cur?.model||gpu?.default_model||hb.remote_model||'—');
    setText('fsLiveWorkerMode',online?'Remote GPU':gpu?.enabled?'GPU unavailable':'Local CPU');
    setText('fsLiveWorkerState',state);
    setText('fsLiveWorkerProgress',(cur||hb.current)?`${value.toFixed(value%1?1:0)}%`:'—');
    setText('fsLiveKpiWorkers',cur?'Transcribing':hb.current?human(appStage):online?'Online':'Offline');
    setWidth('fsLiveWorkerMeter',value);

    const progressLabel=q('#fsLiveWorkerProgress')?.closest('.fs-stat')?.querySelector('span');
    if(progressLabel) progressLabel.textContent=p.label;
    const pos=cur?.position_seconds ?? hb.gpu_position_seconds;
    const dur=cur?.duration_seconds ?? hb.gpu_duration_seconds;
    const eta=cur?.eta_seconds ?? hb.gpu_eta_seconds;
    setText('fsLiveWorkerPosition',pos!=null?`${tc(pos)}${dur?` / ${tc(dur)}`:''}`:'—');
    setText('fsLiveWorkerEta',eta!=null?fmtDur(eta):'—');
    const device=workerStatValue('Device'); if(device) device.textContent=online?'Remote GPU':'Local';
  }

  function hideLegacyModeControls() {
    const hideControl=id=>{
      const el=q('#'+id); if(!el)return;
      if('value' in el) el.value='false';
      const box=el.closest('.field,.checkrow,.wizard-field')||el.parentElement;
      if(box) box.style.display='none';
    };
    hideControl('sDry'); hideControl('wDry');
    const badge=q('#dry'); if(badge) badge.style.display='none';

    // Keep old history entries readable without retaining the removed mode's name.
    if(typeof window.mediaStatusLabel==='function' && !window.__fsDryLabelPatched){
      const old=window.mediaStatusLabel;
      window.mediaStatusLabel=s=>String(s)==='dry-run'?'Analyzed':old(s);
      window.__fsDryLabelPatched=true;
    }
    if(typeof window.mediaStatusBadge==='function' && !window.__fsDryBadgePatched){
      const old=window.mediaStatusBadge;
      window.mediaStatusBadge=s=>String(s)==='dry-run'?'<span class="badge">Analyzed</span>':old(s);
      window.__fsDryBadgePatched=true;
    }
    if(typeof window.wizardBuildSummary==='function' && !window.__fsWizardSummaryPatched){
      const old=window.wizardBuildSummary;
      window.wizardBuildSummary=function(){
        old();
        qa('#wizardSummary > div').forEach(card=>{if(/^Mode\b/i.test(card.textContent.trim()))card.remove();});
      };
      window.__fsWizardSummaryPatched=true;
    }

    const tip=q('#fsTip');
    if(tip && !tip.dataset.noDryObserver){
      tip.dataset.noDryObserver='1';
      const fix=()=>{if(/dry\s*run/i.test(tip.textContent||''))tip.textContent='Tip: Start with a small test folder when validating a new setup.';};
      new MutationObserver(fix).observe(tip,{childList:true,characterData:true,subtree:true}); fix();
    }
  }

  function removeQueueNav() {
    q('[data-polish-action="queue"]')?.remove();
  }

  function showOnlyPane(id) {
    qa('.pane').forEach(p=>p.classList.remove('active'));
    q('#'+id)?.classList.add('active');
  }
  function activateNav(action) {
    qa('.side-nav .nav-item').forEach(x=>x.classList.remove('active'));
    q(`[data-polish-action="${action}"]`)?.classList.add('active');
  }

  function ensureOperationsPane() {
    if(q('#fsOperationsPane')) return;
    const pane=document.createElement('section');
    pane.id='fsOperationsPane'; pane.className='pane';
    pane.innerHTML=`
      <div class="fs-ops-toolbar">
        <button id="fsOpsPause">Pause automatic</button>
        <button id="fsOpsScan" class="primary">Scan now</button>
        <button id="fsOpsStop" class="danger">Stop current</button>
        <span class="spacer"></span><span class="badge" id="fsOpsWorkerBadge">Worker —</span>
      </div>
      <div class="fs-ops-grid">
        <div class="fs-ops-panel">
          <h2>Current Processing</h2>
          <div class="fs-ops-current" id="fsOpsCurrent">No media currently processing</div>
          <div class="fs-ops-meta"><span id="fsOpsStage">Stage: —</span><span id="fsOpsDetect">No detection totals yet</span></div>
          <div class="fs-ops-bar-label"><span>Overall job</span><b id="fsOpsOverallText">—</b></div><div class="fs-ops-bar"><span id="fsOpsOverallBar"></span></div>
          <div class="fs-ops-bar-label"><span>Current stage</span><b id="fsOpsStageText">—</b></div><div class="fs-ops-bar"><span id="fsOpsStageBar"></span></div>
        </div>
        <div class="fs-ops-panel">
          <h2>GPU Worker</h2>
          <div class="fs-ops-stats">
            <div class="fs-ops-stat"><span>Status</span><b id="fsOpsGpuState">—</b></div>
            <div class="fs-ops-stat"><span>Model</span><b id="fsOpsGpuModel">—</b></div>
            <div class="fs-ops-stat"><span>Progress</span><b id="fsOpsGpuProgress">—</b></div>
            <div class="fs-ops-stat"><span>ETA</span><b id="fsOpsGpuEta">—</b></div>
            <div class="fs-ops-stat"><span>Position</span><b id="fsOpsGpuPosition">—</b></div>
            <div class="fs-ops-stat"><span>Backend</span><b id="fsOpsGpuBackend">—</b></div>
          </div>
        </div>
      </div>
      <div class="fs-ops-grid">
        <div class="fs-ops-panel">
          <div class="fs-ops-log-head"><h2>Live Log</h2><div class="fs-ops-segment"><button id="fsOpsLogLocal" class="active">Censorarr</button><button id="fsOpsLogGpu">GPU Worker</button></div><button id="fsOpsClearLog">Clear</button><button id="fsOpsDownloadLog">Download</button></div>
          <pre class="fs-ops-log" id="fsOpsLog">Loading log…</pre>
        </div>
        <div class="fs-ops-panel"><h2>Upcoming Work</h2><div class="fs-ops-queue" id="fsOpsQueue"><span class="muted">Loading…</span></div></div>
      </div>`;
    q('.wrap')?.appendChild(pane);

    q('#fsOpsLogLocal').onclick=()=>{opsLogMode='plex';setOpsLogButtons();refreshOpsLog(true);};
    q('#fsOpsLogGpu').onclick=()=>{opsLogMode='gpu';setOpsLogButtons();refreshOpsLog(true);};
    q('#fsOpsScan').onclick=async()=>{try{await apiJson('/api/control/scan-now',{method:'POST'});await poll();}catch(e){alert(e.message)}};
    q('#fsOpsPause').onclick=async()=>{try{await apiJson(latestStatus?.paused?'/api/control/resume':'/api/control/pause',{method:'POST'});await poll();}catch(e){alert(e.message)}};
    q('#fsOpsStop').onclick=async()=>{if(!confirm('Stop the current media item?'))return;try{await apiJson('/api/control/stop-current',{method:'POST'});await poll();}catch(e){alert(e.message)}};
    q('#fsOpsClearLog').onclick=async()=>{if(!confirm(`Clear the ${opsLogMode==='gpu'?'GPU worker':'Censorarr'} log?`))return;try{await apiJson(opsLogMode==='gpu'?'/api/integrations/asr/logs/clear':'/api/log/clear',{method:'POST'});q('#fsOpsLog').textContent='';}catch(e){alert(e.message)}};
    q('#fsOpsDownloadLog').onclick=()=>{location.href=opsLogMode==='gpu'?'/api/integrations/asr/logs/download':'/api/log/download';};
  }

  function setOpsLogButtons(){
    q('#fsOpsLogLocal')?.classList.toggle('active',opsLogMode==='plex');
    q('#fsOpsLogGpu')?.classList.toggle('active',opsLogMode==='gpu');
  }

  function renderOperations(status,gpu) {
    if(!q('#fsOperationsPane')) return;
    const hb=status?.heartbeat||{},cur=gpu?.current_job && typeof gpu.current_job==='object'?gpu.current_job:null;
    const online=!!gpu?.enabled&&!!gpu?.ok;
    setText('fsOpsWorkerBadge',status?.worker_alive?(status.paused?'Paused':'Worker online'):'Worker stopped');
    q('#fsOpsWorkerBadge')?.classList.toggle('good',!!status?.worker_alive);
    setText('fsOpsPause',status?.paused?'Resume automatic':'Pause automatic');
    setText('fsOpsCurrent',hb.current?basename(hb.current):'No media currently processing');
    const stage=hb.status==='remote-gpu'&&hb.remote_stage?`GPU ${human(hb.remote_stage)}`:human(hb.status||'idle');
    setText('fsOpsStage',`Stage: ${stage}`);
    const bits=[];if(hb.normal_count!=null)bits.push(`Normal ${hb.normal_count}`);if(hb.rescue_count!=null)bits.push(`Rescue ${hb.rescue_count}`);if(hb.subtitle_count!=null)bits.push(`Subtitle ${hb.subtitle_count}`);if(hb.mute_ranges!=null)bits.push(`Mute ${hb.mute_ranges}`);
    setText('fsOpsDetect',bits.join(' · ')||'No detection totals yet');
    const overall=Number(hb.overall_progress??0),stageP=Number(hb.stage_progress??hb.progress??0);
    setWidth('fsOpsOverallBar',overall);setWidth('fsOpsStageBar',stageP);
    setText('fsOpsOverallText',hb.current&&hb.overall_progress!=null?`${overall.toFixed(0)}%`:'—');
    let stageText=hb.current&&Number.isFinite(stageP)?`${stageP.toFixed(0)}%`:'—';
    if(hb.gpu_eta_seconds!=null)stageText+=` · ETA ${fmtDur(hb.gpu_eta_seconds)}`;
    setText('fsOpsStageText',stageText);

    setText('fsOpsGpuState',cur?human(cur.stage||'working'):online?'Online / idle':gpu?.enabled?'Offline':'Disabled');
    setText('fsOpsGpuModel',cur?.model||gpu?.default_model||'—');
    setText('fsOpsGpuProgress',cur&&cur.progress!=null?`${Number(cur.progress).toFixed(1)}%`:'—');
    setText('fsOpsGpuEta',cur?.eta_seconds!=null?fmtDur(cur.eta_seconds):'—');
    setText('fsOpsGpuPosition',cur?.position_seconds!=null?`${tc(cur.position_seconds)}${cur.duration_seconds?` / ${tc(cur.duration_seconds)}`:''}`:'—');
    setText('fsOpsGpuBackend',online?'Remote GPU':gpu?.enabled?'Remote unavailable':'Local');
    q('#fsOpsGpuState')?.classList.toggle('fs-ops-good',online);
  }

  async function refreshOpsQueue() {
    if(!q('#fsOperationsPane.active')) return;
    try{
      const data=await apiJson('/api/queue');const items=data.items||[];
      q('#fsOpsQueue').innerHTML=items.length?items.slice(0,12).map(x=>`<div class="fs-ops-queue-row"><span title="${esc(x.path||'')}">${esc(basename(x.path))}</span><span class="badge">${esc(x.mode||'process')}</span></div>`).join(''):'<span class="muted">Nothing queued.</span>';
    }catch(e){q('#fsOpsQueue').innerHTML=`<span class="muted">Queue unavailable: ${esc(e.message)}</span>`;}
  }

  async function refreshOpsLog(force=false) {
    if(!q('#fsOperationsPane.active')||opsLogBusy)return;
    opsLogBusy=true;
    try{
      const data=await apiJson(opsLogMode==='gpu'?'/api/integrations/asr/logs?lines=400':'/api/log/tail?lines=400');
      const box=q('#fsOpsLog'),near=box.scrollHeight-box.scrollTop-box.clientHeight<100;
      const next=(data.lines||[]).join('\n');
      if(force||box.textContent!==next)box.textContent=next||'No log lines yet.';
      if(near||force)box.scrollTop=box.scrollHeight;
    }catch(e){q('#fsOpsLog').textContent=`Log unavailable: ${e.message}`;}finally{opsLogBusy=false;}
  }

  function openOperations(mode='plex') {
    ensureOperationsPane();
    opsLogMode=mode==='gpu'?'gpu':'plex';setOpsLogButtons();
    showOnlyPane('fsOperationsPane');
    activateNav(mode==='gpu'?'gpu':'logs');
    const title=q('#pageTitle'),sub=q('#pageSubtitle');
    if(title)title.textContent=mode==='gpu'?'GPU Worker':'Live Logs';
    if(sub)sub.textContent=mode==='gpu'?'Live transcription progress, worker status, and GPU log':'Current processing, progress bars, and live Censorarr log';
    renderOperations(latestStatus,latestGpu);refreshOpsQueue();refreshOpsLog(true);
  }
  window.CensorarrOpenOperations=openOperations;

  function openHistory(filterValue='') {
    const button=q('[data-polish-action="history"]');
    window.tab?.('library',button);
    setTimeout(()=>{
      const filter=q('#historyFilter');if(filter){filter.value=filterValue;window.refreshHistory?.();}
    },30);
  }

  function wireNavigation() {
    removeQueueNav();
    const nav=q('.side-nav');
    if(nav&&!nav.dataset.finalCapture){
      nav.dataset.finalCapture='1';
      nav.addEventListener('click',e=>{
        const b=e.target.closest('[data-polish-action]');if(!b)return;
        const a=b.dataset.polishAction;
        if(a==='gpu'||a==='logs'){
          e.preventDefault();e.stopImmediatePropagation();openOperations(a==='gpu'?'gpu':'plex');
        }
      },true);
    }

    const worker=q('#fsWorkerOpen');if(worker)worker.onclick=e=>{e.preventDefault();openOperations('gpu');};
    const inProgress=q('#fsInProgress .fs-link');if(inProgress)inProgress.onclick=e=>{e.preventDefault();openOperations('plex');};
    const recent=q('#fsRecent .fs-link');if(recent)recent.onclick=e=>{e.preventDefault();openHistory('');};
    const waiting=q('#fsWaiting .fs-link');if(waiting)waiting.onclick=e=>{e.preventDefault();openHistory('waiting-subtitle');};
    const review=q('#fsReview .fs-link');if(review)review.onclick=e=>{e.preventDefault();window.tab?.('reviews',null);};
    const hist=q('#fsHistOpen');if(hist)hist.onclick=e=>{e.preventDefault();openHistory('');};

    // The status card remains useful even without an Integrations sidebar destination.
    qa('#fsIntegrations .fs-int').forEach(card=>{
      card.style.cursor='pointer';
      const name=q('.fs-int-name',card)?.textContent?.trim().toLowerCase()||'';
      card.onclick=()=>{
        const map=name==='plex'?'plex':name==='sonarr'?'tv':name==='radarr'?'movies':name==='bazarr'||name==='subtitles'?'subtitles':name.includes('gpu')?'whisper':null;
        if(!map)return;
        q('.fs-settings-group')?.classList.add('open');
        const b=q(`[data-polish-action="settings:${map}"]`);window.openSettingsNav?.(map,b);
      };
    });
  }

  function wirePosterDetails() {
    if(document.documentElement.dataset.fsPosterNav==='1')return;
    document.documentElement.dataset.fsPosterNav='1';
    document.addEventListener('click',e=>{
      const card=e.target.closest('#fsDashboard .fs-poster-card');if(!card)return;
      const id=Number(card.dataset.id||0),kind=card.dataset.kind==='series'?'series':'movie';if(!id)return;
      e.preventDefault();e.stopImmediatePropagation();
      const navKind=kind==='series'?'series':'movies';
      const button=q(`[data-polish-action="library:${navKind}"]`);
      window.openMediaNav?.(navKind,button);
      setTimeout(()=>window.openMediaDetail?.(kind,id),60);
    },true);
  }

  function scrubRemovedModeText(root=document.body) {
    if(!root)return;
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    const nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
    nodes.forEach(node=>{
      const raw=node.nodeValue||'';
      let next=raw.replace(/Analyzed \(dry run\)/gi,'Analyzed').replace(/\bdry-run\b/gi,'Analyzed');
      if(/^\s*dry\s*run\s*$/i.test(next))next='';
      if(next!==raw)node.nodeValue=next;
    });
  }

  async function poll() {
    if(polling)return;polling=true;
    try{
      const [s,g]=await Promise.allSettled([apiJson('/api/status',{cache:'no-store'}),apiJson('/api/integrations/asr/status',{cache:'no-store'})]);
      latestStatus=s.status==='fulfilled'?s.value:latestStatus;
      latestGpu=g.status==='fulfilled'?g.value:latestGpu;
      renderWorkerCard(latestStatus,latestGpu);renderOperations(latestStatus,latestGpu);
      if(q('#fsOperationsPane.active')){refreshOpsQueue();refreshOpsLog();}
    }finally{polling=false;}
  }

  function boot() {
    addStyles();
    stabilizeWorkerCard();hideLegacyModeControls();wireNavigation();wirePosterDetails();ensureOperationsPane();scrubRemovedModeText();
    // updater.js builds dashboard pieces asynchronously; repeat the harmless wiring once they exist.
    setTimeout(()=>{stabilizeWorkerCard();hideLegacyModeControls();wireNavigation();scrubRemovedModeText();},800);
    setTimeout(()=>{stabilizeWorkerCard();hideLegacyModeControls();wireNavigation();scrubRemovedModeText();},1800);
    poll();setInterval(poll,2000);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,300));else setTimeout(boot,300);
})();
