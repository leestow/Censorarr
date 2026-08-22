(() => {
  const q=s=>document.querySelector(s);
  let saving=false;

  async function api(path, options={}){
    const r=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let d={};try{d=await r.json()}catch(_){ }
    if(!r.ok)throw new Error(d.detail||d.error||`HTTP ${r.status}`);
    return d;
  }

  function ensure(){
    const enabled=q('#lmEnabled');
    if(!enabled)return false;
    if(!q('#lmSimulationRow')){
      const row=document.createElement('label');
      row.id='lmSimulationRow';
      row.style.cssText='display:flex;align-items:flex-start;gap:10px;margin:12px 0;padding:10px;border:1px solid var(--line,#294455);border-radius:7px';
      row.innerHTML='<input id="lmSimulationMode" type="checkbox" style="margin-top:2px"><span><b>Simulation Mode</b><span class="footer-note" style="display:block;margin-top:3px">Run the real profanity timing engine and log simulated mute/unmute events, but never send a volume command to Plex.</span><span id="lmSimulationState" class="footer-note" style="display:block;margin-top:4px"></span></span>';
      enabled.closest('label')?.insertAdjacentElement('afterend',row);
      q('#lmSimulationMode').addEventListener('change',save);
    }
    return true;
  }

  function apply(data){
    if(!ensure())return;
    const settings=data.settings||{};
    const sim=!!settings.simulation_mode;
    const box=q('#lmSimulationMode');
    if(box&&!saving)box.checked=sim;
    const state=q('#lmSimulationState');
    if(state){
      state.textContent=sim
        ? (settings.enabled?'ON — simulation is armed; Plex volume will not be changed.':'ON, but Live Mute itself is currently disabled.')
        : 'OFF — normal Live Mute behavior.';
    }
    const test=q('#lmTest');
    if(test){
      test.disabled=sim;
      test.title=sim?'Turn off Simulation Mode to send a real 0.8 second mute command.':'';
      if(sim)test.textContent='Player mute test disabled in Simulation Mode';
      else if(test.textContent==='Player mute test disabled in Simulation Mode')test.textContent='Test active Plex player (0.8 sec)';
    }
    // Do not write #lmLabPill here. The main Timing Lab owns that badge and
    // refreshes it on its own cadence. Two writers caused ARMED/SIMULATION flicker.
  }

  async function save(){
    const box=q('#lmSimulationMode'),state=q('#lmSimulationState');
    if(!box)return;
    saving=true;box.disabled=true;if(state)state.textContent='Saving…';
    try{
      const data=await api('/api/live-mute/settings',{method:'POST',body:JSON.stringify({simulation_mode:box.checked})});
      apply({settings:data.settings||{},sessions:[]});
    }catch(e){
      box.checked=!box.checked;
      if(state)state.textContent=`Could not save Simulation Mode: ${e.message||e}`;
    }finally{
      saving=false;box.disabled=false;
    }
  }

  async function poll(){
    if(!ensure())return;
    try{apply(await api('/api/live-mute/status'))}catch(_){ }
  }

  function boot(){
    let tries=0;
    const t=setInterval(()=>{
      tries++;
      if(ensure()){clearInterval(t);poll();setInterval(poll,500)}
      else if(tries>60)clearInterval(t);
    },200);
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
