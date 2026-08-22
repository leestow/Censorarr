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
