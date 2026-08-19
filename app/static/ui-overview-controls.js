(() => {
  const q=(s,r=document)=>r.querySelector(s);
  let busy=false,lastPaused=null;

  async function request(path,options={}){
    const response=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let data={};try{data=await response.json()}catch(_){ }
    if(!response.ok)throw new Error(data.detail||data.error||`HTTP ${response.status}`);
    return data;
  }

  function addStyles(){
    if(q('#fsOverviewControlStyles'))return;
    const s=document.createElement('style');s.id='fsOverviewControlStyles';s.textContent=`
      #fsStopPauseBtn{border-color:rgba(255,191,76,.58)!important;color:#ffe0a2!important;background:rgba(117,65,5,.30)!important;min-width:142px}
      #fsStopPauseBtn:hover{background:rgba(145,78,5,.44)!important}
      #fsStopPauseBtn.paused{border-color:rgba(71,224,155,.58)!important;color:#98f3c8!important;background:rgba(10,103,66,.32)!important}
      #fsStopPauseBtn.working{opacity:.72;cursor:wait!important}
      @media(max-width:1050px){#fsStopPauseBtn{min-width:0;padding-left:10px!important;padding-right:10px!important}.fs-stop-label{display:none}}
    `;document.head.appendChild(s);
  }

  function ensureButton(){
    const scan=q('#fsScanBtn');
    if(!scan?.parentElement)return null;
    let b=q('#fsStopPauseBtn');
    if(!b){
      b=document.createElement('button');
      b.id='fsStopPauseBtn';b.className='fs-topbtn';
      scan.parentElement.insertBefore(b,scan.nextSibling);
      b.addEventListener('click',toggleStopPause);
    }
    renderButton(lastPaused);
    return b;
  }

  function renderButton(paused){
    const b=q('#fsStopPauseBtn');if(!b)return;
    const isPaused=paused===true;
    b.classList.toggle('paused',isPaused);b.classList.toggle('working',busy);b.disabled=busy;
    if(busy){b.innerHTML='⏳ <span class="fs-stop-label">Working…</span>';return;}
    b.innerHTML=isPaused?'▶ <span class="fs-stop-label">Resume Automation</span>':'■ <span class="fs-stop-label">Stop & Pause</span>';
    b.title=isPaused?'Resume automatic Censorarr processing':'Stop the current job and pause automatic processing';
  }

  async function refreshState(){
    try{
      const s=await request('/api/status');
      lastPaused=!!s.paused;ensureButton();renderButton(lastPaused);
    }catch(_){ensureButton();}
  }

  async function toggleStopPause(){
    if(busy)return;
    busy=true;renderButton(lastPaused);
    try{
      if(lastPaused){
        await request('/api/control/resume',{method:'POST',body:'{}'});
        lastPaused=false;
      }else{
        // Pause FIRST. stop-current restarts the worker, and the pause flag must already
        // exist so the restarted worker cannot claim the next queued/library item.
        await request('/api/control/pause',{method:'POST',body:'{}'});
        try{
          await request('/api/control/stop-current',{method:'POST',body:'{}'});
        }catch(stopErr){
          // Even if there is no cancellable current item, keeping automation paused is
          // still the safest interpretation of the user's request.
          console.debug('Censorarr current-job stop result:',stopErr);
        }
        lastPaused=true;
      }
    }catch(err){
      alert(`Censorarr control failed:\n\n${err.message||err}`);
    }finally{
      busy=false;renderButton(lastPaused);setTimeout(refreshState,800);
    }
  }

  function boot(){addStyles();ensureButton();refreshState();setInterval(refreshState,5000);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,650));else setTimeout(boot,650);
})();

