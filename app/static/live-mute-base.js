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

/* Keep duplicate operational/configuration destinations out of the main sidebar. */
(() => {
  function removeDuplicateNav(){
    document.querySelectorAll(
      '[data-polish-action="gpu"], [data-final-action="gpu"], [data-polish-action="rules"], [data-final-action="rules"]'
    ).forEach(el=>el.remove());
  }
  function boot(){
    removeDuplicateNav();
    const nav=document.querySelector('.side-nav');
    if(nav)new MutationObserver(removeDuplicateNav).observe(nav,{childList:true,subtree:true});
    setTimeout(removeDuplicateNav,500);
    setTimeout(removeDuplicateNav,1500);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();

/* Profanity List is configuration: move it under Settings directly after Detection. */
(() => {
  function moveProfanityNav(){
    const nav=document.querySelector('.side-nav');
    const settings=nav?.querySelector('.fs-settings-group');
    if(!nav||!settings)return;

    const selector='[data-polish-action="profanity"], [data-final-action="profanity"]';
    const existing=settings.querySelector(selector);
    const main=[...nav.querySelectorAll(selector)].find(el=>!el.closest('.fs-settings-group'));

    if(existing){
      if(main)main.remove();
      return;
    }
    if(!main)return;

    const sub=main.cloneNode(true);
    sub.classList.add('sub');
    sub.innerHTML='<span>Profanity List</span>';
    const detection=settings.querySelector('[data-polish-action="settings:detection"], [data-final-action="settings:detection"]');
    if(detection)detection.insertAdjacentElement('afterend',sub);
    else settings.appendChild(sub);
    main.remove();
  }

  function boot(){
    moveProfanityNav();
    const nav=document.querySelector('.side-nav');
    if(nav)new MutationObserver(moveProfanityNav).observe(nav,{childList:true,subtree:true});
    setTimeout(moveProfanityNav,500);
    setTimeout(moveProfanityNav,1500);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();

/* Live Mute timing lab: fast diagnostics for tuning sub-second Plex mute timing. */
(() => {
  const q=s=>document.querySelector(s);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let busy=false, loadedAdvanced=false;

  function fmt(ms){
    ms=Math.max(0,Number(ms)||0);const total=Math.floor(ms/1000),s=total%60,m=Math.floor(total/60)%60,h=Math.floor(total/3600);
    return h?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${m}:${String(s).padStart(2,'0')}`;
  }
  function countdown(ms){
    const n=Number(ms);
    if(!Number.isFinite(n))return '—';
    if(n<=0&&n>-1200)return 'NOW';
    if(n<0)return `${(Math.abs(n)/1000).toFixed(2)}s past`;
    if(n<10000)return `${(n/1000).toFixed(2)}s`;
    if(n<60000)return `${(n/1000).toFixed(1)}s`;
    return fmt(n);
  }
  function ensureStyles(){
    if(q('#lmTimingLabStyles'))return;
    const s=document.createElement('style');s.id='lmTimingLabStyles';s.textContent=`
      .lm-lab{margin-top:16px;border-top:1px solid var(--line,#294455);padding-top:15px}
      .lm-lab-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
      .lm-lab-head h4{margin:0;font-size:14px}.lm-live-pill{font-size:10px;font-weight:800;letter-spacing:.08em;border:1px solid var(--line,#294455);border-radius:999px;padding:4px 8px}
      .lm-live-pill.on{color:#22d58b;border-color:#22d58b}.lm-live-pill.muted{color:#ffcc4d;border-color:#ffcc4d}
      .lm-lab-grid{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:8px}
      .lm-lab-card{background:var(--panel2,rgba(255,255,255,.035));border:1px solid var(--line,#294455);border-radius:7px;padding:10px}
      .lm-lab-card span{display:block;color:var(--muted,#8295a6);font-size:10px;text-transform:uppercase;letter-spacing:.05em}.lm-lab-card b{display:block;margin-top:4px;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .lm-next{margin-top:9px;border:1px solid var(--line,#294455);border-radius:7px;padding:11px}.lm-next-line{display:flex;justify-content:space-between;gap:10px;align-items:center}.lm-countdown{font-size:22px;font-weight:800}.lm-next small{color:var(--muted,#8295a6)}
      .lm-advanced{margin-top:10px}.lm-advanced summary{cursor:pointer;color:var(--muted,#8295a6);font-size:12px}.lm-advanced-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.lm-advanced .field input{width:100%}
      .lm-events{margin-top:10px}.lm-events-row{display:grid;grid-template-columns:70px 90px 1fr;gap:8px;font-size:11px;padding:6px 0;border-bottom:1px solid var(--line,#294455)}.lm-events-row:last-child{border-bottom:0}.lm-event-mute{color:#ffcc4d}.lm-event-unmute{color:#22d58b}
      @media(max-width:900px){.lm-lab-grid{grid-template-columns:repeat(2,1fr)}.lm-advanced-grid{grid-template-columns:1fr}.lm-events-row{grid-template-columns:65px 80px 1fr}}
    `;document.head.appendChild(s);
  }
  function ensure(){
    const host=q('#censorarrLiveMuteSettings');if(!host)return null;
    if(q('#lmTimingLab'))return q('#lmTimingLab');
    ensureStyles();
    const div=document.createElement('div');div.id='lmTimingLab';div.className='lm-lab';div.innerHTML=`
      <div class="lm-lab-head"><div><h4>Experimental Timing Lab</h4><div class="footer-note">Watch the next stored profanity window and tune Plex control timing.</div></div><span id="lmLabPill" class="lm-live-pill">WAITING</span></div>
      <div class="lm-lab-grid">
        <div class="lm-lab-card"><span>Player</span><b id="lmLabPlayer">—</b></div>
        <div class="lm-lab-card"><span>Playback</span><b id="lmLabPosition">—</b></div>
        <div class="lm-lab-card"><span>Stored ranges</span><b id="lmLabRanges">—</b></div>
        <div class="lm-lab-card"><span>Live compensation</span><b id="lmLabPadding">—</b></div>
      </div>
      <div class="lm-next"><div class="lm-next-line"><div><small>Next live mute trigger</small><div><b id="lmLabNextWindow">No upcoming range</b></div></div><div id="lmLabCountdown" class="lm-countdown">—</div></div><div class="footer-note" id="lmLabNextDetail" style="margin-top:5px">Play analyzed media to load its saved mute ranges.</div></div>
      <details class="lm-advanced"><summary>Advanced controller timing</summary><div class="lm-advanced-grid">
        <div class="field"><label>Controller loop</label><input id="lmLoopMs" type="number" min="25" max="500" step="5"><div class="footer-note">How often Censorarr checks the predicted position. Default 50 ms.</div></div>
        <div class="field"><label>Plex timeline resync</label><input id="lmSyncMs" type="number" min="100" max="2000" step="25"><div class="footer-note">Fresh player position/volume poll. Default 350 ms.</div></div>
        <div class="field"><label>Session refresh</label><input id="lmRefreshMs" type="number" min="300" max="5000" step="50"><div class="footer-note">How often active Plex sessions are rediscovered. Default 900 ms.</div></div>
      </div><div class="toolbar" style="margin-top:8px"><button id="lmSaveAdvanced">Save advanced timing</button><span id="lmAdvancedMsg" class="footer-note"></span></div></details>
      <div class="lm-events"><div style="font-size:12px;font-weight:700;margin-bottom:5px">Recent controller events</div><div id="lmLabEvents" class="footer-note">No mute events yet.</div></div>`;
    host.appendChild(div);
    q('#lmSaveAdvanced').onclick=saveAdvanced;
    return div;
  }
  async function api(path,options={}){
    const r=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let d={};try{d=await r.json()}catch(_){ }
    if(!r.ok)throw new Error(d.detail||d.error||`HTTP ${r.status}`);return d;
  }
  async function saveAdvanced(){
    const b=q('#lmSaveAdvanced'),msg=q('#lmAdvancedMsg');if(!b)return;
    b.disabled=true;msg.textContent='Saving…';
    try{
      await api('/api/live-mute/settings',{method:'POST',body:JSON.stringify({loop_ms:Number(q('#lmLoopMs').value||50),timeline_sync_ms:Number(q('#lmSyncMs').value||350),session_refresh_ms:Number(q('#lmRefreshMs').value||900)})});
      msg.textContent='Saved.';setTimeout(()=>{if(msg)msg.textContent=''},1200);
    }catch(e){msg.textContent=`Save failed: ${e.message||e}`}finally{b.disabled=false}
  }
  function render(data){
    if(!ensure())return;
    const settings=data.settings||{},sessions=data.sessions||[];
    if(!loadedAdvanced){
      q('#lmLoopMs').value=settings.loop_ms??50;q('#lmSyncMs').value=settings.timeline_sync_ms??350;q('#lmRefreshMs').value=settings.session_refresh_ms??900;loadedAdvanced=true;
    }
    const s=sessions.find(x=>String(x.state||'').toLowerCase()==='playing')||sessions[0];
    const pill=q('#lmLabPill');
    if(!settings.enabled){pill.textContent='DISABLED';pill.className='lm-live-pill'}
    else if(s?.muted){pill.textContent='MUTED';pill.className='lm-live-pill muted'}
    else if(s){pill.textContent='ARMED';pill.className='lm-live-pill on'}
    else{pill.textContent='WAITING';pill.className='lm-live-pill'}
    q('#lmLabPlayer').textContent=s?`${s.player||'Unknown'} · ${s.user||'Unknown'}`:'No active player';
    q('#lmLabPosition').textContent=s?fmt(s.position_ms):'—';
    q('#lmLabRanges').textContent=s?String(s.range_count??0):'—';
    q('#lmLabPadding').textContent=`-${settings.lead_ms??220} / +${settings.tail_ms??140} ms`;
    const n=s?.next_range;
    if(n){
      const trigger=Number(n.start_ms)-Number(settings.lead_ms??220),delta=trigger-Number(s.position_ms||0);
      q('#lmLabNextWindow').textContent=`${fmt(n.start_ms)} – ${fmt(n.end_ms)}`;
      q('#lmLabCountdown').textContent=countdown(delta);
      q('#lmLabNextDetail').textContent=`Mute command target ${fmt(trigger)} · saved range ${(Number(n.end_ms)-Number(n.start_ms))} ms · current ${fmt(s.position_ms)}`;
    }else{
      q('#lmLabNextWindow').textContent='No upcoming range';q('#lmLabCountdown').textContent='—';
      q('#lmLabNextDetail').textContent=s?(s.range_count?'All saved profanity ranges are behind the current position.':'This media has no saved mute-range report.'):'Play analyzed media to load its saved mute ranges.';
    }
    const events=(data.recent_events||[]).slice(0,8),box=q('#lmLabEvents');
    if(!events.length){box.innerHTML='<span class="footer-note">No mute events yet.</span>';return}
    box.innerHTML=events.map(e=>{
      const when=new Date(Number(e.timestamp||0)*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
      const detail=e.start_ms!=null?`${fmt(e.start_ms)}–${fmt(e.end_ms)}${e.restore_volume!=null?` · restore ${esc(e.restore_volume)}%`:''}`:esc(e.reason||'');
      return `<div class="lm-events-row"><b class="lm-event-${esc(e.action)}">${esc(String(e.action||'').toUpperCase())}</b><span>${esc(when)}</span><span>${detail}</span></div>`;
    }).join('');
  }
  async function poll(){
    if(busy||!ensure())return;busy=true;
    try{render(await api('/api/live-mute/status'))}catch(e){const d=q('#lmLabNextDetail');if(d)d.textContent=`Timing status unavailable: ${e.message||e}`}finally{busy=false}
  }
  function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(ensure()){clearInterval(timer);poll();setInterval(poll,350)}else if(tries>50)clearInterval(timer)},200)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
