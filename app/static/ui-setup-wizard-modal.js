(() => {
  if (window.__censorarrWizardV2) return;
  window.__censorarrWizardV2 = true;

  const q=(s,r=document)=>r.querySelector(s), qa=(s,r=document)=>[...r.querySelectorAll(s)], $=id=>document.getElementById(id);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const GUIDES={};
  let step=0, firstRun=false, answers={
    goal:'both', libraries:'both', plex:'yes', radarr:'yes', sonarr:'yes', bazarr:'no',
    gpu:'yes', gpuLocation:'separate', gpuPlatform:'linux', existing:'yes', ratings:'family', pausePlex:'yes'
  };

  const STEPS=[
    ['Welcome','Getting started'],
    ['Usage','Tell us how you’ll use Censorarr'],
    ['Media Services','Connect the apps you use'],
    ['Paths','Tell us where your media is'],
    ['GPU Worker','Configure processing power'],
    ['Processing Rules','Choose automatic behavior'],
    ['Finish','Review and apply']
  ];

  function setLegacy(id,v){const el=$(id);if(el&&v!==undefined&&v!==null)el.value=String(v)}
  function getLegacy(id,f=''){const el=$(id);return el?String(el.value??f):f}
  function notify(msg,bad=false){const box=$('fsWizardNotice');if(!box)return;box.textContent=msg||'';box.classList.toggle('bad',!!bad)}

  function addStyles(){
    if($('#fsWizardV2Styles'))return;
    const s=document.createElement('style');s.id='fsWizardV2Styles';s.textContent=`
      #setupModal{background:rgba(2,10,18,.76)!important;backdrop-filter:blur(3px);padding:18px!important}
      #setupModal>.dialog.setup-dialog{width:min(1540px,calc(100vw - 34px))!important;max-width:1540px!important;height:min(900px,calc(100vh - 36px));max-height:calc(100vh - 36px)!important;padding:0!important;overflow:hidden!important;border-radius:10px!important;background:#071724!important;border:1px solid #1c3d50!important;color:#eaf7fb!important;box-shadow:0 28px 90px rgba(0,0,0,.55)!important}
      .fs-wizard-legacy{display:none!important}
      .fsw-shell{height:100%;display:grid;grid-template-rows:auto minmax(0,1fr) auto;background:linear-gradient(180deg,#081a27,#07141f)}
      .fsw-top{height:62px;display:flex;align-items:center;gap:16px;padding:0 18px;border-bottom:1px solid #164658;background:linear-gradient(90deg,#073f50,#075f57)}
      .fsw-logo{width:190px;height:42px;object-fit:contain;object-position:left center}.fsw-top h2{margin:0;font-size:20px;color:#fff}.fsw-step-pill{font-size:11px;padding:4px 8px;border:1px solid #2a6070;border-radius:5px;color:#b8ced8;background:#0d2b38}
      .fsw-close{margin-left:auto!important;width:34px;height:34px;padding:0!important;border:1px solid rgba(255,255,255,.18)!important;background:rgba(0,0,0,.16)!important;color:#d9eff5!important}
      .fsw-main{min-height:0;display:grid;grid-template-columns:200px minmax(0,1fr) 315px}
      .fsw-steps{padding:18px 12px;background:#072131;border-right:1px solid #163c4d;overflow:auto}
      .fsw-step{display:grid;grid-template-columns:27px minmax(0,1fr);gap:8px;align-items:start;padding:10px 8px;border-radius:7px;color:#8eabb8;margin-bottom:4px}
      .fsw-step.active{background:#0b4c61;color:#f6ffff}.fsw-step.done{color:#b6d6df}.fsw-num{width:23px;height:23px;border-radius:50%;display:grid;place-items:center;background:#60788a;color:#071724;font-size:11px;font-weight:900}.fsw-step.active .fsw-num{background:#22d0d0;box-shadow:0 0 0 4px rgba(34,208,208,.12)}.fsw-step.done .fsw-num{background:#25b977;color:white}
      .fsw-step b{display:block;font-size:12px;margin:2px 0}.fsw-step small{display:block;font-size:10px;color:inherit;opacity:.75;line-height:1.35}
      .fsw-content{padding:20px 22px;overflow:auto;background:#071925}.fsw-content h2{margin:0 0 5px;font-size:23px;color:#f6fbfd}.fsw-lead{color:#98b1bd;font-size:12px;margin-bottom:16px;max-width:850px}
      .fsw-right{padding:18px 16px;background:#081d2b;border-left:1px solid #163c4d;overflow:auto}.fsw-side-card{border:1px solid #204657;border-radius:7px;padding:14px;background:#0a2433;margin-bottom:14px}.fsw-side-card h3{margin:0 0 10px;font-size:15px;color:#f3fbfd}.fsw-summary-row{display:flex;gap:8px;padding:7px 0;color:#bed2db;font-size:11px;line-height:1.4}.fsw-check{width:17px;height:17px;border-radius:50%;display:grid;place-items:center;background:#22aa68;color:#fff;font-size:10px;flex:0 0 auto}
      .fsw-q{display:grid;grid-template-columns:minmax(230px,1fr) minmax(200px,300px);gap:12px;align-items:center;border:1px solid #173d4e;background:#09202e;padding:9px 11px;border-radius:6px;margin-bottom:7px}.fsw-q-text{display:flex;align-items:center;gap:8px;font-size:12px;color:#dcecf1}.fsw-q-num{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;border:1px solid #274d5e;color:#8fb0bd;font-size:10px;flex:0 0 auto}
      .fsw-help{position:relative;width:16px;height:16px;min-width:16px;border-radius:50%;display:inline-grid;place-items:center;background:#1668be;color:#fff;font-size:10px;font-weight:900;cursor:help}.fsw-help span{position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);width:290px;padding:9px 10px;border-radius:6px;background:#0b1117;border:1px solid #3b5666;color:#eef7fa;font-size:11px;line-height:1.4;font-weight:500;opacity:0;visibility:hidden;z-index:50;box-shadow:0 8px 24px rgba(0,0,0,.35)}.fsw-help:hover span{opacity:1;visibility:visible}
      .fsw-select,.fsw-input{width:100%!important;min-width:0!important;height:36px!important;border:1px solid #245064!important;background:#0b2635!important;color:#d9f8ee!important;border-radius:5px!important;padding:7px 10px!important}.fsw-segment{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:5px}.fsw-segment button{height:36px;padding:6px!important;border:1px solid #285163!important;background:#0b2635!important;color:#b9d0d8!important}.fsw-segment button.active{border-color:#13bfae!important;background:#0b615e!important;color:#dffff7!important}
      .fsw-section{border:1px solid #1b4152;border-radius:7px;background:#09202e;padding:13px;margin-bottom:12px}.fsw-section h3{margin:0 0 4px;font-size:14px;color:#edf8fb}.fsw-section p{margin:0 0 10px;color:#94afba;font-size:11px}.fsw-grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fsw-field label{display:flex;align-items:center;gap:5px;margin-bottom:5px;color:#a9c0ca;font-size:10px}.fsw-field{min-width:0}
      .fsw-test{margin-top:8px}.fsw-status{font-size:10px;color:#61d8a4;margin-left:8px}.fsw-status.bad{color:#ff8787}
      .fsw-guide{margin-top:9px;border-top:1px solid #1a4151;padding-top:8px}.fsw-guide summary{cursor:pointer;color:#64adff;font-size:11px;font-weight:800}.fsw-guide ol{font-size:11px;color:#b6cbd4;line-height:1.5;padding-left:19px}.fsw-shot-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}.fsw-shot{background:#06131c;border:1px solid #254554;border-radius:6px;padding:5px}.fsw-shot img{width:100%;display:block;border-radius:4px}.fsw-shot small{display:block;padding:5px 4px 2px;color:#9bb4bf;font-size:9px}
      .fsw-code{position:relative;background:#03090e;border:1px solid #233e4b;border-radius:6px;padding:10px 78px 10px 11px;color:#ccecff;font:11px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap;overflow:auto;margin:7px 0}.fsw-copy{position:absolute;right:7px;top:7px;padding:4px 8px!important;font-size:9px!important}
      .fsw-footer{height:64px;border-top:1px solid #164657;display:flex;align-items:center;gap:8px;padding:0 18px;background:#081a27}.fsw-footer .spacer{flex:1}.fsw-back,.fsw-next,.fsw-finish{min-width:105px;height:38px}.fsw-next,.fsw-finish{background:#0cb9a9!important;border-color:#18d1bf!important;color:#fff!important;font-weight:800}.fsw-notice{font-size:11px;color:#83dcb5}.fsw-notice.bad{color:#ff8e8e}
      .fsw-callout{padding:10px 12px;border-left:3px solid #16c6c9;background:#0a2835;border-radius:5px;color:#b8cfd7;font-size:11px;line-height:1.5;margin:10px 0}.fsw-callout.good{border-color:#2ac47c}.fsw-callout.warn{border-color:#f4bd58}
      .fsw-review{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.fsw-review>div{padding:10px;border:1px solid #1e4353;border-radius:6px;background:#0a2230}.fsw-review b{display:block;color:#eef9fb;font-size:11px}.fsw-review span{color:#9eb5bf;font-size:10px}
      @media(max-width:1120px){.fsw-main{grid-template-columns:170px minmax(0,1fr)}.fsw-right{display:none}.fsw-q{grid-template-columns:1fr}.fsw-grid2{grid-template-columns:1fr}}
      @media(max-width:720px){#setupModal{padding:6px!important}#setupModal>.dialog.setup-dialog{width:calc(100vw - 12px)!important;height:calc(100vh - 12px)}.fsw-main{grid-template-columns:1fr}.fsw-steps{display:none}.fsw-content{padding:15px}.fsw-review{grid-template-columns:1fr}.fsw-top{padding:0 11px}.fsw-logo{width:150px}.fsw-footer{padding:0 11px}}
    `;document.head.appendChild(s);
  }

  function help(text){return `<span class="fsw-help">?<span>${esc(text)}</span></span>`}
  function option(name,value,label,tip=''){return `<button type="button" data-answer="${name}" data-value="${value}" class="${answers[name]===value?'active':''}" title="${esc(tip)}">${esc(label)}</button>`}

  function seedFromLegacy(){
    answers.libraries=getLegacy('wTvEnabled','true')==='true'?'both':'movies';
    answers.plex=getLegacy('wPlexEnabled','false')==='true'?'yes':'no';
    answers.radarr=getLegacy('wRadEnabled','false')==='true'?'yes':'no';
    answers.sonarr=getLegacy('wSonEnabled','false')==='true'?'yes':'no';
    answers.bazarr=getLegacy('wBazEnabled','false')==='true'?'yes':'no';
    answers.gpu=getLegacy('wAsrBackend','local')==='local'?'no':'yes';
    answers.existing=getLegacy('wProcessExisting','true')==='false'?'no':'yes';
    answers.ratings=(getLegacy('wMovieRatingEnabled','false')==='true'||getLegacy('wTvRatingEnabled','false')==='true')?'family':'all';
    answers.pausePlex=getLegacy('wPlexPause','false')==='true'?'yes':'no';
    try{
      const prof=q('.fsProfanityToggle')?.checked!==false,dial=!!q('.fsDialogueToggle')?.checked;
      answers.goal=prof&&dial?'both':dial?'dialogue':'clean';
    }catch(_){}
  }

  function applyAnswers(){
    const tv=answers.libraries==='both', plex=answers.plex==='yes', gpu=answers.gpu==='yes';
    setLegacy('wTvEnabled',tv);setLegacy('wPlexEnabled',plex);setLegacy('wRadEnabled',answers.radarr==='yes');
    setLegacy('wSonEnabled',tv&&answers.sonarr==='yes');setLegacy('wBazEnabled',answers.bazarr==='yes');
    setLegacy('wAsrBackend',gpu?'auto':'local');setLegacy('wProcessExisting',answers.existing==='yes');
    setLegacy('wSubEnabled','true');setLegacy('wMovieRatingEnabled',plex&&answers.ratings==='family');
    setLegacy('wTvRatingEnabled',plex&&tv&&answers.ratings==='family');setLegacy('wPlexPause',plex&&answers.pausePlex==='yes');
    setLegacy('wPlexRefresh',plex);setLegacy('wDry','false');if($('sReview'))$('sReview').value='false';
    try{window.wizardToggleSections?.()}catch(_){}
  }

  function summaryRows(){
    const rows=[
      answers.libraries==='both'?'Configure Movies and TV Shows':'Configure Movies',
      answers.goal==='both'?'Enable Profanity Censoring and Dialogue Enhancement':answers.goal==='clean'?'Enable Profanity Censoring':'Enable Dialogue Enhancement',
      answers.plex==='yes'?'Show Plex connection setup':'Run without Plex',
      `${answers.radarr==='yes'?'Radarr':'No Radarr'} · ${answers.sonarr==='yes'&&answers.libraries==='both'?'Sonarr':'No Sonarr'} · ${answers.bazarr==='yes'?'Bazarr':'No Bazarr'}`,
      answers.gpu==='yes'?`Show ${platformLabel()} GPU Worker setup`:'Use local CPU processing',
      answers.existing==='yes'?'Process existing library and new media':'Only process new or changed media',
      answers.plex==='yes'&&answers.ratings==='family'?'Use PG-13+ / TV-14+ automation thresholds':'Do not limit automation by Plex rating'
    ];
    return rows.map(x=>`<div class="fsw-summary-row"><span class="fsw-check">✓</span><span>${esc(x)}</span></div>`).join('');
  }
  function platformLabel(){return ({windows:'Windows',linux:'Linux',proxmox:'Proxmox / LXC'})[answers.gpuPlatform]||'Linux'}

  function renderChrome(){
    q('#fsWizardSteps').innerHTML=STEPS.map((x,i)=>`<div class="fsw-step ${i===step?'active':i<step?'done':''}"><span class="fsw-num">${i<step?'✓':i+1}</span><span><b>${x[0]}</b><small>${x[1]}</small></span></div>`).join('');
    $('#fsWizardStepPill').textContent=`Step ${step+1} of ${STEPS.length}`;
    $('#fsWizardSummary').innerHTML=summaryRows();
    $('#fsWizardBack').style.visibility=step===0?'hidden':'visible';
    $('#fsWizardNext').style.display=step===STEPS.length-1?'none':'';
    $('#fsWizardFinish').style.display=step===STEPS.length-1?'':'none';
  }

  function welcome(){
    return `<h2>Welcome to Censorarr</h2><div class="fsw-lead">This setup wizard will configure Censorarr around the way you actually use your media server. It only asks for details that cannot be safely chosen for you.</div>
      <div class="fsw-section"><h3>What the wizard will do</h3><p>Answer normal usage questions first. Censorarr will then configure the matching features and skip services you do not use.</p>
      <div class="fsw-callout good"><b>No advanced knowledge required.</b><br>When a URL, API key, path, or GPU worker is needed, the next screen explains exactly what to enter and how to verify it.</div></div>
      <div class="fsw-section"><h3>Nothing is locked in</h3><p>Every choice can be changed later under Settings or Processing Rules.</p></div>`;
  }

  function usage(){
    return `<h2>Usage & Deployment Questions</h2><div class="fsw-lead">Answer a few quick questions so Censorarr can tailor the rest of setup to your server.</div>
      ${question(1,'What do you want Censorarr to create?','goal',`Profanity Censoring creates a CLEAN track. Dialogue Enhancement creates a separate speech-focused track.`,option('goal','both','Both')+option('goal','clean','Profanity only')+option('goal','dialogue','Dialogue only'))}
      ${question(2,'What media do you want to process?','libraries','TV Shows can be disabled entirely if this installation is movies-only.',option('libraries','both','Movies + TV Shows')+option('libraries','movies','Movies only'))}
      ${question(3,'Do you use Plex?','plex','Plex is optional. It adds rating filters, playback-aware pausing and library refresh.',option('plex','yes','Yes')+option('plex','no','No'))}
      ${question(4,'Do you use Radarr?','radarr','Radarr adds richer movie metadata and artwork. Censorarr still works without it.',option('radarr','yes','Yes')+option('radarr','no','No'))}
      ${question(5,'Do you use Sonarr?','sonarr','Sonarr adds TV series and episode metadata. It is only relevant when TV Shows are enabled.',option('sonarr','yes','Yes')+option('sonarr','no','No'))}
      ${question(6,'Do you use Bazarr?','bazarr','Bazarr is optional and can request missing subtitles for subtitle-assisted detection.',option('bazarr','yes','Yes')+option('bazarr','no','No'))}
      ${question(7,'Do you want to use an NVIDIA GPU Worker?','gpu','The GPU worker makes transcription much faster and enables AI Dialogue Isolation. Censorarr can also run without one.',option('gpu','yes','Yes')+option('gpu','no','No — local CPU'))}
      ${answers.gpu==='yes'?question(8,'Where is the NVIDIA GPU?','gpuLocation','Choose whether the GPU worker will run on the same physical/server machine as Censorarr or somewhere else.',option('gpuLocation','same','Same machine')+option('gpuLocation','separate','Separate machine')):''}
      ${answers.gpu==='yes'?question(9,'What platform is the GPU machine using?','gpuPlatform','This changes the installation instructions shown later.',option('gpuPlatform','windows','Windows')+option('gpuPlatform','linux','Linux')+option('gpuPlatform','proxmox','Proxmox / LXC')):''}
      ${question(10,'Do you want Censorarr to process your existing library?','existing','Choose No if you only want future additions or changed files processed automatically.',option('existing','yes','Yes')+option('existing','no','New/changed only'))}
      ${answers.plex==='yes'?question(11,'Use family-safe rating defaults?','ratings','Recommended preset: automate PG-13 and above for Movies and TV-14 and above for TV. Manual Process/Reprocess can still be used on anything.',option('ratings','family','Yes — recommended')+option('ratings','all','All ratings')):''}`;
  }
  function question(n,label,name,tip,buttons){return `<div class="fsw-q"><div class="fsw-q-text"><span class="fsw-q-num">${n}</span><span>${label}</span>${help(tip)}</div><div class="fsw-segment" data-answer-group="${name}">${buttons}</div></div>`}

  function serviceFields(kind,title,urlId,keyId,placeholder,keyLabel){
    const enabled=answers[kind]==='yes';
    if(!enabled)return `<div class="fsw-section"><h3>${title}</h3><p>Skipped based on your Usage answers. You can add it later.</p></div>`;
    const url=getLegacy(urlId,'');
    return `<div class="fsw-section"><h3>${title}</h3><p>Enter the address Censorarr can reach on your local network, then paste the ${keyLabel}.</p>
      <div class="fsw-grid2"><div class="fsw-field"><label>Server URL ${help('Use the LAN address that is reachable from the Censorarr container, including the port.')}</label><input class="fsw-input" data-mirror="${urlId}" value="${esc(url)}" placeholder="${placeholder}"></div>
      <div class="fsw-field"><label>${keyLabel} ${help('Secrets are stored by Censorarr. Leave this blank when an existing saved secret should be kept.')}</label><input class="fsw-input" data-mirror="${keyId}" type="password" placeholder="Leave blank to keep an existing saved secret"></div></div>
      <div class="fsw-test"><button type="button" data-test="${kind}">Save & Test ${title}</button><span class="fsw-status" data-status="${kind}"></span></div>
      ${serviceGuide(kind,title)}</div>`;
  }

  function serviceGuide(kind,title){
    if(kind==='plex')return `<details class="fsw-guide"><summary>Show me exactly where to get the Plex token</summary><ol><li>Open a Movie or TV item in Plex Web and open the three-dot menu.</li><li>Choose <b>Get Info</b>, then click <b>View XML</b>.</li><li>In the browser address bar, copy only the value after <b>X-Plex-Token=</b>.</li><li>Paste that token above and click Save & Test Plex.</li></ol></details>`;
    const key=kind==='radarr'?'Radarr':kind==='sonarr'?'Sonarr':'Bazarr';
    return `<details class="fsw-guide"><summary>Show me exactly where to get the ${key} API key</summary><ol><li>Open ${key}.</li><li>Go to <b>Settings → General</b>.</li><li>Find the <b>Security</b> / API Key area.</li><li>Copy the API Key, paste it above, then click Save & Test.</li></ol></details>`;
  }

  function mediaServices(){
    return `<h2>Connect your media services</h2><div class="fsw-lead">Only the services you selected are shown as active. Each one can be tested before you continue.</div>
      ${serviceFields('plex','Plex','wPlexUrl','wPlexToken','http://PLEX_SERVER_IP:32400','Plex token')}
      ${serviceFields('radarr','Radarr','wRadUrl','wRadKey','http://RADARR_IP:7878','API key')}
      ${answers.libraries==='both'?serviceFields('sonarr','Sonarr','wSonUrl','wSonKey','http://SONARR_IP:8989','API key'):''}
      ${serviceFields('bazarr','Bazarr','wBazUrl','wBazKey','http://BAZARR_IP:6767','API key')}`;
  }

  function paths(){
    const tv=answers.libraries==='both';
    return `<h2>Media paths</h2><div class="fsw-lead">These are the paths <b>inside Censorarr</b>. For Docker/Synology, they must match the container-side volume mappings.</div>
      <div class="fsw-grid2"><div class="fsw-section"><h3>Movies</h3><div class="fsw-field"><label>Censorarr Movies path ${help('Usually /media. The host/NAS folder can have any name; this is the container-side path.')}</label><input class="fsw-input" data-mirror="wMoviesRoot" value="${esc(getLegacy('wMoviesRoot','/media'))}"></div></div>
      ${tv?`<div class="fsw-section"><h3>TV Shows</h3><div class="fsw-field"><label>Censorarr TV path ${help('Usually /tv. This must be the path visible inside the Censorarr container.')}</label><input class="fsw-input" data-mirror="wTvRoot" value="${esc(getLegacy('wTvRoot','/tv'))}"></div></div>`:''}</div>
      <div class="fsw-section"><h3>Synology Container Manager</h3><p>No screenshots are needed. In the Censorarr container's volume settings, map the real NAS folders to these container paths.</p>
        ${code(`Movies host folder  →  /media${tv?'\nTV Shows host folder →  /tv':''}`)}
        <div class="fsw-callout">Example: <b>/volume1/Movies → /media</b> and <b>/volume1/TV Shows → /tv</b>. Censorarr uses the right-hand/container path.</div></div>`;
  }

  function gpu(){
    if(answers.gpu!=='yes')return `<h2>GPU Worker</h2><div class="fsw-lead">You chose local CPU processing.</div><div class="fsw-callout good">Censorarr will use the local CPU for transcription. You can add the NVIDIA GPU Worker later under Settings → Transcription/GPU Worker.</div>`;
    const plat=answers.gpuPlatform, where=answers.gpuLocation==='same'?'same machine':'separate machine';
    return `<h2>NVIDIA GPU Worker</h2><div class="fsw-lead">You selected a ${platformLabel()} GPU on the ${where}. Follow the instructions below, then enter the worker address and test it.</div>
      <div class="fsw-section"><h3>${platformLabel()} installation</h3>${gpuInstructions(plat)}</div>
      <div class="fsw-section"><h3>Connect Censorarr to the worker</h3><div class="fsw-grid2">
        <div class="fsw-field"><label>GPU Worker URL ${help('Use the LAN IP address of the worker and port 9000.')}</label><input class="fsw-input" data-mirror="wAsrUrl" value="${esc(getLegacy('wAsrUrl',''))}" placeholder="http://GPU_WORKER_IP:9000"></div>
        <div class="fsw-field"><label>Worker token ${help('Use the ASR_WORKER_TOKEN generated by the installer or configured in Docker Compose.')}</label><input class="fsw-input" data-mirror="wAsrToken" type="password" placeholder="Paste token, or leave blank to keep saved token"></div></div>
        <div class="fsw-test"><button type="button" data-test="asr">Save & Test GPU Worker</button><span class="fsw-status" data-status="asr"></span></div></div>`;
  }

  function gpuInstructions(plat){
    if(plat==='windows')return `<p>Use the native Windows worker. Docker Desktop is not required for this path.</p><ol><li>Install/update the NVIDIA display driver. Open PowerShell and verify the GPU:</li></ol>${code('nvidia-smi')}<ol start="2"><li>Open the Censorarr GitHub Releases page and download <b>Censorarr-GPU-Worker-Setup-X.Y.Z.exe</b>.</li><li>Run the installer. It installs the worker, downloads its private CUDA runtime, generates a worker token, creates Windows startup, and starts port 9000.</li><li>The installer opens the generated configuration at the end. Copy the token into the field below.</li></ol>`;
    if(plat==='proxmox')return `<p>Recommended Proxmox route: a Debian 12 LXC/CT with the NVIDIA device nodes passed through, then run the Docker GPU worker inside the CT.</p><ol><li>On the Proxmox host, confirm the NVIDIA driver works:</li></ol>${code('nvidia-smi')}<ol start="2"><li>Pass <b>/dev/nvidia0</b>, <b>/dev/nvidiactl</b>, <b>/dev/nvidia-uvm</b>, and <b>/dev/nvidia-uvm-tools</b> into the CT. Enable nesting/keyctl for Docker.</li><li>Inside the CT, confirm the GPU is visible, then confirm Docker can use it:</li></ol>${code('nvidia-smi\ndocker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi')}<ol start="4"><li>Copy the Censorarr gpu-worker project into the CT, set a strong ASR_WORKER_TOKEN, and build it.</li></ol>${code('docker compose up -d --build --force-recreate\ndocker compose ps')}`;
    return `<p>For Debian/Ubuntu, the native package is the simplest installation and does not require Docker.</p><ol><li>Install/update the NVIDIA driver and verify it:</li></ol>${code('nvidia-smi')}<ol start="2"><li>Download <b>Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb</b> from Censorarr Releases and install it:</li></ol>${code('sudo apt install ./Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb')}<ol start="3"><li>Show the generated token and check the service:</li></ol>${code('sudo /opt/censorarr-gpu-worker/CensorarrGPUWorker --show-token\nsystemctl status censorarr-gpu-worker')}`;
  }

  function code(text){return `<div class="fsw-code">${esc(text)}<button type="button" class="fsw-copy" data-copy="${esc(text)}">Copy</button></div>`}

  function processing(){
    return `<h2>Processing Rules</h2><div class="fsw-lead">These choices control automation. Advanced tuning remains available later under Processing Rules.</div>
      ${question(1,'Process existing library automatically?','existing','Yes works through the library you already have. No only handles future/newly changed media.',option('existing','yes','Yes')+option('existing','no','New/changed only'))}
      ${answers.plex==='yes'?question(2,'Use family-safe rating thresholds?','ratings','PG-13+ Movies and TV-14+ TV is the recommended family-focused automation preset.',option('ratings','family','PG-13+ / TV-14+')+option('ratings','all','All ratings')):''}
      ${answers.plex==='yes'?question(3,'Avoid starting heavy jobs while Plex is streaming?','pausePlex','Recommended on smaller servers so Censorarr does not compete with active playback.',option('pausePlex','yes','Yes')+option('pausePlex','no','No')):''}
      <div class="fsw-callout good">Manual Process/Reprocess always remains available. Censorarr no longer uses the old “Needs Review / wait for approval” workflow; CLEAN processing is automatic once an item is selected for processing.</div>`;
  }

  function finish(){
    const cards=[
      ['Audio',answers.goal==='both'?'Profanity Censoring + Dialogue Enhancement':answers.goal==='clean'?'Profanity Censoring only':'Dialogue Enhancement only'],
      ['Libraries',answers.libraries==='both'?'Movies + TV Shows':'Movies only'],
      ['Plex',answers.plex==='yes'?'Connected / enabled':'Standalone'],
      ['Processing',answers.gpu==='yes'?`${platformLabel()} GPU Worker (${answers.gpuLocation==='same'?'same machine':'separate machine'})`:'Local CPU'],
      ['Existing media',answers.existing==='yes'?'Process existing + new media':'Only new/changed media'],
      ['Approval workflow','Automatic — no Needs Review queue']
    ];
    return `<h2>Review and finish</h2><div class="fsw-lead">Censorarr will apply these choices, verify media access, and release automatic processing.</div><div class="fsw-review">${cards.map(([a,b])=>`<div><b>${esc(a)}</b><span>${esc(b)}</span></div>`).join('')}</div><div class="fsw-callout good">Click <b>Finish Setup</b> when you are ready. You can change every setting later.</div>`;
  }

  function page(){if(step===0)return welcome();if(step===1)return usage();if(step===2)return mediaServices();if(step===3)return paths();if(step===4)return gpu();if(step===5)return processing();return finish()}

  function syncMirrors(root){qa('[data-mirror]',root).forEach(el=>{const sync=()=>setLegacy(el.dataset.mirror,el.value);el.addEventListener('input',sync);el.addEventListener('change',sync)})}
  function wire(){
    const body=$('fsWizardBody');syncMirrors(body);
    qa('[data-answer]',body).forEach(b=>b.onclick=()=>{answers[b.dataset.answer]=b.dataset.value;applyAnswers();render()});
    qa('[data-test]',body).forEach(b=>b.onclick=async()=>{applyAnswers();const kind=b.dataset.test,status=q(`[data-status="${kind}"]`,body);b.disabled=true;if(status)status.textContent='Testing…';try{await window.wizardTest?.(kind);const legacy=$({asr:'wAsrStatus',plex:'wPlexStatus',radarr:'wRadStatus',sonarr:'wSonStatus',bazarr:'wBazStatus'}[kind]);if(status)status.textContent=legacy?.textContent||'Test complete.'}catch(e){if(status){status.textContent=e.message||String(e);status.classList.add('bad')}}finally{b.disabled=false}});
    qa('[data-copy]',body).forEach(b=>b.onclick=async()=>{try{await navigator.clipboard.writeText(b.dataset.copy);const t=b.textContent;b.textContent='Copied';setTimeout(()=>b.textContent=t,900)}catch(_){}})
  }
  function render(){applyAnswers();renderChrome();$('#fsWizardBody').innerHTML=page();wire()}

  async function saveAudioChoices(){
    const body={enabled:answers.goal!=='clean',profanity_censoring_enabled:answers.goal!=='dialogue',profanity_source_preference:'best_original',dialogue_source_preference:'auto_clean',dialogue_source_fallback:'original',method:answers.gpu==='yes'?'ai':'classic',ai_model:'mdx_q',ai_fallback_classic:true,ai_worker_cpu_fallback:true};
    const r=await fetch('/api/dialogue-enhancement/settings',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||`HTTP ${r.status}`)
  }

  function build(){
    const modal=$('setupModal'),dialog=modal?.querySelector('.dialog.setup-dialog');if(!modal||!dialog||dialog.dataset.fswV2==='1')return false;dialog.dataset.fswV2='1';addStyles();
    const legacy=document.createElement('div');legacy.className='fs-wizard-legacy';while(dialog.firstChild)legacy.appendChild(dialog.firstChild);dialog.appendChild(legacy);
    const shell=document.createElement('div');shell.className='fsw-shell';shell.innerHTML=`<div class="fsw-top"><img class="fsw-logo" src="/assets/censorarr-logo-wave.svg" alt="Censorarr"><h2>Setup Wizard</h2><span class="fsw-step-pill" id="fsWizardStepPill"></span><button class="fsw-close" id="fsWizardClose">✕</button></div><div class="fsw-main"><aside class="fsw-steps" id="fsWizardSteps"></aside><main class="fsw-content" id="fsWizardBody"></main><aside class="fsw-right"><div class="fsw-side-card"><h3>✦ Based on your answers</h3><div id="fsWizardSummary"></div></div><div class="fsw-side-card"><h3>Next step</h3><div class="fsw-lead" style="margin:0">Censorarr will only ask for information required by your selections.</div></div></aside></div><div class="fsw-footer"><span class="fsw-notice" id="fsWizardNotice"></span><span class="spacer"></span><button class="fsw-back" id="fsWizardBack">← Back</button><button class="fsw-next" id="fsWizardNext">Next →</button><button class="fsw-finish" id="fsWizardFinish">Finish Setup ✓</button></div>`;
    dialog.insertBefore(shell,legacy);
    $('#fsWizardClose').onclick=()=>{if(!firstRun)window.closeSetupWizard?.()};$('#fsWizardBack').onclick=()=>{if(step>0){step--;render()}};$('#fsWizardNext').onclick=()=>{if(step<STEPS.length-1){step++;render()}};
    $('#fsWizardFinish').onclick=async()=>{const b=$('fsWizardFinish');b.disabled=true;notify('Saving settings and checking your media folders…');try{applyAnswers();await saveAudioChoices();await window.finishSetupWizard?.();notify('Setup complete.')}catch(e){notify(`Could not finish setup: ${e.message||e}`,true);b.disabled=false}};
    render();return true
  }

  const originalOpen=window.openSetupWizard;if(typeof originalOpen==='function'){window.openSetupWizard=async function(isFirst=false){firstRun=!!isFirst;step=0;await originalOpen(isFirst);build();seedFromLegacy();applyAnswers();render();const c=$('fsWizardClose');if(c)c.style.visibility=firstRun?'hidden':'visible'}}

  function retireReviewUi(){const review=$('sReview');if(review){review.value='false';review.closest('.field')?.remove()}const card=$('fsReview');if(card)card.remove();qa('h1,h2,h3,b,span,a').filter(x=>/^\s*Needs Review\s*$/i.test(x.textContent||'')).forEach(x=>x.closest('.fs-section,.panel,.section')?.remove())}
  function boot(){retireReviewUi();build();if($('setupModal')?.classList.contains('open')){seedFromLegacy();applyAnswers();render()}new MutationObserver(()=>retireReviewUi()).observe(document.body,{childList:true,subtree:true})}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,1000),{once:true});else setTimeout(boot,1000)
})();