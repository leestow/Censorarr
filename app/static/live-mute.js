(() => {
  const ID='censorarrLiveMuteSettings';
  let formLoaded=false, formDirty=false;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  async function req(path, options={}){
    const r=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let data={}; try{data=await r.json()}catch(_){ }
    if(!r.ok) throw new Error(data.detail||data.error||`HTTP ${r.status}`);
    return data;
  }
  function fmt(ms){
    ms=Math.max(0,Number(ms)||0);const total=Math.floor(ms/1000),s=total%60,m=Math.floor(total/60)%60,h=Math.floor(total/3600);
    return h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`;
  }
  function findPage(){
    return document.querySelector('.settings-page[data-settings="plex"]')
      || document.querySelector('.settings-page[data-settings="general"]')
      || document.querySelector('.settings-page:not(.hidden)')
      || document.querySelector('.settings-page');
  }
  function ensure(){
    if(document.getElementById(ID)) return document.getElementById(ID);
    const page=findPage(); if(!page)return null;
    const section=document.createElement('div');section.className='section';section.id=ID;
    section.innerHTML=`
      <h3>Experimental: Live Profanity Mute</h3>
      <div class="footer-note" style="margin-bottom:12px">Uses the profanity timestamps Censorarr already detected and mutes the Plex player only while a flagged word is playing. No new audio track is required. Keep this experimental until your Plex client passes the test mute reliably.</div>
      <label style="display:flex;align-items:center;gap:10px;margin:10px 0"><input id="lmEnabled" type="checkbox"><b>Enable Live Mute</b></label>
      <div class="field" style="margin-top:10px"><label>Filtered Plex users <span class="muted">(comma-separated; blank = all users)</span></label><input id="lmUsers" placeholder="Family, Kids"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px">
        <div class="field"><label>Mute early</label><div style="display:flex;align-items:center;gap:8px"><input id="lmLead" type="number" min="0" max="1500" step="10"><span class="muted">ms</span></div></div>
        <div class="field"><label>Restore late</label><div style="display:flex;align-items:center;gap:8px"><input id="lmTail" type="number" min="0" max="1500" step="10"><span class="muted">ms</span></div></div>
      </div>
      <label style="display:flex;align-items:center;gap:10px;margin:12px 0"><input id="lmRequireVolume" type="checkbox"><span>Only mute when the current Plex volume can be read and safely restored</span></label>
      <div class="toolbar" style="margin-top:12px"><button id="lmSave">Save Live Mute settings</button><button id="lmTest">Test active Plex player (0.8 sec)</button></div>
      <div class="footer-note" id="lmMessage" style="margin-top:10px">Loading Live Mute status…</div>
      <div id="lmSessions" style="margin-top:12px"></div>`;
    page.appendChild(section);
    document.getElementById('lmSave').onclick=save;
    document.getElementById('lmTest').onclick=test;
    section.querySelectorAll('input').forEach(el=>el.addEventListener('input',()=>{formDirty=true}));
    return section;
  }
  function render(data){
    if(!ensure())return;
    const s=data.settings||{};
    if(!formLoaded&&!formDirty){
      document.getElementById('lmEnabled').checked=!!s.enabled;
      document.getElementById('lmUsers').value=(s.users||[]).join(', ');
      document.getElementById('lmLead').value=s.lead_ms??220;
      document.getElementById('lmTail').value=s.tail_ms??140;
      document.getElementById('lmRequireVolume').checked=s.require_volume_probe!==false;
      formLoaded=true;
    }
    const msg=document.getElementById('lmMessage');
    if(data.last_error) msg.textContent=`Controller warning: ${data.last_error}`;
    else msg.textContent=s.enabled?'Live Mute is armed. It only acts on Plex sessions that have a Censorarr report with mute ranges.':'Live Mute is disabled.';
    const host=document.getElementById('lmSessions');const sessions=data.sessions||[];
    if(!sessions.length){host.innerHTML='<div class="footer-note">No eligible Plex video session is active right now.</div>';return}
    host.innerHTML=`<div style="font-weight:700;margin-bottom:6px">Active Plex sessions</div>${sessions.map(x=>{
      const volume=x.volume_probe_ok?`volume ${esc(x.current_volume)}%`:'volume unavailable';
      const report=x.range_count?`${x.range_count} mute range${x.range_count===1?'':'s'}`:'no mute-range report';
      const next=x.next_range?` · next ${fmt(x.next_range.start_ms)}–${fmt(x.next_range.end_ms)}`:'';
      const err=x.error?`<div class="footer-note" style="margin-top:4px">${esc(x.error)}</div>`:'';
      return `<div style="border:1px solid var(--line,#294455);border-radius:7px;padding:9px 10px;margin:6px 0"><div style="display:flex;justify-content:space-between;gap:10px"><b>${esc(x.title)}</b><span>${x.muted?'🔇 MUTED':'Listening'}</span></div><div class="footer-note">${esc(x.user)} · ${esc(x.player)} · ${esc(x.state)} · ${fmt(x.position_ms)} · ${esc(volume)} · ${esc(report)}${next}</div>${err}</div>`;
    }).join('')}`;
  }
  async function load(){
    try{render(await req('/api/live-mute/status'))}
    catch(err){const el=document.getElementById('lmMessage');if(el)el.textContent=`Live Mute status failed: ${err.message||err}`}
  }
  async function save(){
    const b=document.getElementById('lmSave');b.disabled=true;b.textContent='Saving…';
    try{
      const body={enabled:document.getElementById('lmEnabled').checked,users:document.getElementById('lmUsers').value,lead_ms:Number(document.getElementById('lmLead').value||220),tail_ms:Number(document.getElementById('lmTail').value||140),require_volume_probe:document.getElementById('lmRequireVolume').checked};
      await req('/api/live-mute/settings',{method:'POST',body:JSON.stringify(body)});formDirty=false;formLoaded=false;await load();b.textContent='Saved';setTimeout(()=>b.textContent='Save Live Mute settings',900);
    }catch(err){alert(`Could not save Live Mute settings:\n\n${err.message||err}`);b.textContent='Save Live Mute settings'}finally{b.disabled=false}
  }
  async function test(){
    const b=document.getElementById('lmTest');b.disabled=true;b.textContent='Testing…';
    try{const r=await req('/api/live-mute/test',{method:'POST',body:'{}'});alert(`Live Mute test succeeded on ${r.player}.\n\nVolume was restored to ${r.restored_volume}%.`);await load()}
    catch(err){alert(`Live Mute test failed:\n\n${err.message||err}`)}finally{b.disabled=false;b.textContent='Test active Plex player (0.8 sec)'}
  }
  function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(ensure()){clearInterval(timer);load();setInterval(load,2500)}else if(tries>40)clearInterval(timer)},250)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();

/* Keep sidebar destinations distinct: Processing Rules owns detection settings, while Logs is a log-only view. */
(() => {
  const q = (s, root=document) => root.querySelector(s);
  const qa = (s, root=document) => [...root.querySelectorAll(s)];

  function addStyles(){
    if(q('#fsNavCleanupStyles'))return;
    const style=document.createElement('style');style.id='fsNavCleanupStyles';
    style.textContent=`
      #fsOperationsPane.fs-nav-logs .fs-ops-toolbar,
      #fsOperationsPane.fs-nav-logs .fs-nav-status-grid,
      #fsOperationsPane.fs-nav-logs .fs-nav-queue-panel{display:none!important}
      #fsOperationsPane.fs-nav-logs .fs-nav-bottom-grid{grid-template-columns:minmax(0,1fr)!important}
      #fsOperationsPane.fs-nav-logs .fs-nav-log-panel{grid-column:1/-1!important}
      #fsOperationsPane.fs-nav-gpu .fs-ops-segment{display:none!important}
    `;document.head.appendChild(style);
  }

  function removeDuplicateDetectionNav(){
    qa('[data-polish-action="settings:detection"]').forEach(el=>el.remove());
    qa('[data-final-action="settings:detection"]').forEach(el=>el.remove());
  }

  function tagOperationsLayout(){
    const pane=q('#fsOperationsPane');if(!pane)return null;
    const grids=qa(':scope > .fs-ops-grid',pane);
    grids[0]?.classList.add('fs-nav-status-grid');
    grids[1]?.classList.add('fs-nav-bottom-grid');
    if(grids[1]){
      const panels=qa(':scope > .fs-ops-panel',grids[1]);
      panels[0]?.classList.add('fs-nav-log-panel');
      panels[1]?.classList.add('fs-nav-queue-panel');
    }
    return pane;
  }

  function currentOperationsMode(){
    if(q('[data-polish-action="gpu"].active,[data-final-action="gpu"].active'))return 'gpu';
    if(q('[data-polish-action="logs"].active,[data-final-action="logs"].active'))return 'logs';
    const title=q('#pageTitle')?.textContent?.trim().toLowerCase()||'';
    if(title==='gpu worker')return 'gpu';
    if(title==='live logs'||title==='logs')return 'logs';
    return '';
  }

  function applyOperationsMode(){
    const pane=tagOperationsLayout();if(!pane||!pane.classList.contains('active'))return;
    const mode=currentOperationsMode();
    pane.classList.toggle('fs-nav-gpu',mode==='gpu');
    pane.classList.toggle('fs-nav-logs',mode==='logs');
    const heading=q('.fs-nav-log-panel .fs-ops-log-head h2');
    const local=q('#fsOpsLogLocal'),gpu=q('#fsOpsLogGpu');
    if(mode==='gpu'){
      if(heading&&heading.textContent!=='GPU Worker Log')heading.textContent='GPU Worker Log';
      if(gpu&&!gpu.classList.contains('active'))gpu.click();
    }else if(mode==='logs'){
      if(heading&&heading.textContent!=='Live Logs')heading.textContent='Live Logs';
      if(local&&!local.classList.contains('active'))local.click();
    }
  }

  function normalizeProcessingRules(){
    const detection=q('.settings-page[data-settings="detection"].active');if(!detection)return;
    const title=q('#pageTitle'),subtitle=q('#pageSubtitle');
    if(title&&title.textContent!=='Processing Rules')title.textContent='Processing Rules';
    const text='Profanity detection, mute timing, rescue behavior, and CLEAN audio output';
    if(subtitle&&subtitle.textContent!==text)subtitle.textContent=text;
  }

  function apply(){addStyles();removeDuplicateDetectionNav();tagOperationsLayout();applyOperationsMode();normalizeProcessingRules();}

  function boot(){
    apply();
    document.addEventListener('click',()=>setTimeout(apply,0),true);
    const title=q('#pageTitle');if(title)new MutationObserver(apply).observe(title,{childList:true,characterData:true,subtree:true});
    const nav=q('.side-nav');if(nav)new MutationObserver(apply).observe(nav,{childList:true,subtree:true,attributes:true,attributeFilter:['class']});
    setInterval(apply,1500);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,400));else setTimeout(boot,400);
})();
