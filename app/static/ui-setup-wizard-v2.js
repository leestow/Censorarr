(() => {
  'use strict';
  if (window.__censorarrSetupWizardV2Loaded) return;
  window.__censorarrSetupWizardV2Loaded = true;

  const $ = id => document.getElementById(id);
  const q = (sel, root=document) => root.querySelector(sel);
  const qa = (sel, root=document) => Array.from(root.querySelectorAll(sel));
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  let currentStep = 0;
  let firstRun = false;
  let built = false;
  let answers = {
    goal: 'both',
    libraries: 'both',
    plex: 'no',
    radarr: 'no',
    sonarr: 'no',
    bazarr: 'no',
    gpu: 'no',
    gpuLocation: 'separate',
    gpuPlatform: 'linux',
    existing: 'yes',
    ratings: 'family',
    pausePlex: 'yes'
  };

  const STEPS = [
    ['Welcome', 'Getting started'],
    ['Usage', 'Tell us how you use Censorarr'],
    ['Media Services', 'Connect only what you use'],
    ['Media Paths', 'Confirm Movies and TV folders'],
    ['GPU Worker', 'Choose where processing runs'],
    ['Automation', 'Choose automatic behavior'],
    ['Finish', 'Review and apply']
  ];

  function setLegacy(id, value) {
    const el = $(id);
    if (el && value !== undefined && value !== null) el.value = String(value);
  }

  function getLegacy(id, fallback='') {
    const el = $(id);
    return el ? String(el.value ?? fallback) : fallback;
  }

  function yes(value) { return String(value) === 'true'; }

  function addStyles() {
    if ($('fsWizardV2Styles')) return;
    const style = document.createElement('style');
    style.id = 'fsWizardV2Styles';
    style.textContent = `
      #setupModal.fs-v2-open{background:rgba(1,10,16,.72)!important;backdrop-filter:blur(3px)}
      #setupModal.fs-v2-open>.dialog.setup-dialog{width:min(1420px,calc(100vw - 34px))!important;max-width:1420px!important;height:min(850px,calc(100vh - 36px))!important;max-height:calc(100vh - 36px)!important;padding:0!important;overflow:hidden!important;border-radius:10px!important;background:#071925!important;border:1px solid #195065!important;box-shadow:0 28px 90px rgba(0,0,0,.5)!important}
      .fs-v2-legacy{display:none!important}
      .fs-v2-shell{height:100%;display:grid;grid-template-rows:64px minmax(0,1fr) 64px;color:#eaf5f8;background:#071925}
      .fs-v2-head{display:flex;align-items:center;gap:14px;padding:0 18px;background:linear-gradient(90deg,#073e50,#075c56);border-bottom:1px solid #176071}
      .fs-v2-logo{width:185px;height:42px;object-fit:contain;object-position:left center}.fs-v2-head h2{font-size:20px;margin:0;color:#fff}.fs-v2-step-pill{font-size:11px;color:#c7dde5;background:#0b3040;border:1px solid #2a6271;border-radius:5px;padding:4px 8px}.fs-v2-close{margin-left:auto;width:34px;height:34px;padding:0!important;color:#e5f4f7!important;background:rgba(0,0,0,.16)!important;border:1px solid rgba(255,255,255,.18)!important}
      .fs-v2-main{display:grid;grid-template-columns:205px minmax(0,1fr) 305px;min-height:0}.fs-v2-nav{overflow:auto;padding:15px 11px;background:#082333;border-right:1px solid #174658}.fs-v2-nav-item{display:grid;grid-template-columns:25px minmax(0,1fr);gap:8px;padding:9px 8px;margin-bottom:3px;border-radius:7px;color:#8eabb7}.fs-v2-nav-item.active{background:#0b5064;color:#fff}.fs-v2-nav-item.done{color:#bdd7df}.fs-v2-num{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;background:#607987;color:#081824;font-size:10px;font-weight:900}.fs-v2-nav-item.active .fs-v2-num{background:#23d0c7}.fs-v2-nav-item.done .fs-v2-num{background:#24b66d;color:#fff}.fs-v2-nav-item b{display:block;font-size:12px;margin-top:1px}.fs-v2-nav-item small{display:block;font-size:9px;line-height:1.3;opacity:.78}
      .fs-v2-body{overflow:auto;padding:20px 22px}.fs-v2-body h2{margin:0 0 5px;font-size:23px;color:#f5fbfd}.fs-v2-lead{color:#94aeba;font-size:12px;line-height:1.5;margin-bottom:15px;max-width:850px}.fs-v2-side{overflow:auto;padding:17px 15px;background:#081f2d;border-left:1px solid #174658}.fs-v2-side-card{border:1px solid #204d5d;border-radius:7px;background:#0a2837;padding:13px;margin-bottom:12px}.fs-v2-side-card h3{margin:0 0 9px;font-size:14px;color:#f3fbfd}.fs-v2-summary{display:flex;gap:8px;padding:6px 0;font-size:10px;line-height:1.4;color:#c0d4dc}.fs-v2-check{flex:0 0 auto;width:17px;height:17px;border-radius:50%;display:grid;place-items:center;background:#20ac68;color:#fff;font-size:10px}
      .fs-v2-question{display:grid;grid-template-columns:minmax(260px,1fr) minmax(220px,310px);gap:12px;align-items:center;border:1px solid #19475a;border-radius:7px;background:#092433;padding:10px 11px;margin-bottom:8px}.fs-v2-question-text{display:flex;align-items:center;gap:8px;font-size:12px;color:#e0edf1}.fs-v2-qnum{width:22px;height:22px;flex:0 0 auto;border:1px solid #315867;border-radius:50%;display:grid;place-items:center;color:#9db8c2;font-size:10px}.fs-v2-options{display:grid;grid-auto-flow:column;grid-auto-columns:1fr;gap:5px}.fs-v2-options button{height:36px;padding:5px!important;background:#0a2b3a!important;color:#bcd3db!important;border:1px solid #2b5666!important}.fs-v2-options button.active{background:#0a625d!important;border-color:#18c9b8!important;color:#ecfffa!important}
      .fs-v2-help{position:relative;display:inline-grid;place-items:center;width:16px;height:16px;min-width:16px;border-radius:50%;background:#117ccc;color:white;font-size:10px;font-weight:900;cursor:help}.fs-v2-help>span{position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);width:285px;padding:9px 10px;border:1px solid #3b5663;border-radius:6px;background:#0a1218;color:#f2f8fa;font-size:10px;line-height:1.45;font-weight:500;opacity:0;visibility:hidden;z-index:50;box-shadow:0 8px 24px rgba(0,0,0,.38)}.fs-v2-help:hover>span,.fs-v2-help:focus>span{opacity:1;visibility:visible}
      .fs-v2-section{border:1px solid #1b4859;border-radius:7px;background:#092433;padding:13px;margin-bottom:11px}.fs-v2-section h3{margin:0 0 4px;font-size:14px;color:#f0f8fb}.fs-v2-section p{margin:0 0 10px;color:#99b2bc;font-size:11px;line-height:1.5}.fs-v2-grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fs-v2-field label{display:flex;align-items:center;gap:5px;margin-bottom:5px;color:#a9c2cb;font-size:10px}.fs-v2-input{width:100%!important;min-width:0!important;height:36px!important;padding:7px 9px!important;border:1px solid #285568!important;background:#0a2a39!important;color:#e3f4f7!important}.fs-v2-test{margin-top:8px}.fs-v2-status{margin-left:8px;color:#69d7a3;font-size:10px}.fs-v2-status.bad{color:#ff8b8b}
      .fs-v2-callout{border-left:3px solid #1ac6be;background:#0a2a39;border-radius:5px;padding:10px 11px;color:#b9ced6;font-size:11px;line-height:1.5;margin:9px 0}.fs-v2-callout.good{border-left-color:#2bc67a}.fs-v2-callout.warn{border-left-color:#f0bc58}.fs-v2-guide{margin-top:9px;border-top:1px solid #1d495a;padding-top:8px}.fs-v2-guide summary{cursor:pointer;color:#6cb2ff;font-size:11px;font-weight:800}.fs-v2-guide ol{padding-left:18px;color:#b7ccd4;font-size:10px;line-height:1.55}.fs-v2-guide img{display:block;width:100%;max-width:720px;margin-top:8px;border:1px solid #315566;border-radius:6px;background:#07141d}.fs-v2-code{position:relative;white-space:pre-wrap;overflow:auto;margin:7px 0;padding:10px 75px 10px 10px;border:1px solid #294b59;border-radius:6px;background:#030a0f;color:#d1ecf4;font:10px/1.55 ui-monospace,Consolas,monospace}.fs-v2-copy{position:absolute;top:6px;right:6px;padding:4px 8px!important;font-size:9px!important}.fs-v2-review{display:grid;grid-template-columns:1fr 1fr;gap:8px}.fs-v2-review>div{border:1px solid #204c5d;border-radius:6px;background:#0a2635;padding:10px}.fs-v2-review b{display:block;color:#f0f9fb;font-size:11px}.fs-v2-review span{display:block;color:#9fb8c2;font-size:10px;margin-top:2px}
      .fs-v2-foot{display:flex;align-items:center;gap:8px;padding:0 18px;border-top:1px solid #174658;background:#081b27}.fs-v2-foot .spacer{flex:1}.fs-v2-back,.fs-v2-next,.fs-v2-finish{height:38px;min-width:105px}.fs-v2-next,.fs-v2-finish{background:#0cb9a8!important;border-color:#1ad1bf!important;color:#fff!important;font-weight:800}.fs-v2-notice{color:#79dbaf;font-size:10px}.fs-v2-notice.bad{color:#ff9090}
      @media(max-width:1080px){.fs-v2-main{grid-template-columns:175px minmax(0,1fr)}.fs-v2-side{display:none}.fs-v2-question{grid-template-columns:1fr}.fs-v2-grid2{grid-template-columns:1fr}}
      @media(max-width:720px){#setupModal.fs-v2-open{padding:5px!important}#setupModal.fs-v2-open>.dialog.setup-dialog{width:calc(100vw - 10px)!important;height:calc(100vh - 10px)!important}.fs-v2-main{grid-template-columns:1fr}.fs-v2-nav{display:none}.fs-v2-body{padding:14px}.fs-v2-review{grid-template-columns:1fr}.fs-v2-logo{width:150px}.fs-v2-head{padding:0 10px}.fs-v2-foot{padding:0 10px}}
    `;
    document.head.appendChild(style);
  }

  function help(text) {
    return `<span class="fs-v2-help" tabindex="0">?<span>${esc(text)}</span></span>`;
  }

  function option(name, value, label) {
    return `<button type="button" data-answer-name="${name}" data-answer-value="${value}" class="${answers[name] === value ? 'active' : ''}">${esc(label)}</button>`;
  }

  function question(number, label, name, helpText, optionsHtml) {
    return `<div class="fs-v2-question"><div class="fs-v2-question-text"><span class="fs-v2-qnum">${number}</span><span>${esc(label)}</span>${help(helpText)}</div><div class="fs-v2-options">${optionsHtml}</div></div>`;
  }

  function seedAnswers() {
    answers.libraries = yes(getLegacy('wTvEnabled','true')) ? 'both' : 'movies';
    answers.plex = yes(getLegacy('wPlexEnabled','false')) ? 'yes' : 'no';
    answers.radarr = yes(getLegacy('wRadEnabled','false')) ? 'yes' : 'no';
    answers.sonarr = yes(getLegacy('wSonEnabled','false')) ? 'yes' : 'no';
    answers.bazarr = yes(getLegacy('wBazEnabled','false')) ? 'yes' : 'no';
    answers.gpu = getLegacy('wAsrBackend','local') === 'local' ? 'no' : 'yes';
    answers.existing = yes(getLegacy('wProcessExisting','true')) ? 'yes' : 'no';
    answers.ratings = yes(getLegacy('wMovieRatingEnabled','false')) || yes(getLegacy('wTvRatingEnabled','false')) ? 'family' : 'all';
    answers.pausePlex = yes(getLegacy('wPlexPause','false')) ? 'yes' : 'no';
    const profanity = q('.fsProfanityToggle');
    const dialogue = q('.fsDialogueToggle');
    if (profanity || dialogue) {
      const p = profanity ? profanity.checked : true;
      const d = dialogue ? dialogue.checked : false;
      answers.goal = p && d ? 'both' : d ? 'dialogue' : 'clean';
    }
  }

  function syncAnswers() {
    const tv = answers.libraries === 'both';
    const plex = answers.plex === 'yes';
    const gpu = answers.gpu === 'yes';
    setLegacy('wTvEnabled', tv);
    setLegacy('wPlexEnabled', plex);
    setLegacy('wRadEnabled', answers.radarr === 'yes');
    setLegacy('wSonEnabled', tv && answers.sonarr === 'yes');
    setLegacy('wBazEnabled', answers.bazarr === 'yes');
    setLegacy('wAsrBackend', gpu ? 'auto' : 'local');
    setLegacy('wProcessExisting', answers.existing === 'yes');
    setLegacy('wSubEnabled', true);
    setLegacy('wMovieRatingEnabled', plex && answers.ratings === 'family');
    setLegacy('wTvRatingEnabled', plex && tv && answers.ratings === 'family');
    setLegacy('wPlexPause', plex && answers.pausePlex === 'yes');
    setLegacy('wPlexRefresh', plex);
    setLegacy('wDry', false);
    if ($('sReview')) $('sReview').value = 'false';
    try { window.wizardToggleSections?.(); } catch (_) {}
  }

  function platformLabel() {
    return ({windows:'Windows', linux:'Linux', proxmox:'Proxmox / LXC', synology:'Synology / Docker'})[answers.gpuPlatform] || 'Linux';
  }

  function summaryHtml() {
    const rows = [
      answers.goal === 'both' ? 'CLEAN + Dialogue Enhanced tracks' : answers.goal === 'clean' ? 'CLEAN tracks only' : 'Dialogue Enhanced tracks only',
      answers.libraries === 'both' ? 'Movies + TV Shows' : 'Movies only',
      answers.plex === 'yes' ? 'Plex setup included' : 'Standalone — no Plex',
      `${answers.radarr === 'yes' ? 'Radarr' : 'No Radarr'} · ${answers.sonarr === 'yes' && answers.libraries === 'both' ? 'Sonarr' : 'No Sonarr'} · ${answers.bazarr === 'yes' ? 'Bazarr' : 'No Bazarr'}`,
      answers.gpu === 'yes' ? `${platformLabel()} GPU worker (${answers.gpuLocation === 'same' ? 'same machine' : 'separate machine'})` : 'Local CPU transcription',
      answers.existing === 'yes' ? 'Existing library + future additions' : 'New/changed media only',
      answers.plex === 'yes' && answers.ratings === 'family' ? 'PG-13+ / TV-14+ automation preset' : 'No Plex rating limit'
    ];
    return rows.map(row => `<div class="fs-v2-summary"><span class="fs-v2-check">✓</span><span>${esc(row)}</span></div>`).join('');
  }

  function welcomePage() {
    return `<h2>Welcome to Censorarr</h2><div class="fs-v2-lead">This wizard asks how you actually use your media server, configures sensible defaults, and only asks for information Censorarr cannot determine on its own.</div>
      <div class="fs-v2-section"><h3>Guided instead of technical</h3><p>You answer normal questions first. Censorarr then shows only the Plex, Radarr, Sonarr, Bazarr, media-path and GPU steps that apply to you.</p><div class="fs-v2-callout good"><b>Nothing here is permanent.</b><br>You can change every choice later in Settings or Processing Rules.</div></div>`;
  }

  function usagePage() {
    let html = `<h2>How will you use Censorarr?</h2><div class="fs-v2-lead">These answers determine the rest of the wizard.</div>`;
    html += question(1,'What do you want Censorarr to create?','goal','CLEAN mutes configured profanity. Dialogue Enhanced creates a separate speech-focused track.',option('goal','both','Both')+option('goal','clean','Profanity only')+option('goal','dialogue','Dialogue only'));
    html += question(2,'What media do you want to process?','libraries','TV Shows can be disabled completely for a movies-only installation.',option('libraries','both','Movies + TV')+option('libraries','movies','Movies only'));
    html += question(3,'Do you use Plex?','plex','Plex is optional. It adds ratings, playback-aware pausing and library refresh.',option('plex','yes','Yes')+option('plex','no','No'));
    html += question(4,'Do you use Radarr?','radarr','Radarr adds movie metadata and artwork. Censorarr can work without it.',option('radarr','yes','Yes')+option('radarr','no','No'));
    if (answers.libraries === 'both') html += question(5,'Do you use Sonarr?','sonarr','Sonarr adds TV series and episode metadata.',option('sonarr','yes','Yes')+option('sonarr','no','No'));
    html += question(6,'Do you use Bazarr?','bazarr','Bazarr is optional and can request missing subtitles.',option('bazarr','yes','Yes')+option('bazarr','no','No'));
    html += question(7,'Do you want to use an NVIDIA GPU Worker?','gpu','The GPU worker speeds transcription and enables AI Dialogue Isolation. Local CPU still works without one.',option('gpu','yes','Yes')+option('gpu','no','No — CPU'));
    if (answers.gpu === 'yes') {
      html += question(8,'Where is the NVIDIA GPU?','gpuLocation','Choose whether the GPU worker runs on the same computer/server as Censorarr or on another machine.',option('gpuLocation','same','Same machine')+option('gpuLocation','separate','Separate machine'));
      html += question(9,'What platform is the GPU machine?','gpuPlatform','The wizard will show installation instructions for this platform.',option('gpuPlatform','windows','Windows')+option('gpuPlatform','linux','Linux')+option('gpuPlatform','proxmox','Proxmox')+option('gpuPlatform','synology','Synology'));
    }
    html += question(10,'Process media already in your library?','existing','Choose New/changed only if you want Censorarr to leave the existing library alone.',option('existing','yes','Yes')+option('existing','no','New/changed only'));
    return html;
  }

  function guideDetails(kind) {
    const data = {
      plex: ['Find your Plex token', ['Open a movie or episode in Plex Web.','Open the three-dot menu and choose Get Info.','Click View XML.','In the browser address bar, copy only the value after X-Plex-Token=.'], '/assets/guide-plex.svg'],
      radarr: ['Find your Radarr API key', ['Open Radarr.','Go to Settings → General.','Find the Security/API Key section.','Copy the API key and paste it into Censorarr.'], '/assets/guide-radarr.svg'],
      sonarr: ['Find your Sonarr API key', ['Open Sonarr.','Go to Settings → General.','Find the Security/API Key section.','Copy the API key and paste it into Censorarr.'], '/assets/guide-sonarr.svg'],
      bazarr: ['Find your Bazarr API key', ['Open Bazarr.','Go to Settings → General.','The API Key is in the Basic section.','Copy the API key and paste it into Censorarr.'], '/assets/guide-bazarr.svg']
    }[kind];
    if (!data) return '';
    const [title, steps, image] = data;
    return `<details class="fs-v2-guide"><summary>Show me exactly where to get this</summary><ol>${steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol><img src="${image}" alt="${esc(title)}" onerror="this.style.display='none'"></details>`;
  }

  function serviceBlock(kind, title, enabled, urlId, secretId, urlPlaceholder) {
    if (!enabled) return `<div class="fs-v2-section"><h3>${esc(title)}</h3><p>Skipped based on your Usage answers.</p></div>`;
    const statusId = `fsV2Status-${kind}`;
    return `<div class="fs-v2-section"><h3>${esc(title)}</h3><p>Enter the local-network address Censorarr can reach, then paste the required secret.</p><div class="fs-v2-grid2">
      <div class="fs-v2-field"><label>Server URL ${help('Include http:// or https:// and the port. Use an address reachable from the Censorarr container.')}</label><input class="fs-v2-input" data-mirror="${urlId}" value="${esc(getLegacy(urlId,''))}" placeholder="${urlPlaceholder}"></div>
      <div class="fs-v2-field"><label>${kind === 'plex' ? 'Plex token' : 'API key'} ${help('This is stored as a secret. Leave the field blank if you want to keep an already-saved secret.')}</label><input class="fs-v2-input" data-mirror="${secretId}" type="password" autocomplete="new-password" placeholder="Paste new value, or leave blank to keep saved"></div></div>
      <div class="fs-v2-test"><button type="button" data-test-kind="${kind}">Save & Test ${esc(title)}</button><span class="fs-v2-status" id="${statusId}"></span></div>${guideDetails(kind)}</div>`;
  }

  function servicesPage() {
    return `<h2>Connect your media services</h2><div class="fs-v2-lead">Only the services you said you use need configuration.</div>
      ${serviceBlock('plex','Plex',answers.plex==='yes','wPlexUrl','wPlexToken','http://PLEX_SERVER_IP:32400')}
      ${serviceBlock('radarr','Radarr',answers.radarr==='yes','wRadUrl','wRadKey','http://RADARR_IP:7878')}
      ${answers.libraries==='both' ? serviceBlock('sonarr','Sonarr',answers.sonarr==='yes','wSonUrl','wSonKey','http://SONARR_IP:8989') : ''}
      ${serviceBlock('bazarr','Bazarr',answers.bazarr==='yes','wBazUrl','wBazKey','http://BAZARR_IP:6767')}`;
  }

  function pathsPage() {
    const tv = answers.libraries === 'both';
    return `<h2>Media paths</h2><div class="fs-v2-lead">Use the paths Censorarr sees inside its container. On Synology/Docker these are usually /media and /tv.</div><div class="fs-v2-grid2">
      <div class="fs-v2-section"><h3>Movies</h3><div class="fs-v2-field"><label>Movies path ${help('Usually /media. This is the container-side path, not the NAS host path.')}</label><input class="fs-v2-input" data-mirror="wMoviesRoot" value="${esc(getLegacy('wMoviesRoot','/media'))}"></div></div>
      ${tv ? `<div class="fs-v2-section"><h3>TV Shows</h3><div class="fs-v2-field"><label>TV path ${help('Usually /tv. This is the container-side path.')}</label><input class="fs-v2-input" data-mirror="wTvRoot" value="${esc(getLegacy('wTvRoot','/tv'))}"></div></div>` : ''}</div>
      <div class="fs-v2-section"><h3>Synology / Docker volume mappings</h3><p>Map the real host folders to the container paths above.</p>${codeBlock(`Movies host folder  →  /media${tv ? '\nTV Shows host folder →  /tv' : ''}`)}<div class="fs-v2-callout">Example: <b>/volume1/Movies → /media</b>${tv ? ' and <b>/volume1/TV Shows → /tv</b>' : ''}.</div></div>`;
  }

  function codeBlock(text) {
    return `<div class="fs-v2-code">${esc(text)}<button type="button" class="fs-v2-copy" data-copy-text="${esc(text)}">Copy</button></div>`;
  }

  function gpuInstructions() {
    if (answers.gpuPlatform === 'windows') {
      return `<p>Use the native Windows GPU Worker installer. Docker Desktop is not required.</p><ol><li>Install/update the NVIDIA driver and verify the GPU in PowerShell:</li></ol>${codeBlock('nvidia-smi')}<ol start="2"><li>Download <b>Censorarr-GPU-Worker-Setup-X.Y.Z.exe</b> from the Censorarr Releases page.</li><li>Run the installer. It installs the worker, downloads its private CUDA runtime, generates a token, enables startup, and listens on port 9000.</li><li>Copy the generated worker token into Censorarr below.</li></ol>`;
    }
    if (answers.gpuPlatform === 'proxmox') {
      return `<p>Use a Debian LXC/CT with the NVIDIA devices passed through, then run the Docker GPU Worker inside the CT.</p><ol><li>Verify the Proxmox host sees the GPU:</li></ol>${codeBlock('nvidia-smi')}<ol start="2"><li>Pass /dev/nvidia0, /dev/nvidiactl, /dev/nvidia-uvm and /dev/nvidia-uvm-tools into the CT. Enable nesting/keyctl.</li><li>Inside the CT, verify NVIDIA and Docker GPU access:</li></ol>${codeBlock('nvidia-smi\ndocker run --rm --gpus all nvidia/cuda:12.2.0-base-ubuntu22.04 nvidia-smi')}<ol start="4"><li>Copy the gpu-worker project into the CT, set a strong ASR_WORKER_TOKEN, and start it:</li></ol>${codeBlock('docker compose up -d --build --force-recreate\ndocker compose ps')}`;
    }
    if (answers.gpuPlatform === 'synology') {
      return `<p>Use this only on a Synology that actually exposes a supported NVIDIA GPU to containers.</p><ol><li>Verify the NAS host can see the GPU with <b>nvidia-smi</b>.</li><li>Install/configure NVIDIA container runtime support for DSM/Container Manager.</li><li>Deploy the Censorarr <b>gpu-worker</b> Docker project with GPU access and a strong ASR_WORKER_TOKEN.</li><li>Verify the worker is running on port 9000, then use the NAS IP below.</li></ol>${codeBlock('docker compose up -d --build --force-recreate\ndocker compose ps')}`;
    }
    return `<p>For Debian/Ubuntu, the native package is the simplest route and does not require Docker.</p><ol><li>Install/update the NVIDIA driver and verify it:</li></ol>${codeBlock('nvidia-smi')}<ol start="2"><li>Download <b>Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb</b> from Releases and install it:</li></ol>${codeBlock('sudo apt install ./Censorarr-GPU-Worker-X.Y.Z-linux-amd64.deb')}<ol start="3"><li>Show the generated token and verify the service:</li></ol>${codeBlock('sudo /opt/censorarr-gpu-worker/CensorarrGPUWorker --show-token\nsystemctl status censorarr-gpu-worker')}`;
  }

  function gpuPage() {
    if (answers.gpu !== 'yes') return `<h2>GPU Worker</h2><div class="fs-v2-lead">You chose local CPU transcription.</div><div class="fs-v2-callout good">No GPU worker is required. Censorarr will use this server for transcription, and you can add a GPU worker later.</div>`;
    const where = answers.gpuLocation === 'same' ? 'same machine as Censorarr' : 'separate machine';
    return `<h2>NVIDIA GPU Worker</h2><div class="fs-v2-lead">You selected ${platformLabel()} on the ${where}.</div><div class="fs-v2-section"><h3>${platformLabel()} installation</h3>${gpuInstructions()}</div><div class="fs-v2-section"><h3>Connect Censorarr to the worker</h3><div class="fs-v2-grid2">
      <div class="fs-v2-field"><label>GPU Worker URL ${help('Use the worker machine LAN IP and port 9000, for example http://192.168.1.50:9000.')}</label><input class="fs-v2-input" data-mirror="wAsrUrl" value="${esc(getLegacy('wAsrUrl',''))}" placeholder="http://GPU_WORKER_IP:9000"></div>
      <div class="fs-v2-field"><label>Worker token ${help('Use the ASR_WORKER_TOKEN generated by the installer or configured in Docker.')}</label><input class="fs-v2-input" data-mirror="wAsrToken" type="password" autocomplete="new-password" placeholder="Paste token, or leave blank to keep saved"></div></div>
      <div class="fs-v2-test"><button type="button" data-test-kind="asr">Save & Test GPU Worker</button><span class="fs-v2-status" id="fsV2Status-asr"></span></div></div>`;
  }

  function automationPage() {
    let html = `<h2>Automatic processing</h2><div class="fs-v2-lead">These are safe starting defaults. Advanced tuning remains under Processing Rules.</div>`;
    html += question(1,'Process the existing library automatically?','existing','Yes works through files already present. New/changed only handles future changes.',option('existing','yes','Yes')+option('existing','no','New/changed only'));
    if (answers.plex === 'yes') {
      html += question(2,'Use the family-focused rating preset?','ratings','Recommended: automate PG-13 and above for Movies and TV-14 and above for TV.',option('ratings','family','PG-13+ / TV-14+')+option('ratings','all','All ratings'));
      html += question(3,'Avoid starting heavy jobs while Plex is streaming?','pausePlex','Recommended on smaller servers so Censorarr does not compete with active playback.',option('pausePlex','yes','Yes')+option('pausePlex','no','No'));
    }
    html += `<div class="fs-v2-callout good">CLEAN processing is automatic. The old “Needs Review / wait for approval” workflow is not part of the family-safe setup.</div>`;
    return html;
  }

  function finishPage() {
    const cards = [
      ['Audio features', answers.goal === 'both' ? 'Profanity Censoring + Dialogue Enhancement' : answers.goal === 'clean' ? 'Profanity Censoring only' : 'Dialogue Enhancement only'],
      ['Libraries', answers.libraries === 'both' ? 'Movies + TV Shows' : 'Movies only'],
      ['Plex', answers.plex === 'yes' ? 'Enabled' : 'Not used'],
      ['GPU', answers.gpu === 'yes' ? `${platformLabel()} · ${answers.gpuLocation === 'same' ? 'same machine' : 'separate machine'}` : 'Local CPU'],
      ['Existing media', answers.existing === 'yes' ? 'Process existing + new media' : 'Only new/changed media'],
      ['Review workflow', 'Automatic — no approval queue']
    ];
    return `<h2>Review and finish</h2><div class="fs-v2-lead">Censorarr will apply these answers, run its normal media-access preflight, and then release automatic processing.</div><div class="fs-v2-review">${cards.map(([a,b])=>`<div><b>${esc(a)}</b><span>${esc(b)}</span></div>`).join('')}</div><div class="fs-v2-callout good">Click <b>Finish Setup</b> when ready.</div>`;
  }

  function pageHtml() {
    if (currentStep === 0) return welcomePage();
    if (currentStep === 1) return usagePage();
    if (currentStep === 2) return servicesPage();
    if (currentStep === 3) return pathsPage();
    if (currentStep === 4) return gpuPage();
    if (currentStep === 5) return automationPage();
    return finishPage();
  }

  function syncMirrors(root) {
    qa('[data-mirror]', root).forEach(el => {
      const update = () => setLegacy(el.dataset.mirror, el.value);
      el.addEventListener('input', update);
      el.addEventListener('change', update);
    });
  }

  async function testConnection(kind, button) {
    syncAnswers();
    const status = $(`fsV2Status-${kind}`);
    if (status) { status.textContent = 'Testing…'; status.classList.remove('bad'); }
    button.disabled = true;
    try {
      if (typeof window.wizardTest !== 'function') throw new Error('Connection test is not available yet.');
      await window.wizardTest(kind);
      const legacyStatus = $({asr:'wAsrStatus',plex:'wPlexStatus',radarr:'wRadStatus',sonarr:'wSonStatus',bazarr:'wBazStatus'}[kind]);
      const text = legacyStatus?.textContent?.trim() || 'Test complete.';
      if (status) { status.textContent = text; status.classList.toggle('bad', /failed/i.test(text)); }
    } catch (err) {
      if (status) { status.textContent = err.message || String(err); status.classList.add('bad'); }
    } finally {
      button.disabled = false;
    }
  }

  function wirePage() {
    const body = $('fsWizardV2Body');
    syncMirrors(body);
    qa('[data-answer-name]', body).forEach(button => {
      button.addEventListener('click', () => {
        answers[button.dataset.answerName] = button.dataset.answerValue;
        syncAnswers();
        render();
      });
    });
    qa('[data-test-kind]', body).forEach(button => button.addEventListener('click', () => testConnection(button.dataset.testKind, button)));
    qa('[data-copy-text]', body).forEach(button => button.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copyText);
        const old = button.textContent;
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = old; }, 800);
      } catch (_) {}
    }));
  }

  function render() {
    if (!built) return;
    syncAnswers();
    $('fsWizardV2Nav').innerHTML = STEPS.map((item, i) => `<div class="fs-v2-nav-item ${i===currentStep?'active':i<currentStep?'done':''}"><span class="fs-v2-num">${i<currentStep?'✓':i+1}</span><span><b>${esc(item[0])}</b><small>${esc(item[1])}</small></span></div>`).join('');
    $('fsWizardV2Step').textContent = `Step ${currentStep + 1} of ${STEPS.length}`;
    $('fsWizardV2Summary').innerHTML = summaryHtml();
    $('fsWizardV2Body').innerHTML = pageHtml();
    $('fsWizardV2Back').style.visibility = currentStep === 0 ? 'hidden' : 'visible';
    $('fsWizardV2Next').style.display = currentStep === STEPS.length - 1 ? 'none' : '';
    $('fsWizardV2Finish').style.display = currentStep === STEPS.length - 1 ? '' : 'none';
    wirePage();
  }

  function notice(text, bad=false) {
    const el = $('fsWizardV2Notice');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('bad', !!bad);
  }

  async function saveAudioChoices() {
    const body = {
      enabled: answers.goal !== 'clean',
      profanity_censoring_enabled: answers.goal !== 'dialogue',
      profanity_source_preference: 'best_original',
      dialogue_source_preference: 'auto_clean',
      dialogue_source_fallback: 'original',
      method: answers.gpu === 'yes' ? 'ai' : 'classic',
      ai_model: 'mdx_q',
      ai_fallback_classic: true,
      ai_worker_cpu_fallback: true
    };
    const response = await fetch('/api/dialogue-enhancement/settings', {
      method: 'POST', credentials: 'same-origin', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
    });
    if (!response.ok) {
      let data = {};
      try { data = await response.json(); } catch (_) {}
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
  }

  async function finish() {
    const button = $('fsWizardV2Finish');
    button.disabled = true;
    notice('Saving settings and checking media access…');
    try {
      syncAnswers();
      await saveAudioChoices();
      if (typeof window.finishSetupWizard !== 'function') throw new Error('Setup completion function is unavailable.');
      window.finishSetupWizard();
      const start = Date.now();
      const poll = setInterval(() => {
        const text = String($('wFinishStatus')?.textContent || '').trim();
        if (/^Could not finish setup:/i.test(text)) {
          clearInterval(poll); button.disabled = false; notice(text, true);
        } else if (/setup complete/i.test(text)) {
          clearInterval(poll); notice(text, false);
        } else if (Date.now() - start > 60000) {
          clearInterval(poll); button.disabled = false;
        }
      }, 200);
    } catch (err) {
      button.disabled = false;
      notice(`Could not finish setup: ${err.message || err}`, true);
    }
  }

  function build() {
    if (built) return true;
    const modal = $('setupModal');
    const dialog = q('#setupModal>.dialog.setup-dialog');
    if (!modal || !dialog) return false;
    addStyles();

    const legacy = document.createElement('div');
    legacy.className = 'fs-v2-legacy';
    while (dialog.firstChild) legacy.appendChild(dialog.firstChild);

    const shell = document.createElement('div');
    shell.className = 'fs-v2-shell';
    shell.innerHTML = `<header class="fs-v2-head"><img class="fs-v2-logo" src="/assets/censorarr-logo-wave.svg" alt="Censorarr"><h2>Setup Wizard</h2><span class="fs-v2-step-pill" id="fsWizardV2Step"></span><button type="button" class="fs-v2-close" id="fsWizardV2Close">✕</button></header><div class="fs-v2-main"><aside class="fs-v2-nav" id="fsWizardV2Nav"></aside><main class="fs-v2-body" id="fsWizardV2Body"></main><aside class="fs-v2-side"><div class="fs-v2-side-card"><h3>✦ Based on your answers</h3><div id="fsWizardV2Summary"></div></div><div class="fs-v2-side-card"><h3>What happens next?</h3><div class="fs-v2-lead" style="margin:0">Censorarr only asks for connection details and paths required by the choices you made.</div></div></aside></div><footer class="fs-v2-foot"><span class="fs-v2-notice" id="fsWizardV2Notice"></span><span class="spacer"></span><button type="button" class="fs-v2-back" id="fsWizardV2Back">← Back</button><button type="button" class="fs-v2-next" id="fsWizardV2Next">Next →</button><button type="button" class="fs-v2-finish" id="fsWizardV2Finish">Finish Setup ✓</button></footer>`;

    dialog.appendChild(shell);
    dialog.appendChild(legacy);
    modal.classList.add('fs-v2-open');
    built = true;

    $('fsWizardV2Back').addEventListener('click', () => { if (currentStep > 0) { currentStep -= 1; render(); } });
    $('fsWizardV2Next').addEventListener('click', () => { if (currentStep < STEPS.length - 1) { currentStep += 1; render(); } });
    $('fsWizardV2Finish').addEventListener('click', finish);
    $('fsWizardV2Close').addEventListener('click', () => { if (!firstRun) window.closeSetupWizard?.(); });
    return true;
  }

  const legacyOpen = window.openSetupWizard;
  if (typeof legacyOpen === 'function') {
    window.openSetupWizard = async function(isFirstRun=false) {
      firstRun = !!isFirstRun;
      currentStep = 0;
      await legacyOpen(isFirstRun);
      if (!build()) return;
      seedAnswers();
      syncAnswers();
      $('setupModal')?.classList.add('fs-v2-open');
      $('fsWizardV2Close').style.visibility = firstRun ? 'hidden' : 'visible';
      render();
    };
  }

  function retireReviewUiOnly() {
    const review = $('sReview');
    if (review) {
      review.value = 'false';
      review.closest('.field')?.classList.add('hidden');
    }
    $('fsReview')?.classList.add('hidden');
  }

  function boot() {
    retireReviewUiOnly();
    build();
    const modal = $('setupModal');
    if (modal?.classList.contains('open')) {
      firstRun = $('wizardCloseBtn')?.classList.contains('hidden') === true;
      seedAnswers();
      syncAnswers();
      $('fsWizardV2Close').style.visibility = firstRun ? 'hidden' : 'visible';
      render();
    }
    new MutationObserver(retireReviewUiOnly).observe(document.body, {childList:true, subtree:true});
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 0), {once:true});
  else setTimeout(boot, 0);
})();
