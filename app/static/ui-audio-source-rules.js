(() => {
  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  let loading=false,saving=false,state={
    profanity_source_preference:'best_original',
    dialogue_source_preference:'auto_clean',
    dialogue_source_fallback:'original'
  };

  async function request(path,options={}){
    const r=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let data={};try{data=await r.json()}catch(_){ }
    if(!r.ok)throw new Error(data.detail||data.error||`HTTP ${r.status}`);return data;
  }

  function styles(){
    if(q('#fsAudioSourceRuleStyles'))return;
    const s=document.createElement('style');s.id='fsAudioSourceRuleStyles';s.textContent=`
      .fs-source-rules{margin-top:12px!important}
      .fs-source-rules-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}
      .fs-source-rules-head h3{margin:0!important}.fs-source-rules-head p{margin:4px 0 0;color:var(--muted);font-size:12px;max-width:760px}
      .fs-source-rules-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
      .fs-source-rule{padding:12px;background:var(--panel2);border:1px solid var(--line);border-radius:8px}
      .fs-source-rule label{display:block;font-weight:800;font-size:12px;margin-bottom:5px}.fs-source-rule select{width:100%}
      .fs-source-rule small{display:block;color:var(--muted);font-size:10px;line-height:1.45;margin-top:6px}
      .fs-source-preview{margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent2);background:color-mix(in srgb,var(--accent2) 7%,var(--panel2));font-size:11px;color:var(--muted)}
      .fs-source-save{font-size:11px;color:var(--muted);white-space:nowrap}.fs-source-save.good{color:#22c983}.fs-source-save.bad{color:var(--bad)}
      .wrap.fs-content-light .fs-source-rule{background:#f6f9fc!important;border-color:#d7e3ec!important}.wrap.fs-content-light .fs-source-preview{background:#eef6ff!important;color:#526b7e!important}
      @media(max-width:900px){.fs-source-rules-grid{grid-template-columns:1fr}}
    `;document.head.appendChild(s);
  }

  function panel(key){
    const box=document.createElement('div');box.className='section fs-source-rules';box.dataset.sourceRules=key;
    box.innerHTML=`<div class="fs-source-rules-head"><div><h3>Automation Source Rules</h3><p>Choose which audio Censorarr uses when processing the library automatically. Manual per-movie processing can override these defaults later.</p></div><span class="fs-source-save">Loading…</span></div>
      <div class="fs-source-rules-grid">
        <div class="fs-source-rule"><label>Profanity Censoring source</label><select class="fsProfanitySource">
          <option value="best_original">Auto — Best Original English Track</option>
          <option value="prefer_surround_original">Prefer Original Surround English</option>
          <option value="prefer_stereo_original">Prefer Original Stereo English</option>
        </select><small>Censorarr-generated CLEAN and Dialogue Enhanced tracks are never used as the profanity transcription source.</small></div>
        <div class="fs-source-rule"><label>Dialogue Enhancement source</label><select class="fsDialogueSource">
          <option value="auto_clean">Auto — Prefer CLEAN, then Original</option>
          <option value="original">Original audio</option>
          <option value="clean_only">CLEAN audio only</option>
        </select><small>Auto makes the enhanced track profanity-safe whenever a CLEAN track exists or is created during the same job.</small></div>
        <div class="fs-source-rule"><label>If preferred CLEAN is unavailable</label><select class="fsDialogueFallback">
          <option value="original">Fall back to Original</option>
          <option value="skip">Skip Dialogue Enhancement</option>
        </select><small>Skip is useful with CLEAN-only. The per-feature marker remembers the skip for the current settings so Censorarr does not retry it every scan.</small></div>
      </div><div class="fs-source-preview"></div>`;
    qa('select',box).forEach(x=>x.addEventListener('change',save));return box;
  }

  function ensure(){
    for(const [section,key] of [['general','general'],['detection','detection']]){
      const page=q(`.settings-page[data-settings="${section}"]`);if(!page||q(`[data-source-rules="${key}"]`,page))continue;
      const feature=q('[data-feature-panel]',page);const box=panel(key);
      if(feature)feature.insertAdjacentElement('afterend',box);else page.insertBefore(box,page.firstElementChild||null);
    }
    sync();
  }

  function status(text,kind=''){qa('.fs-source-save').forEach(x=>{x.textContent=text;x.classList.toggle('good',kind==='good');x.classList.toggle('bad',kind==='bad')})}

  function preview(){
    const d=state.dialogue_source_preference,f=state.dialogue_source_fallback;
    let text='';
    if(d==='original')text='Dialogue Enhanced will always be created from the selected original audio track, so profanity remains present in that enhanced track.';
    else if(d==='clean_only'&&f==='skip')text='Dialogue Enhanced will only be created when CLEAN exists. Media with no CLEAN track is recorded as Dialogue skipped for this source rule.';
    else if(d==='clean_only')text='Dialogue Enhanced will use CLEAN when available; otherwise Censorarr falls back to the best original audio track.';
    else text='Recommended: Censorarr uses CLEAN for Dialogue Enhancement whenever possible, and falls back to the best original track when CLEAN does not exist.';
    qa('.fs-source-preview').forEach(x=>x.textContent=text);
  }

  function sync(){
    qa('.fsProfanitySource').forEach(x=>x.value=state.profanity_source_preference);
    qa('.fsDialogueSource').forEach(x=>x.value=state.dialogue_source_preference);
    qa('.fsDialogueFallback').forEach(x=>x.value=state.dialogue_source_fallback);
    preview();
  }

  async function load(){
    if(loading)return;loading=true;
    try{
      const s=await request('/api/dialogue-enhancement/settings');
      state={
        profanity_source_preference:s.profanity_source_preference||'best_original',
        dialogue_source_preference:s.dialogue_source_preference||'auto_clean',
        dialogue_source_fallback:s.dialogue_source_fallback||'original'
      };sync();status('Saved automation defaults loaded.');
    }catch(e){status(`Could not load: ${e.message}`,'bad')}
    finally{loading=false}
  }

  async function save(e){
    if(saving)return;
    if(e?.target?.classList.contains('fsProfanitySource'))state.profanity_source_preference=e.target.value;
    if(e?.target?.classList.contains('fsDialogueSource'))state.dialogue_source_preference=e.target.value;
    if(e?.target?.classList.contains('fsDialogueFallback'))state.dialogue_source_fallback=e.target.value;
    sync();saving=true;status('Saving…');
    try{
      const result=await request('/api/dialogue-enhancement/settings',{method:'POST',body:JSON.stringify(state)});
      status(result.message||'Saved.','good');
    }catch(err){status(`Save failed: ${err.message}`,'bad');await load()}
    finally{saving=false}
  }

  function boot(){styles();ensure();load();setTimeout(()=>{ensure();load()},900)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,650));else setTimeout(boot,650);
})();
