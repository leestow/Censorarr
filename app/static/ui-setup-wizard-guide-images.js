(() => {
  if (window.__censorarrWizardGuideImages) return;
  window.__censorarrWizardGuideImages = true;

  const q=(s,r=document)=>r.querySelector(s), qa=(s,r=document)=>[...r.querySelectorAll(s)], $=id=>document.getElementById(id);
  const GUIDES={
    plex:{src:'/assets/guide-plex.svg',caption:'Plex: open the item menu → Get Info → View XML → copy only the X-Plex-Token value from the browser URL. Example token is fake.'},
    radarr:{src:'/assets/guide-radarr.svg',caption:'Radarr Settings → General → Security. The API key shown in this guide is a fake example.'},
    sonarr:{src:'/assets/guide-sonarr.svg',caption:'Sonarr Settings → General → Security. The API key shown in this guide is a fake example.'},
    bazarr:{src:'/assets/guide-bazarr.svg',caption:'Bazarr Settings → General. The API key shown in this guide is a fake example.'},
  };

  const HELP={
    sExtensions:'The video file types Censorarr watches. Most users should leave the defaults unchanged.',
    sScan:'How often automatic processing checks your media folders for new or changed files.',
    sStable:'How long a file must stop changing before Censorarr considers it safe to process. This prevents Censorarr from touching a download while it is still being copied.',
    sProcessExisting:'Yes lets Censorarr work through media already in your library. New/changed only leaves existing files alone until they change.',
    sMarkerEnabled:'Recommended. Censorarr remembers completed files so unchanged media is not processed repeatedly.',
    sMarkerFilename:'The small internal marker filename Censorarr uses to remember completed work. Most users never need to change this.',
    sSchedEnabled:'Limits automatic jobs to the schedule below. Manual Process/Reprocess remains available outside the schedule.',
    sSchedStart:'The earliest time Censorarr is allowed to start a new automatic job.',
    sSchedEnd:'The time Censorarr stops starting new automatic jobs. A job already running is allowed to finish.',
    sSeverity:'Only dictionary entries at this severity or higher are muted. A higher number means a stricter threshold.',
    sWordWindow:'The largest multi-word phrase Censorarr will try to match as one profanity entry.',
    sPrecisionEnabled:'Recommended. Uses nearby quiet audio and neighboring words to place mute edges more accurately than raw transcription timestamps.',
    sPrecisionBefore:'Extra silence added immediately before a detected word. Smaller values make the mute tighter.',
    sPrecisionAfter:'Extra silence added immediately after a detected word. Smaller values make the mute tighter.',
    sPrecisionSearch:'How far Censorarr searches around a word for a nearby quiet point where the mute can begin or end naturally.',
    sPrecisionGuard:'Protects nearby non-profane words from being clipped when Censorarr adjusts mute boundaries.',
    sPrecisionEnergy:'How quiet audio must be before Censorarr considers it a good place to start or end a mute.',
    sPrecisionFrame:'Size of each tiny audio slice used when looking for quiet mute boundaries. The default is usually best.',
    sRescue:'Runs a second targeted transcription pass around suspicious areas to catch words the first pass may have missed.',
    sRescueConf:'Low-confidence transcript words below this level can trigger the rescue pass.',
    sRescueFuzzyCeil:'Limits fuzzy rescue matching to uncertain words so confident normal speech is not changed unnecessarily.',
    sRescueFuzzySim:'How similar a rescue result must be to a configured profanity before Censorarr accepts it.',
    sRescueBefore:'How much audio before a suspicious word is included in the rescue clip.',
    sRescueAfter:'How much audio after a suspicious word is included in the rescue clip.',
    sRescueGap:'Nearby rescue areas closer than this are combined into one clip to reduce extra transcription work.',
    sRescueMax:'Safety limit for how many rescue clips Censorarr can create from one media file.',
    sRescueCenter:'For surround audio, prefers the center/dialogue channel during rescue because speech is usually strongest there.',
    sRescueMild:'Optional extra words that can trigger a rescue pass even if they are not strong enough to mute by themselves.',
    sRescuePrompt:'Optional text that helps Whisper recognize the kinds of words Censorarr is looking for during rescue.',
    sTitle:'The name shown by Plex and other players for the Censorarr-created CLEAN audio track.',
    sCleanLang:'Language tag written into the CLEAN track. Use eng for English unless you have a specific reason to change it.',
    sCleanCodec:'Audio format used for the CLEAN track. Auto keeps a compatible choice based on the source.',
    sCleanFirst:'Recommended for Plex. Places the CLEAN track before the original audio so players are more likely to select it.',
    sDefault:'Marks the CLEAN track as the default audio stream in the media file.',
    sReplaceClean:'When processing again, replaces Censorarr’s existing CLEAN track instead of adding another duplicate.',
    sReprocessClean:'Normally off. When enabled, automatic scans can rebuild files that already have a CLEAN track.',
    wMoviesRoot:'The Movies path Censorarr sees inside its container. In the standard Docker/Synology setup this is /media.',
    wTvRoot:'The TV Shows path Censorarr sees inside its container. In the standard Docker/Synology setup this is /tv.',
    wAsrBackend:'Where speech transcription runs. A GPU worker is much faster; local CPU works without another machine.',
    wAsrUrl:'The network address of the Censorarr GPU Worker, normally http://WORKER_IP:9000.',
    wAsrToken:'The shared secret used to protect the GPU Worker. Leave it blank when you want to keep an already-saved token.',
    wPlexUrl:'The local network address of Plex Media Server, normally http://SERVER_IP:32400.',
    wPlexToken:'Lets Censorarr read Plex ratings/activity and refresh changed media. It is stored as a secret.',
    wRadUrl:'The address Censorarr uses to reach Radarr, normally http://SERVER_IP:7878.',
    wRadKey:'Lets Censorarr read Radarr movie metadata. Censorarr does not need your Radarr username or password.',
    wSonUrl:'The address Censorarr uses to reach Sonarr, normally http://SERVER_IP:8989.',
    wSonKey:'Lets Censorarr read Sonarr series/episode metadata. Censorarr does not need your Sonarr username or password.',
    wBazUrl:'The address Censorarr uses to reach Bazarr, normally http://SERVER_IP:6767.',
    wBazKey:'Lets Censorarr request missing subtitles when subtitle assistance needs them.',
  };

  function addStyles(){
    if($('#fsSettingHelpStyles'))return;
    const style=document.createElement('style');style.id='fsSettingHelpStyles';style.textContent=`
      .fs-setting-help{position:relative;display:inline-grid!important;place-items:center;width:16px;height:16px;min-width:16px;padding:0!important;margin-left:4px;border-radius:50%!important;border:1px solid #2998ef!important;background:transparent!important;color:#168df1!important;font-size:10px!important;font-weight:900!important;line-height:1!important;cursor:help!important;vertical-align:middle}
      .fs-setting-help-tip{position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%) translateY(3px);width:300px;max-width:min(300px,80vw);padding:9px 10px;border-radius:6px;background:#101922;color:#f2f8fb;border:1px solid #354b5a;box-shadow:0 9px 24px rgba(0,0,0,.30);font-size:11px;font-weight:500;line-height:1.45;white-space:normal;opacity:0;visibility:hidden;pointer-events:none;transition:.12s;z-index:500}
      .fs-setting-help:hover .fs-setting-help-tip,.fs-setting-help:focus .fs-setting-help-tip{opacity:1;visibility:visible;transform:translateX(-50%) translateY(0)}
      @media(max-width:650px){.fs-setting-help-tip{left:auto;right:-8px;transform:translateY(3px)}.fs-setting-help:hover .fs-setting-help-tip,.fs-setting-help:focus .fs-setting-help-tip{transform:translateY(0)}}
    `;document.head.appendChild(style);
  }

  function kindFor(details){
    const text=(q('summary',details)?.textContent||'').toLowerCase();
    if(text.includes('plex'))return 'plex';
    if(text.includes('radarr'))return 'radarr';
    if(text.includes('sonarr'))return 'sonarr';
    if(text.includes('bazarr'))return 'bazarr';
    return '';
  }

  function enrichGuides(root=document){
    qa('.fsw-guide',root).forEach(details=>{
      if(details.dataset.guideImage==='1')return;
      const kind=kindFor(details),guide=GUIDES[kind];if(!guide)return;
      details.dataset.guideImage='1';
      const wrap=document.createElement('div');wrap.className='fsw-shot-grid';
      wrap.innerHTML=`<div class="fsw-shot"><img src="${guide.src}" alt="${kind} setup guide"><small>${guide.caption}</small></div>`;
      details.appendChild(wrap);
    });
  }

  function inferHelp(label){
    const t=String(label||'').toLowerCase();
    if(/api key/.test(t))return 'A secret key that lets Censorarr talk to this service without using your username and password.';
    if(/token/.test(t))return 'A secret value used to authenticate Censorarr to this service. Censorarr stores saved secrets securely and does not send them back to the browser.';
    if(/server url|worker url|\burl\b/.test(t))return 'The network address Censorarr uses to reach this service. Include http:// or https:// and the port when the service uses one.';
    if(/path|folder|root/.test(t))return 'The path must be the location Censorarr can actually see. In Docker, this is usually the container-side path, not the host/NAS path.';
    if(/codec/.test(t))return 'The audio format used for the generated track. Leave the recommended/default choice unless you need compatibility with a specific player.';
    if(/bitrate/.test(t))return 'Controls the audio quality/file-size tradeoff for the generated track. The recommended value is usually the best starting point.';
    if(/language/.test(t))return 'The language metadata written into or expected from this track/source. eng means English.';
    if(/default/.test(t))return 'Controls whether players should prefer this generated audio track automatically.';
    if(/replace/.test(t))return 'When enabled, Censorarr updates its existing generated track instead of creating a duplicate.';
    if(/fallback/.test(t))return 'What Censorarr should do when the preferred method or source is unavailable, so automatic processing can continue safely.';
    if(/model/.test(t))return 'The AI/transcription model used for this task. Larger models can be more accurate but need more memory and processing time.';
    if(/timeout/.test(t))return 'How long Censorarr waits before treating an operation as stuck or unavailable.';
    if(/scan|interval/.test(t))return 'Controls how often Censorarr checks for new work. Shorter intervals react faster but perform more frequent checks.';
    if(/severity|threshold|confidence|similarity|score/.test(t))return 'A decision threshold. The nearby description and default are designed to be a safe starting point; change it only when tuning detection behavior.';
    return '';
  }

  function bubble(text){
    const b=document.createElement('button');b.type='button';b.className='fs-setting-help';b.setAttribute('aria-label','Explain this setting');
    const tip=document.createElement('span');tip.className='fs-setting-help-tip';tip.textContent=text;b.appendChild(tip);return b;
  }

  function enrichSettings(root=document){
    addStyles();
    for(const [id,text] of Object.entries(HELP)){
      const control=$(id);if(!control)continue;
      const field=control.closest('.field');const label=field?.querySelector(':scope > label');
      if(!label||label.querySelector('.fs-setting-help,.help-icon,.fsw-help'))continue;
      label.appendChild(bubble(text));
    }
    qa('.settings-page .field',root).forEach(field=>{
      const label=q(':scope > label',field);if(!label||label.querySelector('.fs-setting-help,.help-icon,.fsw-help'))return;
      const text=inferHelp(label.textContent);if(text)label.appendChild(bubble(text));
    });
  }

  function syncFirstRunClose(){
    const legacy=$('wizardCloseBtn'),modern=$('fsWizardClose');if(!legacy||!modern)return;
    modern.style.visibility=legacy.classList.contains('hidden')?'hidden':'visible';
  }

  function guardFinish(){
    const button=$('fsWizardFinish');if(!button||button.dataset.finishGuard==='1')return;
    button.dataset.finishGuard='1';
    button.addEventListener('click',()=>{
      const started=Date.now();
      const timer=setInterval(()=>{
        const legacy=String($('wFinishStatus')?.textContent||'').trim();
        const notice=$('fsWizardNotice');
        if(/^Could not finish setup:/i.test(legacy)){
          if(notice){notice.textContent=legacy;notice.classList.add('bad')}
          button.disabled=false;clearInterval(timer);return;
        }
        if(/setup complete/i.test(legacy)){
          if(notice){notice.textContent=legacy;notice.classList.remove('bad')}
          clearInterval(timer);return;
        }
        if(Date.now()-started>60000)clearInterval(timer);
      },200);
    });
  }

  function boot(){
    addStyles();enrichGuides();enrichSettings();syncFirstRunClose();guardFinish();
    const legacyClose=$('wizardCloseBtn');if(legacyClose)new MutationObserver(syncFirstRunClose).observe(legacyClose,{attributes:true,attributeFilter:['class']});
    new MutationObserver(muts=>{
      let settings=false,guides=false,wizard=false;
      for(const m of muts)for(const node of m.addedNodes)if(node instanceof Element){
        if(node.matches?.('.fsw-guide')||node.querySelector?.('.fsw-guide'))guides=true;
        if(node.matches?.('.settings-page,.field')||node.querySelector?.('.settings-page,.field'))settings=true;
        if(node.id==='fsWizardFinish'||node.querySelector?.('#fsWizardFinish'))wizard=true;
      }
      if(guides)enrichGuides();if(settings)enrichSettings();if(wizard)guardFinish();syncFirstRunClose();
    }).observe(document.body,{childList:true,subtree:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();