(() => {
  const q=(s,r=document)=>r.querySelector(s), qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const $=id=>document.getElementById(id);
  let wizardDirty=false;

  const HELP={
    sExtensions:'Video file types Censorarr should watch. Most users can leave the defaults alone.',
    sScan:'How often Censorarr checks your media folders for something new or changed.',
    sStable:'How long a file must stop changing before Censorarr considers it safe to process. This avoids touching downloads that are still being copied.',
    sProcessExisting:'Choose Yes if you want Censorarr to work through media that is already in your library. Choose New/changed only if you only want future additions handled automatically.',
    sMarkerEnabled:'Recommended. Censorarr remembers which files have already been completed so unchanged media is not processed over and over.',
    sMarkerFilename:'Internal marker file used to remember completion. Most users should leave this unchanged.',
    sSchedEnabled:'Limits automatic processing to a time window. Manual Process/Reprocess is still available outside the schedule.',
    sSchedStart:'The earliest time automatic processing is allowed to begin.',
    sSchedEnd:'The time automatic processing should stop starting new jobs.',
    wMoviesRoot:'The folder path Censorarr sees inside its container. This is usually /media, not the folder path shown by your NAS or Windows host.',
    wTvRoot:'The folder path Censorarr sees inside its container. This is usually /tv.',
    wProcessExisting:'Yes means Censorarr can work through media already in your library. New/changed only leaves the old library alone until something changes.',
    wAsrBackend:'Where speech transcription runs. A GPU worker is much faster; local CPU works without another machine.',
    wAsrUrl:'The address of your Censorarr GPU worker, including http:// and port 9000 unless you changed the worker port.',
    wAsrToken:'Optional shared secret used to protect the GPU worker. Leave this blank if you are keeping an already-saved token.',
    wPlexUrl:'The local address of your Plex Media Server, usually http://SERVER_IP:32400.',
    wPlexToken:'A Plex authentication token lets Censorarr read ratings, activity, and refresh changed media. It is stored as a secret.',
    wPlexMoviesFrom:'The movie path Plex reports for the file. Censorarr maps this to its own /media path.',
    wPlexTvFrom:'The TV path Plex reports for the file. Censorarr maps this to its own /tv path.',
    wMovieRatingEnabled:'When enabled, Censorarr can automatically limit movie processing by Plex content rating.',
    wTvRatingEnabled:'When enabled, Censorarr can automatically limit TV processing by Plex content rating.',
    wPlexPause:'Prevents Censorarr from starting a new heavy job while Plex is actively streaming video.',
    wPlexRefresh:'Recommended. Tells Plex to notice newly-created or replaced audio tracks after processing.',
    wRadUrl:'The address you use to reach Radarr from the Censorarr container, usually http://SERVER_IP:7878.',
    wRadKey:'Radarr API key. It lets Censorarr read movie metadata; it does not need your Radarr username/password.',
    wRadFrom:'The movie path Radarr reports. Censorarr maps this path to /media.',
    wSonUrl:'The address you use to reach Sonarr from the Censorarr container, usually http://SERVER_IP:8989.',
    wSonKey:'Sonarr API key. It lets Censorarr read show and episode metadata; it does not need your Sonarr username/password.',
    wSonFrom:'The TV path Sonarr reports. Censorarr maps this path to /tv.',
    wBazUrl:'The address you use to reach Bazarr from Censorarr, usually http://SERVER_IP:6767.',
    wBazKey:'Bazarr API key. It lets Censorarr request missing subtitles when subtitle assistance needs them.',
    wBazMoviesFrom:'The movie path Bazarr/Radarr reports. Censorarr maps it to /media.',
    wBazTvFrom:'The TV path Bazarr/Sonarr reports. Censorarr maps it to /tv.'
  };

  function addStyles(){
    if($('#fsGuidedSetupStyles'))return;
    const s=document.createElement('style');s.id='fsGuidedSetupStyles';s.textContent=`
      .fs-help-bubble{position:relative;display:inline-flex!important;align-items:center;justify-content:center;width:17px;height:17px;min-width:17px;padding:0!important;margin-left:4px;border-radius:50%!important;border:1px solid color-mix(in srgb,var(--accent2) 55%,var(--line))!important;background:color-mix(in srgb,var(--accent2) 8%,var(--panel))!important;color:var(--accent2)!important;font-size:10px!important;font-weight:900!important;line-height:1!important;cursor:help!important;vertical-align:middle}
      .fs-help-bubble .fs-help-tip{position:absolute;left:50%;bottom:calc(100% + 9px);transform:translateX(-50%) translateY(4px);width:300px;max-width:min(300px,80vw);padding:9px 11px;border-radius:7px;background:#111a24;color:#f5f8fb;border:1px solid #34475a;box-shadow:0 9px 26px rgba(0,0,0,.3);font-size:11px;font-weight:500;line-height:1.45;white-space:normal;opacity:0;visibility:hidden;pointer-events:none;transition:.13s;z-index:300}
      .fs-help-bubble:hover .fs-help-tip,.fs-help-bubble:focus .fs-help-tip{opacity:1;visibility:visible;transform:translateX(-50%) translateY(0)}
      .fs-wizard-interview{display:grid;gap:14px}.fs-question{border:1px solid var(--line);border-radius:9px;padding:14px;background:var(--panel2)}
      .fs-question-title{font-weight:850;font-size:14px;margin-bottom:3px}.fs-question-help{color:var(--muted);font-size:11px;line-height:1.45;margin-bottom:10px}
      .fs-answer-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}.fs-answer{display:flex!important;align-items:flex-start!important;gap:8px!important;border:1px solid var(--line);border-radius:7px;padding:10px 11px;background:var(--panel);cursor:pointer;font-size:12px;line-height:1.35}
      .fs-answer input{min-width:auto!important;margin-top:2px}.fs-answer:has(input:checked){border-color:color-mix(in srgb,var(--accent2) 65%,var(--line));background:color-mix(in srgb,var(--accent2) 8%,var(--panel))}
      .fs-config-preview{padding:11px 13px;border-left:3px solid var(--accent);background:color-mix(in srgb,var(--accent) 7%,var(--panel2));border-radius:6px;font-size:11px;line-height:1.5}
      .fs-key-guide{margin-top:8px;border:1px solid var(--line);border-radius:8px;background:var(--panel2);overflow:hidden}.fs-key-guide summary{cursor:pointer;padding:9px 11px;font-size:11px;font-weight:800;color:var(--accent2)}
      .fs-key-guide-body{padding:0 12px 12px}.fs-key-guide ol{margin:4px 0 10px;padding-left:19px;font-size:11px;line-height:1.55}.fs-guide-shot{border:1px dashed color-mix(in srgb,var(--accent2) 45%,var(--line));background:color-mix(in srgb,var(--accent2) 5%,var(--panel));border-radius:7px;padding:14px;color:var(--muted);font-size:10px;text-align:center}
      .fs-wizard-autoconfig{font-size:11px;color:var(--muted);margin-top:7px}.fs-wizard-autoconfig b{color:var(--text)}
      .wizard-step[data-wstep="1"] #wDry,.wizard-step[data-wstep="1"] #wDry+*{display:none!important}
      @media(max-width:650px){.fs-answer-grid{grid-template-columns:1fr}.fs-help-bubble .fs-help-tip{left:auto;right:-8px;transform:translateY(4px)}.fs-help-bubble:hover .fs-help-tip,.fs-help-bubble:focus .fs-help-tip{transform:translateY(0)}}
    `;document.head.appendChild(s);
  }

  function helpBubble(text){
    const b=document.createElement('button');b.type='button';b.className='fs-help-bubble';b.setAttribute('aria-label','More information');b.innerHTML=`?<span class="fs-help-tip"></span>`;q('.fs-help-tip',b).textContent=text;return b;
  }

  function enhanceHelp(root=document){
    for(const [id,text] of Object.entries(HELP)){
      const el=$(id);if(!el||!root.contains(el)&&root!==document)continue;
      const label=el.closest('.field')?.querySelector(':scope > label');if(!label||q('.fs-help-bubble,.help-icon',label))continue;
      label.appendChild(helpBubble(text));
    }
    qa('.settings-page .field',root).forEach(field=>{
      const label=q(':scope > label',field);if(!label||q('.fs-help-bubble,.help-icon',label))return;
      const note=q('.fs-general-help,.footer-note,small',field);const text=note?.textContent?.trim();
      if(text&&text.length>18)label.appendChild(helpBubble(text));
    });
  }

  function answer(name,value,label,detail=''){
    return `<label class="fs-answer"><input type="radio" name="${name}" value="${value}"><span><b>${label}</b>${detail?`<br><span class="muted">${detail}</span>`:''}</span></label>`;
  }

  function selected(name,fallback=''){return q(`input[name="${name}"]:checked`)?.value||fallback}
  function setRadio(name,value){const x=q(`input[name="${name}"][value="${value}"]`);if(x)x.checked=true}
  function setValue(id,value){const el=$(id);if(el&&value!==undefined&&value!==null)el.value=String(value)}

  function buildInterview(){
    const step=q('.wizard-step[data-wstep="0"]');if(!step||step.dataset.fsGuided==='1')return;
    step.dataset.fsGuided='1';
    step.innerHTML=`<h2>Tell us how you use your media server</h2><div class="wizard-lead">Answer a few plain-English questions. Censorarr will choose sensible defaults for you, then only ask for connection details it cannot discover on its own.</div>
      <div class="fs-wizard-interview">
        <div class="fs-question"><div class="fs-question-title">What do you want Censorarr to create?</div><div class="fs-question-help">You can change this later. CLEAN mutes configured profanity. Dialogue Enhanced makes speech easier to hear.</div><div class="fs-answer-grid">${answer('fsGoal','both','Both — recommended','Create CLEAN and Dialogue Enhanced tracks.')}${answer('fsGoal','clean','CLEAN only','Profanity censoring without dialogue enhancement.')}${answer('fsGoal','dialogue','Dialogue only','Improve dialogue without creating a CLEAN track.')}</div></div>
        <div class="fs-question"><div class="fs-question-title">What is in this Censorarr installation?</div><div class="fs-answer-grid">${answer('fsLibraries','both','Movies + TV Shows')}${answer('fsLibraries','movies','Movies only')}</div></div>
        <div class="fs-question"><div class="fs-question-title">Which apps do you already use?</div><div class="fs-question-help">Choose Yes only for services you actually have. Censorarr will skip configuration screens you do not need.</div><div class="fs-answer-grid">${answer('fsPlex','yes','I use Plex')}${answer('fsPlex','no','No Plex / standalone')}${answer('fsRadarr','yes','I use Radarr')}${answer('fsRadarr','no','No Radarr')}${answer('fsSonarr','yes','I use Sonarr')}${answer('fsSonarr','no','No Sonarr')}${answer('fsBazarr','yes','I use Bazarr')}${answer('fsBazarr','no','No Bazarr')}</div></div>
        <div class="fs-question"><div class="fs-question-title">Do you already have the Censorarr NVIDIA GPU Worker running?</div><div class="fs-question-help">If not, Censorarr can still transcribe on the local CPU. Dialogue Enhancement will use the lighter Classic method until a GPU worker is added.</div><div class="fs-answer-grid">${answer('fsGpu','yes','Yes — use my GPU worker','Recommended for AI Dialogue Enhancement and faster transcription.')}${answer('fsGpu','no','No — use this server','No separate GPU worker required.')}</div></div>
        <div class="fs-question"><div class="fs-question-title">What should automatic processing include?</div><div class="fs-answer-grid">${answer('fsExisting','yes','Existing library + new media','Work through what I already have and keep up with additions.')}${answer('fsExisting','no','Only new or changed media','Leave the existing library alone unless a file changes.')}</div></div>
        <div class="fs-question" id="fsRatingQuestion"><div class="fs-question-title">If Plex is connected, which ratings should automation target?</div><div class="fs-question-help">The family-focused preset uses the existing PG-13 movie / TV-14 television thresholds. Manual Process/Reprocess is still available for anything else.</div><div class="fs-answer-grid">${answer('fsRatings','family','Family-focused preset — recommended','Automatically target PG-13+ movies and TV-14+ shows.')}${answer('fsRatings','all','All ratings','Do not use Plex ratings to limit automation.')}</div></div>
        <div class="fs-question" id="fsPlexActivityQuestion"><div class="fs-question-title">Should Censorarr avoid starting heavy jobs while Plex is playing video?</div><div class="fs-answer-grid">${answer('fsPausePlex','yes','Yes — recommended','Wait until active Plex playback stops before starting another automatic job.')}${answer('fsPausePlex','no','No','Allow automatic jobs while Plex is streaming.')}</div></div>
        <div class="fs-config-preview" id="fsConfigPreview"></div>
      </div>`;
    qa('input[type="radio"]',step).forEach(x=>x.addEventListener('change',()=>{wizardDirty=true;applyInterview()}));
  }

  function seedInterview(){
    if(wizardDirty)return;
    const prof=q('.fsProfanityToggle')?.checked!==false;
    const dial=!!q('.fsDialogueToggle')?.checked;
    setRadio('fsGoal',prof&&dial?'both':dial?'dialogue':'clean');
    setRadio('fsLibraries',$('wTvEnabled')?.value==='true'?'both':'movies');
    setRadio('fsPlex',$('wPlexEnabled')?.value==='true'?'yes':'no');
    setRadio('fsRadarr',$('wRadEnabled')?.value==='true'?'yes':'no');
    setRadio('fsSonarr',$('wSonEnabled')?.value==='true'?'yes':'no');
    setRadio('fsBazarr',$('wBazEnabled')?.value==='true'?'yes':'no');
    setRadio('fsGpu',$('wAsrBackend')?.value==='local'?'no':'yes');
    setRadio('fsExisting',$('wProcessExisting')?.value==='false'?'no':'yes');
    setRadio('fsRatings',($('wMovieRatingEnabled')?.value==='true'||$('wTvRatingEnabled')?.value==='true')?'family':'all');
    setRadio('fsPausePlex',$('wPlexPause')?.value==='true'?'yes':'no');
    applyInterview();
  }

  function applyInterview(){
    const tv=selected('fsLibraries','both')==='both';
    const plex=selected('fsPlex','no')==='yes';
    const rad=selected('fsRadarr','no')==='yes';
    const son=tv&&selected('fsSonarr','no')==='yes';
    const baz=selected('fsBazarr','no')==='yes';
    const gpu=selected('fsGpu','no')==='yes';
    const family=selected('fsRatings','family')==='family';
    setValue('wTvEnabled',tv);setValue('wPlexEnabled',plex);setValue('wRadEnabled',rad);setValue('wSonEnabled',son);setValue('wBazEnabled',baz);
    setValue('wAsrBackend',gpu?'auto':'local');setValue('wProcessExisting',selected('fsExisting','yes')==='yes');setValue('wSubEnabled',true);
    setValue('wMovieRatingEnabled',plex&&family);setValue('wTvRatingEnabled',plex&&tv&&family);setValue('wPlexPause',plex&&selected('fsPausePlex','yes')==='yes');setValue('wPlexRefresh',plex);
    setValue('wDry',false);
    try{window.wizardToggleSections?.()}catch(_){}
    const rq=$('fsRatingQuestion'),pq=$('fsPlexActivityQuestion');if(rq)rq.classList.toggle('hidden',!plex);if(pq)pq.classList.toggle('hidden',!plex);
    const goal=selected('fsGoal','both');const preview=$('fsConfigPreview');if(preview){
      const pieces=[goal==='both'?'CLEAN + Dialogue Enhanced':goal==='clean'?'CLEAN only':'Dialogue Enhanced only',tv?'Movies + TV':'Movies',gpu?'GPU worker with CPU fallback':'Local CPU',plex?'Plex connected':'Standalone'];
      if(rad)pieces.push('Radarr');if(son)pieces.push('Sonarr');if(baz)pieces.push('Bazarr');
      preview.innerHTML=`<b>Censorarr will configure:</b> ${pieces.join(' · ')}${plex&&family?'<br>Automation will use the family-focused PG-13 / TV-14 rating thresholds.':''}${!gpu&&goal!=='clean'?'<br>Without a GPU worker, Dialogue Enhancement will start with the lighter Classic method.':''}`;
    }
  }

  function guide(id,title,steps,slot){
    const input=$(id),field=input?.closest('.field');if(!field||q('.fs-key-guide',field))return;
    const d=document.createElement('details');d.className='fs-key-guide';d.innerHTML=`<summary>Show me exactly where to get this</summary><div class="fs-key-guide-body"><b>${title}</b><ol>${steps.map(x=>`<li>${x}</li>`).join('')}</ol><div class="fs-guide-shot" data-guide-shot="${slot}">Screenshot guide will appear here. The written steps work now.</div></div>`;field.appendChild(d);
  }

  function installGuides(){
    guide('wPlexToken','Find your Plex token',["Open Plex Web and sign in to the account that owns or can access this server.","Open any movie or episode and choose Get Info.","Choose View XML.","Look at the browser address bar and copy only the value after X-Plex-Token=. Paste that value into Censorarr."],'plex-token');
    guide('wRadKey','Find your Radarr API key',["Open Radarr.","Go to Settings → General.","Find the Security section.","Copy the API Key and paste it into Censorarr."],'radarr-api');
    guide('wSonKey','Find your Sonarr API key',["Open Sonarr.","Go to Settings → General.","Find the Security section.","Copy the API Key and paste it into Censorarr."],'sonarr-api');
    guide('wBazKey','Find your Bazarr API key',["Open Bazarr.","Go to Settings → General.","Find the Security section.","Copy the API Key and paste it into Censorarr."],'bazarr-api');
  }

  function hideRetiredWizardMode(){
    const dry=$('wDry');if(!dry)return;dry.value='false';const field=dry.closest('.field');if(field)field.style.display='none';
    qa('.wizard-note,.wizard-lead').forEach(el=>{if(/dry\s*run/i.test(el.textContent||''))el.remove()});
  }

  function relevantSteps(){
    const plex=selected('fsPlex',$('wPlexEnabled')?.value==='true'?'yes':'no')==='yes';
    const rad=selected('fsRadarr',$('wRadEnabled')?.value==='true'?'yes':'no')==='yes';
    const son=selected('fsLibraries',$('wTvEnabled')?.value==='true'?'both':'movies')==='both'&&selected('fsSonarr',$('wSonEnabled')?.value==='true'?'yes':'no')==='yes';
    const baz=selected('fsBazarr',$('wBazEnabled')?.value==='true'?'yes':'no')==='yes';
    const out=[0,1,2];if(plex)out.push(3);if(rad||son)out.push(4);if(baz)out.push(5);out.push(6);return out;
  }

  function overrideWizardNavigation(){
    if(window.__fsGuidedWizardNav)return;window.__fsGuidedWizardNav=true;
    const oldRender=window.wizardRender,oldFinish=window.finishSetupWizard,oldOpen=window.openSetupWizard;
    if(typeof oldRender==='function')window.wizardRender=function(){applyInterview();oldRender();const steps=relevantSteps(),idx=Math.max(0,steps.indexOf(window.WIZARD_STEP??0));const label=$('wizardStepLabel');if(label)label.textContent=`Step ${idx+1} of ${steps.length}`;const p=$('wizardProgress');if(p)p.innerHTML=steps.map((_,i)=>`<span class="${i<idx?'done':i===idx?'active':''}"></span>`).join('');};
    window.wizardNext=function(){applyInterview();const steps=relevantSteps(),cur=Number(window.WIZARD_STEP??0),idx=steps.indexOf(cur),next=steps[Math.min(steps.length-1,Math.max(0,idx)+1)];window.WIZARD_STEP=next;window.wizardRender?.()};
    window.wizardBack=function(){const steps=relevantSteps(),cur=Number(window.WIZARD_STEP??0),idx=steps.indexOf(cur),prev=steps[Math.max(0,(idx<0?1:idx)-1)];window.WIZARD_STEP=prev;window.wizardRender?.()};
    if(typeof oldOpen==='function')window.openSetupWizard=async function(firstRun=false){wizardDirty=false;await oldOpen(firstRun);setTimeout(()=>{buildInterview();seedInterview();installGuides();hideRetiredWizardMode();enhanceHelp();window.wizardRender?.()},0)};
    if(typeof oldFinish==='function')window.finishSetupWizard=async function(){
      applyInterview();const goal=selected('fsGoal','both'),gpu=selected('fsGpu','no')==='yes';
      try{
        await fetch('/api/dialogue-enhancement/settings',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({
          enabled:goal!=='clean',profanity_censoring_enabled:goal!=='dialogue',profanity_source_preference:'best_original',dialogue_source_preference:'auto_clean',dialogue_source_fallback:'original',method:gpu?'ai':'classic',ai_model:'mdx_q',ai_fallback_classic:true,ai_worker_cpu_fallback:true
        })});
      }catch(e){console.warn('Could not save wizard audio recommendations',e)}
      return oldFinish();
    };
    const oldSummary=window.wizardBuildSummary;window.wizardBuildSummary=function(){
      if(typeof oldSummary==='function')oldSummary();const box=$('wizardSummary');if(!box)return;const goal=selected('fsGoal','both'),gpu=selected('fsGpu','no')==='yes';
      const cards=[['Audio features',goal==='both'?'CLEAN + Dialogue Enhanced':goal==='clean'?'CLEAN only':'Dialogue Enhanced only'],['Libraries',selected('fsLibraries','both')==='both'?'Movies + TV Shows':'Movies only'],['Processing hardware',gpu?'GPU worker + CPU fallback':'Local CPU'],['Plex',selected('fsPlex','no')==='yes'?'Connected':'Standalone'],['Library managers',`${selected('fsRadarr','no')==='yes'?'Radarr on':'Radarr off'} · ${selected('fsSonarr','no')==='yes'?'Sonarr on':'Sonarr off'}`],['Subtitle help',selected('fsBazarr','no')==='yes'?'Bazarr + available subtitles':'Available subtitles when present']];
      box.innerHTML=cards.map(x=>`<div><b>${x[0]}</b>${x[1]}</div>`).join('');
    };
  }

  function watchWizard(){
    const modal=$('setupModal');if(!modal)return;
    new MutationObserver(()=>{if(modal.classList.contains('open'))setTimeout(()=>{buildInterview();seedInterview();installGuides();hideRetiredWizardMode();enhanceHelp()},0)}).observe(modal,{attributes:true,attributeFilter:['class']});
  }

  function boot(){addStyles();buildInterview();installGuides();hideRetiredWizardMode();enhanceHelp();overrideWizardNavigation();watchWizard();
    new MutationObserver(muts=>{for(const m of muts)for(const n of m.addedNodes)if(n instanceof Element)enhanceHelp(n)}).observe(document.body,{childList:true,subtree:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,900),{once:true});else setTimeout(boot,900);
})();
