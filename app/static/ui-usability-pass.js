(() => {
  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  let featureState={profanity:true,dialogue:false},saving=false,sorting=false;

  function addStyles(){
    if(q('#fsUsabilityStyles'))return;
    const s=document.createElement('style');s.id='fsUsabilityStyles';s.textContent=`
      /* Daylight mode owns only the main content area. The sidebar and top bar intentionally
         stay dark/teal. These rules are deliberately broad so legacy and newly-added pages
         cannot leave random dark islands behind. */
      .wrap.fs-content-light{
        --bg:#f3f7fb!important;--panel:#ffffff!important;--panel2:#f6f9fc!important;
        --panel3:#eaf1f7!important;--text:#142435!important;--muted:#647b8e!important;
        --line:#d6e2eb!important;--accent:#15966a!important;--accent2:#337eea!important;
        --warn:#9a6500!important;--bad:#c83f46!important;
        background:#f3f7fb!important;color:#142435!important;
      }

      .wrap.fs-content-light .card,
      .wrap.fs-content-light .panel,
      .wrap.fs-content-light .section,
      .wrap.fs-content-light .table-wrap,
      .wrap.fs-content-light .page-actions,
      .wrap.fs-content-light .media-card,
      .wrap.fs-content-light .season-card,
      .wrap.fs-content-light .mini-info,
      .wrap.fs-content-light .settings-head,
      .wrap.fs-content-light .settings-header,
      .wrap.fs-content-light .setting-callout,
      .wrap.fs-content-light .integration-card,
      .wrap.fs-content-light .fs-kpi,
      .wrap.fs-content-light .fs-media-panel,
      .wrap.fs-content-light .fs-side-card,
      .wrap.fs-content-light .fs-tipbar,
      .wrap.fs-content-light .fs-int,
      .wrap.fs-content-light .fs-ops-panel,
      .wrap.fs-content-light .fs-help-nav,
      .wrap.fs-content-light .fs-help-article,
      .wrap.fs-content-light .fs-integrations-overview-card,
      .wrap.fs-content-light .browser,
      .wrap.fs-content-light .review-list,
      .wrap.fs-content-light .warning,
      .wrap.fs-content-light .integration-notice,
      .wrap.fs-content-light details{
        background:#fff!important;color:#142435!important;border-color:#d5e1ea!important;
        box-shadow:none!important;
      }

      .wrap.fs-content-light .panel h2,
      .wrap.fs-content-light .panel h3,
      .wrap.fs-content-light .section h2,
      .wrap.fs-content-light .section h3,
      .wrap.fs-content-light .settings-page-title,
      .wrap.fs-content-light .settings-head h2,
      .wrap.fs-content-light .settings-header h2,
      .wrap.fs-content-light .fs-side-title h2,
      .wrap.fs-content-light .fs-section-head h2,
      .wrap.fs-content-light .fs-ops-panel h2,
      .wrap.fs-content-light .fs-help-article h1,
      .wrap.fs-content-light .fs-help-article h2,
      .wrap.fs-content-light .fs-help-article h3,
      .wrap.fs-content-light .media-title,
      .wrap.fs-content-light .episode-title,
      .wrap.fs-content-light .current,
      .wrap.fs-content-light .fs-ops-current{
        color:#142435!important;
      }

      .wrap.fs-content-light .muted,
      .wrap.fs-content-light .sub,
      .wrap.fs-content-light .footer-note,
      .wrap.fs-content-light .settings-page-desc,
      .wrap.fs-content-light .field label,
      .wrap.fs-content-light .media-year,
      .wrap.fs-content-light .media-sub,
      .wrap.fs-content-light .fs-card-sub,
      .wrap.fs-content-light .fs-kpi-label,
      .wrap.fs-content-light .fs-history th,
      .wrap.fs-content-light .fs-ops-meta,
      .wrap.fs-content-light .fs-integrations-overview-desc,
      .wrap.fs-content-light .fs-integrations-overview-state,
      .wrap.fs-content-light .fs-help-topic small{
        color:#647b8e!important;
      }

      .wrap.fs-content-light input,
      .wrap.fs-content-light select,
      .wrap.fs-content-light textarea{
        background:#f7fafc!important;color:#142435!important;border-color:#c8d8e3!important;
      }
      .wrap.fs-content-light input::placeholder,
      .wrap.fs-content-light textarea::placeholder{color:#8295a5!important}
      .wrap.fs-content-light input:focus,
      .wrap.fs-content-light select:focus,
      .wrap.fs-content-light textarea:focus{
        border-color:#40a7c7!important;box-shadow:0 0 0 2px rgba(38,153,187,.12)!important;
      }

      .wrap.fs-content-light button:not(.primary):not(.good):not(.danger):not(.fs-topbtn),
      .wrap.fs-content-light .fs-ops-segment button{
        background:#eef4f8!important;color:#21384a!important;border-color:#cbd9e3!important;
      }
      .wrap.fs-content-light button:hover:not(.fs-topbtn){background:#e5eef4!important}
      .wrap.fs-content-light .fs-ops-segment button.active,
      .wrap.fs-content-light .segmented button.active{
        background:#dcecff!important;color:#1f5da8!important;border-color:#b9d2ed!important;
      }

      .wrap.fs-content-light table,
      .wrap.fs-content-light .fs-history{color:#142435!important}
      .wrap.fs-content-light th,
      .wrap.fs-content-light .det.head{
        background:#f1f6fa!important;color:#62798c!important;border-color:#dce6ed!important;
      }
      .wrap.fs-content-light td,
      .wrap.fs-content-light .det,
      .wrap.fs-content-light .entry,
      .wrap.fs-content-light .fs-stat,
      .wrap.fs-content-light .fs-ops-stat,
      .wrap.fs-content-light .fs-ops-queue-row{
        color:#142435!important;border-color:#dce6ed!important;
      }
      .wrap.fs-content-light tr:hover td,
      .wrap.fs-content-light .entry:hover{background:#f7fafc!important}

      .wrap.fs-content-light .badge,
      .wrap.fs-content-light .summary-chip{
        background:#eef4f8!important;color:#526b7e!important;border-color:#d2dfe8!important;
      }
      .wrap.fs-content-light .badge.good{background:#edf9f3!important;color:#12865c!important;border-color:#a9ddc6!important}
      .wrap.fs-content-light .badge.warn{background:#fff8e8!important;color:#946000!important;border-color:#ead29d!important}
      .wrap.fs-content-light .badge.bad{background:#fff0f1!important;color:#b83b43!important;border-color:#edb9bd!important}
      .wrap.fs-content-light .fs-success{background:#eaf8f0!important;color:#148254!important}
      .wrap.fs-content-light .optional-label{background:#e8f1ff!important;color:#2f6fca!important}

      .wrap.fs-content-light .fs-meter,
      .wrap.fs-content-light .bar,
      .wrap.fs-content-light .fs-ops-bar{background:#e3ecf2!important}
      .wrap.fs-content-light .fs-integrations-overview-icon{background:#f0f5f8!important}
      .wrap.fs-content-light .fs-poster-placeholder,
      .wrap.fs-content-light .poster.placeholder{background:#eaf1f6!important;color:#6f8596!important}
      .wrap.fs-content-light .empty-state{background:#fff!important;color:#6d8292!important;border-color:#cbdbe6!important}
      .wrap.fs-content-light .daypick label{background:#f7fafc!important;color:#253c4e!important;border-color:#cbd9e3!important}

      /* Help/Wiki content. Code blocks stay slightly tinted, but not black. */
      .wrap.fs-content-light .fs-help-topic:hover{background:#f1f6fa!important}
      .wrap.fs-content-light .fs-help-topic.active{background:#e5f0ff!important;color:#194d88!important}
      .wrap.fs-content-light .fs-help-callout{background:#eef6ff!important;border-color:#c4dafa!important;color:#20384d!important}
      .wrap.fs-content-light .fs-help-article pre,
      .wrap.fs-content-light .fs-help-article code:not(pre code){background:#edf3f7!important;color:#233b4c!important;border-color:#d2dee7!important}
      .wrap.fs-content-light .fs-help-article pre code{color:#233b4c!important}

      /* Media details: keep fanart readable, but remove the black fallback block in day mode. */
      .wrap.fs-content-light .detail-hero{background:#dce8f0!important}
      .wrap.fs-content-light .movie-file-card .mini-info{background:#f7fafc!important}

      /* Settings-specific cleanup. */
      .wrap.fs-content-light #settingsPane .settings-header,
      .wrap.fs-content-light #settingsPane .settings-head{background:#f8fbfd!important}
      .wrap.fs-content-light #settingsPane .section,
      .wrap.fs-content-light #settingsPane .setting-callout,
      .wrap.fs-content-light #settingsPane .field,
      .wrap.fs-content-light #settingsPane .table-wrap{
        background:#fff!important;color:#142435!important;border-color:#d5e1ea!important;box-shadow:none!important;
      }
      .wrap.fs-content-light #settingsPane .setting-callout{background:#f4f8fb!important;color:#647b8e!important}

      /* The operational/live-log console is intentionally dark in BOTH modes for readability.
         Everything surrounding it follows daylight mode. */
      .wrap.fs-content-light .fs-ops-log,
      .wrap.fs-content-light .log{
        background:#060a0f!important;color:#c9d9e7!important;border-color:#1d2b39!important;
      }

      .fs-feature-master{margin-bottom:14px!important;border:1px solid color-mix(in srgb,var(--accent2) 28%,var(--line))!important}
      .fs-feature-master-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}
      .fs-feature-master-head h3{margin:0!important;font-size:18px!important}.fs-feature-master-head p{margin:4px 0 0;color:var(--muted);font-size:12px;max-width:760px}
      .fs-feature-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
      .fs-feature-card{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:14px;padding:14px;border:1px solid var(--line);background:var(--panel2);border-radius:8px;transition:.16s}
      .fs-feature-card.on{border-color:color-mix(in srgb,#22c983 55%,var(--line));background:color-mix(in srgb,#22c983 7%,var(--panel2))}
      .fs-feature-name{display:flex;align-items:center;gap:8px;font-weight:800;font-size:14px}.fs-feature-state{font-size:10px;padding:2px 7px;border-radius:999px;background:color-mix(in srgb,var(--muted) 14%,transparent);color:var(--muted)}
      .fs-feature-card.on .fs-feature-state{background:color-mix(in srgb,#22c983 18%,transparent);color:#22c983}.fs-feature-desc{color:var(--muted);font-size:11px;margin-top:4px;line-height:1.4}
      .fs-switch{position:relative;width:48px;height:27px;display:inline-block;flex:0 0 auto}.fs-switch input{opacity:0;width:0;height:0;position:absolute}.fs-switch span{position:absolute;inset:0;border-radius:999px;background:#526979;cursor:pointer;transition:.18s}.fs-switch span:before{content:'';position:absolute;width:21px;height:21px;left:3px;top:3px;border-radius:50%;background:white;box-shadow:0 1px 4px rgba(0,0,0,.28);transition:.18s}.fs-switch input:checked+span{background:#18b879}.fs-switch input:checked+span:before{transform:translateX(21px)}
      .fs-feature-save-state{font-size:11px;color:var(--muted);white-space:nowrap}.fs-feature-save-state.good{color:#22c983}.fs-feature-save-state.bad{color:var(--bad)}
      .wrap.fs-content-light .fs-feature-card{background:#f6f9fc!important;border-color:#d7e3ec!important}.wrap.fs-content-light .fs-feature-card.on{background:#effbf6!important;border-color:#9dddc2!important}

      #fsIntegrations .fs-int-icon{background:transparent!important;width:27px!important;height:27px!important;border-radius:5px!important;overflow:visible!important}
      #fsIntegrations .fs-int-icon img{display:block;width:27px;height:27px;object-fit:contain}
      #fsIntegrations .fs-int-icon img.fs-bazarr-logo{background:#fff;border-radius:50%}
      @media(max-width:760px){.fs-feature-grid{grid-template-columns:1fr}}
    `;document.head.appendChild(s);
  }

  async function request(path,options={}){
    const r=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let data={};try{data=await r.json()}catch(_){ }
    if(!r.ok)throw new Error(data.detail||data.error||`HTTP ${r.status}`);return data;
  }

  function featurePanel(key){
    const box=document.createElement('div');box.className='section fs-feature-master';box.dataset.featurePanel=key;
    box.innerHTML=`<div class="fs-feature-master-head"><div><h3>Audio Features</h3><p>Choose these independently. Profanity Censoring creates the CLEAN track. Dialogue Enhancement creates a separate speech-focused track. You can run either one, both, or neither.</p></div><span class="fs-feature-save-state">Loading…</span></div><div class="fs-feature-grid"><div class="fs-feature-card" data-feature-card="profanity"><div><div class="fs-feature-name">Profanity Censoring <span class="fs-feature-state">OFF</span></div><div class="fs-feature-desc">Detect configured profanity and create/replace the muted CLEAN audio track.</div></div><label class="fs-switch" title="Toggle Profanity Censoring"><input class="fsProfanityToggle" type="checkbox"><span></span></label></div><div class="fs-feature-card" data-feature-card="dialogue"><div><div class="fs-feature-name">Dialogue Enhancement <span class="fs-feature-state">OFF</span></div><div class="fs-feature-desc">Create a separate speech-focused stereo track. If censoring is off, Whisper is skipped completely.</div></div><label class="fs-switch" title="Toggle Dialogue Enhancement"><input class="fsDialogueToggle" type="checkbox"><span></span></label></div></div>`;
    qa('input',box).forEach(el=>el.addEventListener('change',saveFeatures));
    return box;
  }

  function ensureFeaturePanels(){
    const pages=[['general','general'],['detection','detection']];
    for(const [section,key] of pages){
      const page=q(`.settings-page[data-settings="${section}"]`);if(!page||q(`[data-feature-panel="${key}"]`,page))continue;
      const panel=featurePanel(key);page.insertBefore(panel,page.firstElementChild||null);
    }
    const old=q('#sDialogueEnabled');if(old){const field=old.closest('.field');if(field)field.style.display='none';}
    const h=q('#dialogueEnhancementSection h3');if(h){h.childNodes[0].nodeValue='Dialogue Enhancement Details ';const tag=q('.optional-label',h);if(tag)tag.textContent='Advanced';}
    syncFeatureUi();
  }

  function syncFeatureUi(){
    qa('.fsProfanityToggle').forEach(x=>x.checked=!!featureState.profanity);
    qa('.fsDialogueToggle').forEach(x=>x.checked=!!featureState.dialogue);
    qa('[data-feature-card="profanity"]').forEach(card=>{card.classList.toggle('on',!!featureState.profanity);const s=q('.fs-feature-state',card);if(s)s.textContent=featureState.profanity?'ON':'OFF';});
    qa('[data-feature-card="dialogue"]').forEach(card=>{card.classList.toggle('on',!!featureState.dialogue);const s=q('.fs-feature-state',card);if(s)s.textContent=featureState.dialogue?'ON':'OFF';});
    const old=q('#sDialogueEnabled');if(old)old.value=String(!!featureState.dialogue);
  }

  function featureStatus(text,kind=''){
    qa('.fs-feature-save-state').forEach(x=>{x.textContent=text;x.classList.toggle('good',kind==='good');x.classList.toggle('bad',kind==='bad');});
  }

  async function loadFeatures(){
    try{const s=await request('/api/dialogue-enhancement/settings');featureState={profanity:s.profanity_censoring_enabled!==false,dialogue:!!s.enabled};syncFeatureUi();featureStatus('Changes apply after the current item.');}
    catch(e){featureStatus(`Could not load: ${e.message}`,'bad');}
  }

  async function saveFeatures(e){
    if(saving)return;
    const next={profanity:q('.fsProfanityToggle')?.checked??featureState.profanity,dialogue:q('.fsDialogueToggle')?.checked??featureState.dialogue};
    if(e?.target?.classList.contains('fsProfanityToggle'))next.profanity=e.target.checked;
    if(e?.target?.classList.contains('fsDialogueToggle'))next.dialogue=e.target.checked;
    featureState=next;syncFeatureUi();saving=true;featureStatus('Saving…');
    try{
      const result=await request('/api/dialogue-enhancement/settings',{method:'POST',body:JSON.stringify({enabled:featureState.dialogue,profanity_censoring_enabled:featureState.profanity})});
      featureStatus('Saved — worker reloads after the current item.','good');
      const old=q('#dialogueEnhancementStatus');if(old)old.textContent=result.message||'Saved.';
    }catch(err){featureStatus(`Save failed: ${err.message}`,'bad');await loadFeatures();}
    finally{saving=false;}
  }

  function sortAllMedia(){
    const grid=q('#fsAllGrid');if(!grid||sorting)return;
    const cards=qa(':scope > .media-card',grid);if(cards.length<2)return;
    const sorted=[...cards].sort((a,b)=>{
      const at=(q('.media-title',a)?.textContent||'').trim();const bt=(q('.media-title',b)?.textContent||'').trim();
      return at.localeCompare(bt,undefined,{numeric:true,sensitivity:'base'});
    });
    if(sorted.every((card,i)=>card===cards[i]))return;
    sorting=true;const frag=document.createDocumentFragment();sorted.forEach(c=>frag.appendChild(c));grid.appendChild(frag);sorting=false;
  }

  function watchAllMedia(){
    const grid=q('#fsAllGrid');if(!grid||grid.dataset.alphaWatch==='1')return;
    grid.dataset.alphaWatch='1';new MutationObserver(()=>sortAllMedia()).observe(grid,{childList:true});sortAllMedia();
  }

  const iconMap={
    'sonarr':['/assets/sonarr.svg','Sonarr'],
    'radarr':['/assets/radarr.svg','Radarr'],
    'plex':['/assets/plex.svg','Plex'],
    'bazarr':['/assets/bazarr.svg','Bazarr'],
    'gpu worker':['/assets/censorarr-favicon-wave.svg?v=7','Censorarr GPU Worker']
  };
  function applyIntegrationIcons(){
    qa('#fsIntegrations .fs-int').forEach(card=>{
      const name=(q('.fs-int-name',card)?.textContent||'').trim().toLowerCase();const spec=iconMap[name];if(!spec)return;
      const holder=q('.fs-int-icon',card);if(!holder)return;
      const old=q('img',holder);if(old&&old.getAttribute('src')===spec[0])return;
      holder.innerHTML=`<img src="${spec[0]}" alt="${spec[1]}"${name==='bazarr'?' class="fs-bazarr-logo"':''}>`;
    });
  }

  function watchIntegrations(){
    const box=q('#fsIntegrations');if(!box||box.dataset.realIconWatch==='1')return;
    box.dataset.realIconWatch='1';new MutationObserver(()=>applyIntegrationIcons()).observe(box,{childList:true,subtree:false});applyIntegrationIcons();
  }

  function wireDialogueDetailSync(){
    const sel=q('#sDialogueEnabled');if(!sel||sel.dataset.masterSynced==='1')return;sel.dataset.masterSynced='1';sel.addEventListener('change',()=>{featureState.dialogue=sel.value==='true';syncFeatureUi();});
  }

  function boot(){
    addStyles();ensureFeaturePanels();watchAllMedia();watchIntegrations();wireDialogueDetailSync();loadFeatures();
    setTimeout(()=>{ensureFeaturePanels();watchAllMedia();watchIntegrations();wireDialogueDetailSync();sortAllMedia();applyIntegrationIcons();},900);
    setInterval(()=>{watchAllMedia();watchIntegrations();sortAllMedia();applyIntegrationIcons();},3000);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,500));else setTimeout(boot,500);
})();
