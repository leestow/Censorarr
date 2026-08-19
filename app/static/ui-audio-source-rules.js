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
      @media(max-width:900px){.fs-source-rules-grid,.fs-ai-dialogue-grid{grid-template-columns:1fr}}
    `;document.head.appendChild(s);
  }

  function sourcePanel(key){
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

  function aiPanel(key){
    const box=document.createElement('div');box.className='section fs-ai-dialogue-rules';box.dataset.aiDialogueRules=key;
    box.innerHTML=`<div class="fs-ai-dialogue-head"><div><h3>Dialogue Enhancement Engine</h3><p>AI mode isolates human dialogue, raises it, and automatically ducks competing music/effects only while speech is active.</p></div><span class="fs-ai-worker">Checking GPU worker…</span></div>
      <div class="fs-ai-dialogue-grid">
        <div class="fs-ai-rule"><label>Method</label><select class="fsDialogueMethod">
          <option value="ai">AI Dialogue Isolation — Recommended</option>
          <option value="classic">Classic Center / EQ / Compression</option>
        </select><small>AI is much more selective because the isolated speech stem controls the mix instead of assuming all center-channel sound is dialogue.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>AI separation model</label><select class="fsDialogueAiModel">
          <option value="mdx_q">MDX-Q — lower memory / recommended</option>
          <option value="htdemucs">HTDemucs — heavier</option>
        </select><small>MDX-Q is the recommended first choice for smaller GPUs. The GPU worker unloads Whisper before separation to free VRAM.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>If AI cannot complete</label><select class="fsDialogueAiFallback">
          <option value="true">Fall back to Classic</option>
          <option value="false">Fail the item instead</option>
        </select><small>Classic fallback keeps automation moving if the AI worker is unavailable or separation fails.</small></div>
      </div>
      <div class="fs-ai-dialogue-grid" style="margin-top:10px">
        <div class="fs-ai-rule" data-ai-only><label>If GPU separation fails</label><select class="fsDialogueAiCpuFallback">
          <option value="true">Retry AI on worker CPU</option>
          <option value="false">Do not retry on CPU</option>
        </select><small>CPU fallback is much slower, but can finish a movie if the GPU runs out of memory.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>Dialogue-aware ducking</label><div style="font-weight:800;padding:8px 0">Always ON in AI mode</div><small>Light ≈ 2 dB background duck, Medium ≈ 4 dB, Strong ≈ 6 dB. Smooth attack/release prevents obvious pumping.</small></div>
        <div class="fs-ai-rule" data-ai-only><label>Strength controls</label><div style="font-weight:800;padding:8px 0">Speech lift + background ducking</div><small>Use the existing Enhancement Strength setting below. Stronger levels both emphasize isolated speech more and reduce competing sound more aggressively while speech is present.</small></div>
      </div><div class="fs-ai-preview"></div>`;
    qa('select',box).forEach(x=>x.addEventListener('change',save));return box;
  }

  function rewriteLegacyCopy(){
    const callout=q('#dialogueEnhancementSection .setting-callout');
    if(callout)callout.textContent='Creates an additional speech-focused stereo track while preserving CLEAN and original audio. AI mode isolates human dialogue on the GPU worker, dynamically ducks competing music/effects while speech is active, then mixes the enhanced dialogue back in. Classic mode remains available as a fast lightweight alternative.';
    const note=q('#dialogueEnhancementSection .footer-note');
    if(note)note.textContent='Medium is the recommended starting point. In AI mode, strength changes both speech emphasis and dialogue-triggered background ducking.';
  }

  function ensure(){
    for(const [section,key] of [['general','general'],['detection','detection']]){
      const page=q(`.settings-page[data-settings="${section}"]`);if(!page)continue;
      let source=q(`[data-source-rules="${key}"]`,page);
      if(!source){
        source=sourcePanel(key);const feature=q('[data-feature-panel]',page);
        if(feature)feature.insertAdjacentElement('afterend',source);else page.insertBefore(source,page.firstElementChild||null);
      }
      if(!q(`[data-ai-dialogue-rules="${key}"]`,page))source.insertAdjacentElement('afterend',aiPanel(key));
    }
    rewriteLegacyCopy();sync();
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
    qa('.fs-ai-preview').forEach(x=>x.textContent=text);
    qa('[data-ai-only]').forEach(x=>x.classList.toggle('disabled',state.method!=='ai'));
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
      };sync();status('Saved automation defaults loaded.');await checkAI();
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

  function boot(){styles();ensure();load();setTimeout(()=>{ensure();load()},900)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,650));else setTimeout(boot,650);
})();