(() => {
  const q=(s,r=document)=>r.querySelector(s);
  const qa=(s,r=document)=>[...r.querySelectorAll(s)];

  function addStyles(){
    if(q('#fsIntegrationsOverviewStyles'))return;
    const s=document.createElement('style');s.id='fsIntegrationsOverviewStyles';s.textContent=`
      .fs-integrations-overview-grid{display:grid;grid-template-columns:repeat(2,minmax(280px,1fr));gap:12px;max-width:980px}
      .fs-integrations-overview-card{display:grid;grid-template-columns:48px minmax(0,1fr) auto;gap:12px;align-items:center;background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:14px}
      .fs-integrations-overview-icon{width:44px;height:44px;display:grid;place-items:center;border-radius:9px;background:color-mix(in srgb,var(--panel3) 72%,transparent)}
      .fs-integrations-overview-icon img{width:31px;height:31px;object-fit:contain;display:block}
      .fs-integrations-overview-icon .cc{font-size:14px;font-weight:900;color:var(--accent2)}
      .fs-integrations-overview-name{font-size:15px;font-weight:800;margin-bottom:2px}
      .fs-integrations-overview-desc{font-size:11px;color:var(--muted);margin-bottom:5px}
      .fs-integrations-overview-state{font-size:11px;font-weight:700;color:var(--muted)}
      .fs-integrations-overview-state.on{color:var(--accent)}
      .wrap.fs-content-light .fs-integrations-overview-card{background:#fff!important;border-color:#d7e3ec!important;color:#142435!important}
      .wrap.fs-content-light .fs-integrations-overview-icon{background:#f0f5f8!important}
      @media(max-width:850px){.fs-integrations-overview-grid{grid-template-columns:1fr}.fs-integrations-overview-card{grid-template-columns:44px minmax(0,1fr)}}
    `;document.head.appendChild(s);
  }

  function serviceCard({id,name,icon,desc,section,label='Configure'}){
    const art=icon.startsWith('/')?`<img src="${icon}" alt="">`:`<span class="cc">${icon}</span>`;
    return `<div class="fs-integrations-overview-card">
      <div class="fs-integrations-overview-icon">${art}</div>
      <div><div class="fs-integrations-overview-name">${name}</div><div class="fs-integrations-overview-desc">${desc}</div><div class="fs-integrations-overview-state" id="fsIntState-${id}">Checking…</div></div>
      <button class="small" type="button" data-integration-section="${section}">${label}</button>
    </div>`;
  }

  function ensurePage(){
    const shell=q('#settingsPane .settings-shell');
    if(!shell)return null;
    let page=q('.settings-page[data-settings="integrations"]',shell);
    if(!page){
      page=document.createElement('div');page.className='settings-page';page.dataset.settings='integrations';
      page.innerHTML=`<h2 class="settings-page-title">Integrations</h2><div class="settings-page-desc">One place to see the optional services Censorarr uses. Open any card to change that service's existing settings.</div><div class="fs-integrations-overview-grid">
        ${serviceCard({id:'sonarr',name:'Sonarr',icon:'/assets/sonarr.svg',desc:'TV metadata, artwork and episode information.',section:'tv'})}
        ${serviceCard({id:'radarr',name:'Radarr',icon:'/assets/radarr.svg',desc:'Movie metadata, artwork and file information.',section:'movies'})}
        ${serviceCard({id:'plex',name:'Plex',icon:'/assets/plex.svg',desc:'Ratings, playback-aware pausing and library refresh.',section:'plex'})}
        ${serviceCard({id:'bazarr',name:'Bazarr',icon:'/assets/bazarr.svg',desc:'Optional subtitle assistance and missing-subtitle requests.',section:'subtitles'})}
        ${serviceCard({id:'gpu',name:'GPU Worker',icon:'/assets/censorarr-favicon-wave.svg',desc:'Remote Whisper transcription acceleration.',section:'whisper',label:'Transcription'})}
        ${serviceCard({id:'subtitles',name:'Subtitle Assistance',icon:'CC',desc:'Embedded, local and optional Bazarr subtitle evidence.',section:'subtitles',label:'Subtitle Settings'})}
      </div>`;
      shell.appendChild(page);
      qa('[data-integration-section]',page).forEach(b=>b.onclick=()=>openExistingSettings(b.dataset.integrationSection));
    }
    return page;
  }

  function ensureNav(){
    const group=q('.fs-settings-group');
    if(!group||q('[data-integrations-overview-nav]',group))return;
    const b=document.createElement('button');b.className='nav-item sub';b.type='button';b.dataset.integrationsOverviewNav='1';b.innerHTML='<span>Integrations</span>';
    const before=q('[data-polish-action="settings:notifications"]',group);
    group.insertBefore(b,before||null);
    b.onclick=e=>{e.stopPropagation();openIntegrations(b);};
  }

  function activate(button){qa('.side-nav .nav-item').forEach(x=>x.classList.remove('active'));button?.classList.add('active');}

  async function openExistingSettings(section){
    const b=q(`[data-polish-action="settings:${section}"]`);
    q('.fs-settings-group')?.classList.add('open');
    if(typeof window.openSettingsNav==='function')await window.openSettingsNav(section,b);
  }

  async function openIntegrations(button=q('[data-integrations-overview-nav]')){
    const page=ensurePage();if(!page)return;
    q('.fs-settings-group')?.classList.add('open');activate(button);
    qa('.pane').forEach(p=>p.classList.remove('active'));q('#settingsPane')?.classList.add('active');
    qa('#settingsPane .settings-page').forEach(p=>p.classList.toggle('active',p===page));
    const pageTitle=q('#pageTitle'),pageSubtitle=q('#pageSubtitle'),settingsTitle=q('#settingsTitle');
    if(pageTitle)pageTitle.textContent='Integrations';
    if(pageSubtitle)pageSubtitle.textContent='Optional services connected to Censorarr';
    if(settingsTitle)settingsTitle.textContent='Integrations';
    await refreshStates();
  }

  function setState(id,on,detail=''){
    const e=q(`#fsIntState-${id}`);if(!e)return;e.classList.toggle('on',!!on);e.textContent=on?(detail||'Configured'):(detail||'Not configured');
  }

  async function refreshStates(){
    try{
      const r=await fetch('/api/settings',{credentials:'same-origin'});if(!r.ok)throw new Error(`HTTP ${r.status}`);const s=await r.json();
      const arr=s.arr_integrations||{},sub=s.subtitle_assist||{},plex=s.rating_filter||{},tvPlex=s.tv?.rating_filter||{},wh=s.whisper||{};
      setState('sonarr',!!(arr.sonarr?.enabled&&String(arr.sonarr?.url||'').trim()));
      setState('radarr',!!(arr.radarr?.enabled&&String(arr.radarr?.url||'').trim()));
      setState('plex',!!(String(plex.plex_url||'').trim()||String(tvPlex.plex_url||'').trim()));
      setState('bazarr',!!(sub.bazarr?.enabled&&String(sub.bazarr?.url||'').trim()));
      const remote=String(wh.backend||'local')!=='local';setState('gpu',remote,remote?'Remote transcription configured':'Using local transcription');
      setState('subtitles',sub.enabled!==false,sub.enabled!==false?'Enabled':'Disabled');
    }catch(err){
      ['sonarr','radarr','plex','bazarr','gpu','subtitles'].forEach(id=>setState(id,false,'Status unavailable'));
    }
  }

  function wireViewAll(){const b=q('#fsIntOpen');if(b)b.onclick=e=>{e.preventDefault();openIntegrations();};}

  function boot(){addStyles();ensurePage();ensureNav();wireViewAll();setTimeout(wireViewAll,600);setTimeout(wireViewAll,1600);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,900));else setTimeout(boot,900);
})();
