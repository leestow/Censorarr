(() => {
  const q=(s,r=document)=>r.querySelector(s);
  let busy=false,lastPaused=null;

  async function request(path,options={}){
    const response=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let data={};try{data=await response.json()}catch(_){ }
    if(!response.ok)throw new Error(data.detail||data.error||`HTTP ${response.status}`);
    return data;
  }

  function addStyles(){
    if(q('#fsOverviewControlStyles'))return;
    const s=document.createElement('style');s.id='fsOverviewControlStyles';s.textContent=`
      #fsStopPauseBtn{border-color:rgba(255,191,76,.58)!important;color:#ffe0a2!important;background:rgba(117,65,5,.30)!important;min-width:142px}
      #fsStopPauseBtn:hover{background:rgba(145,78,5,.44)!important}
      #fsStopPauseBtn.paused{border-color:rgba(71,224,155,.58)!important;color:#98f3c8!important;background:rgba(10,103,66,.32)!important}
      #fsStopPauseBtn.working{opacity:.72;cursor:wait!important}
      @media(max-width:1050px){#fsStopPauseBtn{min-width:0;padding-left:10px!important;padding-right:10px!important}.fs-stop-label{display:none}}
    `;document.head.appendChild(s);
  }

  function ensureButton(){
    const scan=q('#fsScanBtn');
    if(!scan?.parentElement)return null;
    let b=q('#fsStopPauseBtn');
    if(!b){
      b=document.createElement('button');
      b.id='fsStopPauseBtn';b.className='fs-topbtn';
      scan.parentElement.insertBefore(b,scan.nextSibling);
      b.addEventListener('click',toggleStopPause);
    }
    renderButton(lastPaused);
    return b;
  }

  function renderButton(paused){
    const b=q('#fsStopPauseBtn');if(!b)return;
    const isPaused=paused===true;
    b.classList.toggle('paused',isPaused);b.classList.toggle('working',busy);b.disabled=busy;
    if(busy){b.innerHTML='⏳ <span class="fs-stop-label">Working…</span>';return;}
    b.innerHTML=isPaused?'▶ <span class="fs-stop-label">Resume Automation</span>':'■ <span class="fs-stop-label">Stop & Pause</span>';
    b.title=isPaused?'Resume automatic Censorarr processing':'Stop the current job and pause automatic processing';
  }

  async function refreshState(){
    try{
      const s=await request('/api/status');
      lastPaused=!!s.paused;ensureButton();renderButton(lastPaused);
    }catch(_){ensureButton();}
  }

  async function toggleStopPause(){
    if(busy)return;
    busy=true;renderButton(lastPaused);
    try{
      if(lastPaused){
        await request('/api/control/resume',{method:'POST',body:'{}'});
        lastPaused=false;
      }else{
        // Pause FIRST. stop-current restarts the worker, and the pause flag must already
        // exist so the restarted worker cannot claim the next queued/library item.
        await request('/api/control/pause',{method:'POST',body:'{}'});
        try{
          await request('/api/control/stop-current',{method:'POST',body:'{}'});
        }catch(stopErr){
          // Even if there is no cancellable current item, keeping automation paused is
          // still the safest interpretation of the user's request.
          console.debug('Censorarr current-job stop result:',stopErr);
        }
        lastPaused=true;
      }
    }catch(err){
      alert(`Censorarr control failed:\n\n${err.message||err}`);
    }finally{
      busy=false;renderButton(lastPaused);setTimeout(refreshState,800);
    }
  }

  function boot(){addStyles();ensureButton();refreshState();setInterval(refreshState,5000);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,650));else setTimeout(boot,650);
})();
