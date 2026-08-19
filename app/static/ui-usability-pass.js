(() => {
  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  let featureState={profanity:true,dialogue:false},saving=false,sorting=false;

  function addStyles(){
    if(q('#fsUsabilityStyles'))return;
    const s=document.createElement('style');s.id='fsUsabilityStyles';s.textContent=`
      /* Light mode should actually make the CONTENT cards light while leaving the
         teal top bar and blue sidebar unchanged. */
      .wrap.fs-content-light #settingsPane .settings-header,
      .wrap.fs-content-light #settingsPane .section,
      .wrap.fs-content-light #settingsPane .setting-callout,
      .wrap.fs-content-light #settingsPane .field,
      .wrap.fs-content-light #settingsPane .table-wrap{
        background:#fff!important;color:#142435!important;border-color:#d5e1ea!important;box-shadow:none!important
      }
      .wrap.fs-content-light #settingsPane .settings-header{background:#f8fbfd!important}
      .wrap.fs-content-light #settingsPane .section h2,
      .wrap.fs-content-light #settingsPane .section h3,
      .wrap.fs-content-light #settingsPane .field label,
      .wrap.fs-content-light #settingsPane .settings-header h2{color:#142435!important}
      .wrap.fs-content-light #settingsPane .footer-note,
      .wrap.fs-content-light #settingsPane .setting-callout,
      .wrap.fs-content-light #settingsPane .muted{color:#647b8e!important}
      .wrap.fs-content-light #settingsPane input,
      .wrap.fs-content-light #settingsPane select,
      .wrap.fs-content-light #settingsPane textarea{
        background:#f7fafc!important;color:#142435!important;border-color:#c8d8e3!important
      }
      .wrap.fs-content-light #settingsPane input:focus,
      .wrap.fs-content-light #settingsPane select:focus,
      .wrap.fs-content-light #settingsPane textarea:focus{border-color:#40a7c7!important;box-shadow:0 0 0 2px rgba(38,153,187,.12)!important}
      .wrap.fs-content-light #settingsPane button:not(.primary):not(.good):not(.danger){background:#eef4f8!important;color:#21384a!important;border-color:#cbd9e3!important}
      .wrap.fs-content-light #settingsPane .optional-label{background:#e8f1ff!important;color:#2f6fca!important}

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
    // The detailed Dialogue section remains useful for strength/codec settings, but the
    // duplicate enable dropdown is hidden so there is only one obvious master switch.
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
    // The toggle that fired is authoritative; mirror duplicate panels before saving.
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
