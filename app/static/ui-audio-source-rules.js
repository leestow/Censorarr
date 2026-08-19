(() => {
  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  let loading=false,saving=false,state={
    profanity_source_preference:'best_original',
    dialogue_source_preference:'auto_clean',
    dialogue_source_fallback:'original',
    method:'ai',
    ai_model:'mdx_q',
    ai_fallback_classic:true,
    ai_worker_cpu_fallback:true
  };
  let aiStatus=null;

  async function request(path,options={}){
    const r=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let data={};try{data=await r.json()}catch(_){ }
    if(!r.ok)throw new Error(data.detail||data.error||`HTTP ${r.status}`);return data;
  }

  function styles(){
    if(q('#fsAudioSourceRuleStyles'))return;
    const s=document.createElement('style');s.id='fsAudioSourceRuleStyles';s.textContent=`
      .fs-source-rules,.fs-ai-dialogue-rules{margin-top:12px!important}
      .fs-source-rules-head,.fs-ai-dialogue-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:12px}
      .fs-source-rules-head h3,.fs-ai-dialogue-head h3{margin:0!important}.fs-source-rules-head p,.fs-ai-dialogue-head p{margin:4px 0 0;color:var(--muted);font-size:12px;max-width:760px}
      .fs-source-rules-grid,.fs-ai-dialogue-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
      .fs-source-rule,.fs-ai-rule{padding:12px;background:var(--panel2);border:1px solid var(--line);border-radius:8px}
      .fs-source-rule label,.fs-ai-rule label{display:block;font-weight:800;font-size:12px;margin-bottom:5px}.fs-source-rule select,.fs-ai-rule select{width:100%}
      .fs-source-rule small,.fs-ai-rule small{display:block;color:var(--muted);font-size:10px;line-height:1.45;margin-top:6px}
      .fs-source-preview,.fs-ai-preview{margin-top:10px;padding:10px 12px;border-left:3px solid var(--accent2);background:color-mix(in srgb,var(--accent2) 7%,var(--panel2));font-size:11px;color:var(--muted);line-height:1.5}
      .fs-source-save,.fs-ai-worker{font-size:11px;color:var(--muted);white-space:nowrap}.fs-source-save.good,.fs-ai-worker.good{color:#22c983}.fs-source-save.bad,.fs-ai-worker.bad{color:var(--bad)}
      .fs-ai-rule.disabled{opacity:.52}.fs-ai-rule.disabled select{pointer-events:none}
      .wrap.fs-content-light .fs-source-rule,.wrap.fs-content-light .fs-ai-rule{background:#f6f9fc!important;border-color:#d7e3ec!important}.wrap.fs-content-light .fs-source-preview,.wrap.fs-content-light .fs-ai-preview{background:#eef6ff!important;color:#526b7e!important}

      /* General is for global behavior. Advanced audio tuning lives under Processing Rules. */
      .settings-page[data-settings="general"].fs-general-organized{
        display:grid!important;grid-template-columns:minmax(0,1.7fr) minmax(310px,.8fr);gap:14px!important;align-items:start;max-width:1380px!important;width:100%!important
      }
      .settings-page[data-settings="general"].fs-general-organized>.settings-page-title,
      .settings-page[data-settings="general"].fs-general-organized>.settings-page-desc,
      .settings-page[data-settings="general"].fs-general-organized>[data-feature-panel="general"]{grid-column:1/-1}
      .settings-page[data-settings="general"]>[data-feature-panel="general"]{order:2;margin:0!important}
      .settings-page[data-settings="general"]>[data-general-section="processing"]{grid-column:1;order:3;margin:0!important}
      .settings-page[data-settings="general"]>[data-general-section="schedule"]{grid-column:2;order:4;margin:0!important}
      .settings-page[data-settings="general"]>.fs-general-next{grid-column:1/-1;order:5}
      .settings-page[data-settings="general"]>.settings-page-title{order:0;margin:0!important}
      .settings-page[data-settings="general"]>.settings-page-desc{order:1;margin:-8px 0 2px!important;max-width:980px}
      .settings-page[data-settings="general"] [data-general-section]{background:var(--panel)!important;border:1px solid var(--line)!important;padding:17px 18px!important;border-radius:10px!important}
      .settings-page[data-settings="general"] [data-general-section] h3{font-size:16px!important;margin-bottom:4px!important}
      .fs-general-section-desc{font-size:11px;color:var(--muted);line-height:1.45;margin:0 0 15px}
      .settings-page[data-settings="general"] [data-general-section] .field{margin-bottom:12px}
      .settings-page[data-settings="general"] [data-general-section] .field>label{font-weight:750;color:var(--text);font-size:11px}
      .settings-page[data-settings="general"] [data-general-section] input,
      .settings-page[data-settings="general"] [data-general-section] select{width:100%}
      .fs-general-help{font-size:10px;color:var(--muted);line-height:1.4;margin-top:4px}
      .fs-general-next{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px 16px;border:1px solid color-mix(in srgb,var(--accent2) 32%,var(--line));background:color-mix(in srgb,var(--accent2) 6%,var(--panel));border-radius:9px}
      .fs-general-next h3{margin:0 0 3px!important;font-size:14px!important}.fs-general-next p{margin:0;color:var(--muted);font-size:11px;line-height:1.45;max-width:850px}.fs-general-next button{white-space:nowrap}
      .settings-page[data-settings="general"] .fs-feature-master-head h3{font-size:16px!important}
      .settings-page[data-settings="general"] .fs-feature-master{padding:17px 18px!important;background:var(--panel)!important;border-radius:10px!important}
      .settings-page[data-settings="general"] .fs-feature-card{padding:13px 14px!important}
      .settings-page[data-settings="general"] .fs-feature-desc{font-size:10px!important}
      .wrap.fs-content-light .fs-general-next{background:#f4f8fc!important;border-color:#c9dced!important}.wrap.fs-content-light .settings-page[data-settings="general"] [data-general-section]{background:#fff!important}
      @media(max-width:1100px){.settings-page[data-settings="general"].fs-general-organized{grid-template-columns:1fr!important}.settings-page[data-settings="general"]>[data-general-section="processing"],.settings-page[data-settings="general"]>[data-general-section="schedule"]{grid-column:1!important}}
      @media(max-width:900px){.fs-source-rules-grid,.fs-ai-dialogue-grid{grid-template-columns:1fr}.fs-general-next{align-items:flex-start;flex-direction:column}}
    `;document.head.appendChild(s);
  }

  function sourcePanel(key){
    const box=document.createElement('div');box.className='section fs-source-rules';box.dataset.sourceRules=key;
    box.innerHTML=`<div class="fs-source-rules-head"><div><h3>Audio Source Rules</h3><p>Choose which audio Censorarr uses when it builds CLEAN and Dialogue Enhanced tracks automatically.</p></div><span class="fs-source-save">Loading…</span></div>
      <div class="fs-source-rules-grid">
        <div class="fs-source-rule"><label>Profanity Censoring starts from</label><select class="fsProfanitySource">
          <option value="best_original">Auto — Best Original English Track</option>
          <option value="prefer_surround_original">Prefer Original Surround English</option>
          <option value="prefer_stereo_original">Prefer Original Stereo English</option>
        </select><small>Generated CLEAN and Dialogue Enhanced tracks are never used as the profanity transcription source.</small></div>
        <div class="fs-source-rule"><label>Dialogue Enhancement starts from</label><select class="fsDialogueSource">
          <option value="auto_clean">Auto — Prefer CLEAN, then Original</option>
          <option value="original">Original audio</option>
          <option value="clean_only">CLEAN audio only</option>
        </select><small>Recommended Auto keeps the enhanced track profanity-safe whenever a CLEAN track exists or is created in the same job.</small></div>
        <div class="fs-source-rule"><label>If CLEAN is unavailable</label><select class="fsDialogueFallback">
          <option value="original">Fall back to Original</option>
          <option value="skip">Skip Dialogue Enhancement</option>
        </select><small>This only matters when Dialogue Enhancement is configured to prefer or require CLEAN audio.</small></div>
      </div><div class="fs-source-preview"></div>`;
    qa('select',box).forEach(x=>x.addEventListener('change',save));return box;
  }

  function aiPanel(key){
    const box=document.createElement('div');box.className='section fs-ai-dialogue-rules';box.dataset.aiDialogueRules=key;
    box.innerHTML=`<div class="fs-ai-dialogue-head"><div><h3>Dialogue Enhancement Engine</h3><p>Choose how speech is isolated and what Censorarr should do if the preferred AI path cannot finish.</p></div><span class="fs-ai-worker">Checking GPU worker…</span></div>
      <div class="fs-ai-dialogue-grid">
        <div class="fs-ai-rule"><label>Enhancement method</label><select class="fsDialogueMethod">
          <option value="ai">AI Dialogue Isolation — Recommended</option>
          <option value="classic">Classic Center / EQ / Compression</option>
        </select><small>AI isolates a speech stem and uses it to control the mix. Classic processing is faster but less selective.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>AI separation model</label><select class="fsDialogueAiModel">
          <option value="mdx_q">MDX-Q — lower memory / recommended</option>
          <option value="htdemucs">HTDemucs — heavier</option>
        </select><small>MDX-Q is the recommended first choice for smaller GPUs. Whisper is unloaded before separation to free VRAM.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>If AI cannot complete</label><select class="fsDialogueAiFallback">
          <option value="true">Fall back to Classic</option>
          <option value="false">Fail the item instead</option>
        </select><small>Classic fallback keeps automation moving if AI separation is unavailable.</small></div>
      </div>
      <div class="fs-ai-dialogue-grid" style="margin-top:10px">
        <div class="fs-ai-rule" data-ai-only><label>If GPU separation fails</label><select class="fsDialogueAiCpuFallback">
          <option value="true">Retry AI on worker CPU</option>
          <option value="false">Do not retry on CPU</option>
        </select><small>CPU fallback is much slower, but it can finish a movie if the GPU runs out of memory.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>Dialogue-aware ducking</label><div style="font-weight:800;padding:8px 0">Always ON in AI mode</div><small>Background sound is reduced only while detected dialogue is active.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>Strength</label><div style="font-weight:800;padding:8px 0">Speech lift + background ducking</div><small>Light ≈ 2 dB duck, Medium ≈ 4 dB, Strong ≈ 6 dB. The detailed strength control is below.</small></div>
      </div><div class="fs-ai-preview"></div>`;
    qa('select',box).forEach(x=>x.addEventListener('change',save));return box;
  }

  function addHelp(controlId,text){
    const el=q('#'+controlId);const field=el?.closest('.field');if(!field||q('.fs-general-help',field))return;
    const note=document.createElement('div');note.className='fs-general-help';note.textContent=text;field.appendChild(note);
  }

  function organizeGeneral(){
    const page=q('.settings-page[data-settings="general"]');if(!page)return;
    page.classList.add('fs-general-organized');

    // These advanced controls used to be duplicated on General and Processing Rules.
    // Keep only the Processing Rules copies so General remains genuinely general.
    qa('[data-source-rules="general"],[data-ai-dialogue-rules="general"]',page).forEach(x=>x.remove());

    const title=q('.settings-page-title',page);if(title)title.textContent='General';
    const desc=q('.settings-page-desc',page);if(desc)desc.textContent='Turn Censorarr features on or off and choose when automatic processing should run. Audio tuning and AI behavior live under Processing Rules.';

    const feature=q('[data-feature-panel="general"]',page);
    if(feature){
      const h=q('.fs-feature-master-head h3',feature);if(h)h.textContent='Audio Features';
      const p=q('.fs-feature-master-head p',feature);if(p)p.textContent='Choose what Censorarr should create. These switches are independent: use Profanity Censoring, Dialogue Enhancement, both, or neither.';
      if(desc)desc.insertAdjacentElement('afterend',feature);else page.prepend(feature);
    }

    const sections=qa(':scope > .section',page).filter(x=>!x.matches('[data-feature-panel]'));
    const processing=sections.find(x=>q('h3',x)?.textContent.trim().toLowerCase()==='processing');
    const schedule=sections.find(x=>q('h3',x)?.textContent.trim().toLowerCase()==='processing schedule');

    if(processing){
      processing.dataset.generalSection='processing';
      const h=q('h3',processing);if(h)h.textContent='Automatic Processing';
      if(!q('.fs-general-section-desc',processing))h?.insertAdjacentHTML('afterend','<div class="fs-general-section-desc">Controls how Censorarr watches the library and remembers completed media.</div>');
    }
    if(schedule){
      schedule.dataset.generalSection='schedule';
      const h=q('h3',schedule);if(h)h.textContent='Processing Schedule';
      if(!q('.fs-general-section-desc',schedule))h?.insertAdjacentHTML('afterend','<div class="fs-general-section-desc">Optional quiet-hours window for automatic library processing. Manual Process/Reprocess remains available.</div>');
    }

    // Dry Run is retired in the family-safe build. Keep the hidden legacy control only
    // because the stable save routine still reads its value.
    const dry=q('#sDry');if(dry){dry.value='false';const field=dry.closest('.field');if(field)field.style.display='none';}

    const labels={
      sExtensions:'Media types to watch',sScan:'Check library every (seconds)',sStable:'Wait for files to stop changing (seconds)',
      sProcessExisting:'Process media already in the library',sMarkerEnabled:'Remember completed media',sMarkerFilename:'Completion marker filename',
      sSchedEnabled:'Use an automatic processing schedule',sSchedStart:'Start processing at',sSchedEnd:'Stop processing at'
    };
    for(const [id,text] of Object.entries(labels)){const el=q('#'+id);const label=el?.closest('.field')?.querySelector('label');if(label)label.textContent=text;}
    addHelp('sExtensions','Usually leave this at the standard video extensions unless your library uses another container format.');
    addHelp('sScan','How often Censorarr checks for new or changed media when automation is running.');
    addHelp('sStable','Prevents Censorarr from touching a file that is still being copied or downloaded.');
    addHelp('sProcessExisting','Yes scans the existing library too. New/changed only limits normal automation to future changes.');
    addHelp('sMarkerEnabled','Recommended. Prevents unchanged media from being processed repeatedly.');

    let next=q('.fs-general-next',page);
    if(!next){
      next=document.createElement('div');next.className='fs-general-next';
      next.innerHTML='<div><h3>Need to tune how the audio is processed?</h3><p>Audio source selection, AI model, GPU/CPU fallback, dialogue ducking behavior, detection settings, and other processing details are under <b>Processing Rules</b>.</p></div><button type="button" class="primary">Open Processing Rules</button>';
      q('button',next).onclick=()=>{
        const nav=q('[data-final-action="rules"]');
        if(nav?.click)return nav.click();
        window.openSettingsNav?.('detection',nav||null);
      };
      page.appendChild(next);
    }
  }

  function rewriteLegacyCopy(){
    const callout=q('#dialogueEnhancementSection .setting-callout');
    if(callout)callout.textContent='Creates an additional speech-focused stereo track while preserving CLEAN and original audio. AI mode isolates human dialogue on the GPU worker, dynamically ducks competing music/effects while speech is active, then mixes the enhanced dialogue back in. Classic mode remains available as a fast lightweight alternative.';
    const note=q('#dialogueEnhancementSection .footer-note');
    if(note)note.textContent='Medium is the recommended starting point. In AI mode, strength changes both speech emphasis and dialogue-triggered background ducking.';
  }

  function ensure(){
    // Advanced source/engine controls belong under Processing Rules (Detection), not General.
    const page=q('.settings-page[data-settings="detection"]');
    if(page){
      let source=q('[data-source-rules="detection"]',page);
      if(!source){
        source=sourcePanel('detection');const feature=q('[data-feature-panel]',page);
        if(feature)feature.insertAdjacentElement('afterend',source);else page.insertBefore(source,page.firstElementChild||null);
      }
      if(!q('[data-ai-dialogue-rules="detection"]',page))source.insertAdjacentElement('afterend',aiPanel('detection'));
    }
    organizeGeneral();rewriteLegacyCopy();sync();
  }

  function status(text,kind=''){qa('.fs-source-save').forEach(x=>{x.textContent=text;x.classList.toggle('good',kind==='good');x.classList.toggle('bad',kind==='bad')})}

  function sourcePreview(){
    const d=state.dialogue_source_preference,f=state.dialogue_source_fallback;
    let text='';
    if(d==='original')text='Dialogue Enhanced will always be created from the selected original audio track, so profanity remains present in that enhanced track.';
    else if(d==='clean_only'&&f==='skip')text='Dialogue Enhanced will only be created when CLEAN exists. Media with no CLEAN track is recorded as Dialogue skipped for this source rule.';
    else if(d==='clean_only')text='Dialogue Enhanced will use CLEAN when available; otherwise Censorarr falls back to the best original audio track.';
    else text='Recommended: Censorarr uses CLEAN for Dialogue Enhancement whenever possible, and falls back to the best original track when CLEAN does not exist.';
    qa('.fs-source-preview').forEach(x=>x.textContent=text);
  }

  function aiPreview(){
    let text='';
    if(state.method==='classic')text='Classic mode does not run AI separation. It emphasizes likely dialogue using center-channel weighting, speech EQ and compression. It is much faster but less selective.';
    else text='AI mode: isolate dialogue → use the dialogue stem as a sidechain key → smoothly lower the original soundtrack only while speech is active → add the isolated speech layer back → limit final peaks. Music and explosions return to their normal level when nobody is speaking.';
    qa('[data-ai-dialogue-rules] .fs-ai-preview').forEach(x=>x.textContent=text);
    qa('[data-ai-dialogue-rules] [data-ai-only]').forEach(x=>x.classList.toggle('disabled',state.method!=='ai'));
  }

  function sync(){
    qa('.fsProfanitySource').forEach(x=>x.value=state.profanity_source_preference);
    qa('.fsDialogueSource').forEach(x=>x.value=state.dialogue_source_preference);
    qa('.fsDialogueFallback').forEach(x=>x.value=state.dialogue_source_fallback);
    qa('.fsDialogueMethod').forEach(x=>x.value=state.method);
    qa('.fsDialogueAiModel').forEach(x=>x.value=state.ai_model);
    qa('.fsDialogueAiFallback').forEach(x=>x.value=String(state.ai_fallback_classic));
    qa('.fsDialogueAiCpuFallback').forEach(x=>x.value=String(state.ai_worker_cpu_fallback));
    sourcePreview();aiPreview();
  }

  async function checkAI(){
    try{
      aiStatus=await request('/api/dialogue-enhancement/ai-status');
      const ready=!!aiStatus.dialogue_ai;
      const device=Number(aiStatus.cuda_devices||0)>0?'CUDA GPU':'CPU only';
      const version=aiStatus.version?` · worker ${aiStatus.version}`:'';
      qa('.fs-ai-worker').forEach(x=>{x.textContent=ready?`AI worker ready · ${device}${version}`:`AI unavailable${aiStatus.reason?` · ${aiStatus.reason}`:''}`;x.classList.toggle('good',ready);x.classList.toggle('bad',!ready)});
    }catch(e){qa('.fs-ai-worker').forEach(x=>{x.textContent=`AI status unavailable · ${e.message}`;x.classList.remove('good');x.classList.add('bad')})}
  }

  async function load(){
    if(loading)return;loading=true;
    try{
      const s=await request('/api/dialogue-enhancement/settings');
      state={
        profanity_source_preference:s.profanity_source_preference||'best_original',
        dialogue_source_preference:s.dialogue_source_preference||'auto_clean',
        dialogue_source_fallback:s.dialogue_source_fallback||'original',
        method:s.method||'ai',
        ai_model:s.ai_model||'mdx_q',
        ai_fallback_classic:s.ai_fallback_classic!==false,
        ai_worker_cpu_fallback:s.ai_worker_cpu_fallback!==false
      };sync();status('Saved processing rules loaded.');await checkAI();
    }catch(e){status(`Could not load: ${e.message}`,'bad')}
    finally{loading=false}
  }

  async function save(e){
    if(saving)return;
    if(e?.target?.classList.contains('fsProfanitySource'))state.profanity_source_preference=e.target.value;
    if(e?.target?.classList.contains('fsDialogueSource'))state.dialogue_source_preference=e.target.value;
    if(e?.target?.classList.contains('fsDialogueFallback'))state.dialogue_source_fallback=e.target.value;
    if(e?.target?.classList.contains('fsDialogueMethod'))state.method=e.target.value;
    if(e?.target?.classList.contains('fsDialogueAiModel'))state.ai_model=e.target.value;
    if(e?.target?.classList.contains('fsDialogueAiFallback'))state.ai_fallback_classic=e.target.value==='true';
    if(e?.target?.classList.contains('fsDialogueAiCpuFallback'))state.ai_worker_cpu_fallback=e.target.value==='true';
    sync();saving=true;status('Saving…');
    try{
      const result=await request('/api/dialogue-enhancement/settings',{method:'POST',body:JSON.stringify(state)});
      status(result.message||'Saved.','good');
    }catch(err){status(`Save failed: ${err.message}`,'bad');await load()}
    finally{saving=false}
  }

  function boot(){styles();ensure();load();setTimeout(()=>{ensure();organizeGeneral()},900);setTimeout(organizeGeneral,1800)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,650));else setTimeout(boot,650);
})();
