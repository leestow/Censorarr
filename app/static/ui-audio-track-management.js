(() => {
  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

  async function request(path,options={}){
    const r=await fetch(path,{credentials:'same-origin',headers:{'Content-Type':'application/json'},...options});
    let data={};try{data=await r.json()}catch(_){ }
    if(!r.ok)throw new Error(data.detail||data.error||`HTTP ${r.status}`);return data;
  }

  function fmtTime(seconds){
    const s=Math.max(0,Math.round(Number(seconds)||0));
    if(s<60)return `${s}s`;
    const m=Math.floor(s/60),r=s%60;
    if(m<60)return `${m}m ${String(r).padStart(2,'0')}s`;
    const h=Math.floor(m/60),mm=m%60;
    return `${h}h ${mm}m`;
  }

  function styles(){
    if(q('#fsAudioTrackManagerStyles'))return;
    const s=document.createElement('style');s.id='fsAudioTrackManagerStyles';s.textContent=`
      .fs-audio-manager-note{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;margin-bottom:10px;border:1px solid var(--line);border-radius:7px;background:var(--panel2);color:var(--muted);font-size:11px;line-height:1.45}
      .fs-audio-lock{font-size:16px;line-height:1}.fs-audio-table td{vertical-align:middle}.fs-audio-title{font-weight:760}.fs-audio-sub{font-size:10px;color:var(--muted);margin-top:2px}
      .fs-audio-kind{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:999px;font-size:10px;font-weight:760;border:1px solid var(--line);background:var(--panel2)}
      .fs-audio-kind.generated{color:#29d39a;border-color:color-mix(in srgb,#29d39a 45%,var(--line));background:color-mix(in srgb,#29d39a 9%,var(--panel2))}
      .fs-audio-kind.protected{color:var(--muted)}.fs-audio-row.removable{cursor:pointer}.fs-audio-row.removable:hover td{background:color-mix(in srgb,var(--accent2) 8%,var(--panel2))!important}
      .fs-audio-remove{white-space:nowrap}.fs-audio-remove[disabled]{cursor:not-allowed;opacity:.55}.fs-audio-loading{padding:14px;color:var(--muted)}
      .fs-audio-progress{margin:0 0 11px;padding:12px 13px;border:1px solid color-mix(in srgb,var(--accent2) 45%,var(--line));border-radius:8px;background:color-mix(in srgb,var(--accent2) 7%,var(--panel2))}
      .fs-audio-progress.error{border-color:color-mix(in srgb,var(--bad) 55%,var(--line));background:color-mix(in srgb,var(--bad) 8%,var(--panel2))}
      .fs-audio-progress.complete{border-color:color-mix(in srgb,var(--accent) 55%,var(--line));background:color-mix(in srgb,var(--accent) 8%,var(--panel2))}
      .fs-audio-progress-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:5px}.fs-audio-progress-head b{font-size:12px}.fs-audio-progress-pct{font-size:14px;font-weight:850}
      .fs-audio-progress-stage{font-size:11px;color:var(--muted);margin-bottom:8px}.fs-audio-progress-bar{height:9px;background:var(--panel3);border-radius:999px;overflow:hidden}.fs-audio-progress-bar>span{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--accent2),var(--accent));border-radius:999px;transition:width .25s ease}
      .fs-audio-progress-meta{display:flex;gap:16px;flex-wrap:wrap;margin-top:7px;color:var(--muted);font-size:10px}
      .wrap.fs-content-light .fs-audio-manager-note{background:#f6f9fc!important;border-color:#d7e3ec!important;color:#526b7e!important}
      .wrap.fs-content-light .fs-audio-kind{background:#f6f9fc!important;border-color:#d7e3ec!important}.wrap.fs-content-light .fs-audio-row.removable:hover td{background:#eef6ff!important}
      .wrap.fs-content-light .fs-audio-progress{background:#eef6ff!important}.wrap.fs-content-light .fs-audio-progress-bar{background:#d9e5ee!important}
    `;document.head.appendChild(s);
  }

  function featureLabel(feature){
    if(feature==='profanity_censoring')return 'Profanity Censoring';
    if(feature==='dialogue_enhancement')return 'Dialogue Enhancement';
    return 'Censorarr';
  }

  function audioSection(){
    const root=q('#mediaDetail');if(!root)return null;
    let section=qa('.section',root).find(x=>q('h3',x)?.textContent?.trim()==='Audio tracks');
    if(section)return section;
    section=document.createElement('div');section.className='section';section.innerHTML='<h3>Audio tracks</h3>';
    const movieFile=qa('.section',root).find(x=>q('h3',x)?.textContent?.trim()==='Movie file');
    if(movieFile)movieFile.insertAdjacentElement('afterend',section);else root.appendChild(section);
    return section;
  }

  async function renderTracks(path){
    const section=audioSection();if(!section||!path)return;
    section.innerHTML='<h3>Audio tracks</h3><div class="fs-audio-loading">Inspecting audio streams…</div>';
    try{
      const data=await request('/api/audio-tracks?path='+encodeURIComponent(path));
      const rows=data.audio||[];
      section.innerHTML=`<h3>Audio tracks</h3>
        <div class="fs-audio-manager-note"><span class="fs-audio-lock">🔒</span><div><b>Original and pre-existing audio is permanently protected.</b><br>Censorarr only enables Remove for tracks it can verify that Censorarr created. Removing one of those tracks is a stream-copy remux; video and protected audio are not re-encoded. Automation remembers the removal and will not recreate that feature until you manually Process/Reprocess this movie.</div></div>
        <div class="table-wrap"><table class="fs-audio-table"><thead><tr><th>Track</th><th>Codec</th><th>Channels</th><th>Language</th><th>Type</th><th>Default</th><th></th></tr></thead><tbody>
        ${rows.map(a=>`<tr class="fs-audio-row ${a.removable?'removable':''}" data-stream="${Number(a.stream_index)}">
          <td><div class="fs-audio-title">${esc(a.title||`Audio ${Number(a.relative_index)+1}`)}</div><div class="fs-audio-sub">Stream ${Number(a.relative_index)+1}${a.channel_layout?` · ${esc(a.channel_layout)}`:''}</div></td>
          <td>${esc(String(a.codec||'').toUpperCase()||'—')}</td><td>${esc(a.channels??'—')}</td><td>${esc(a.language||'—')}</td>
          <td>${a.removable?`<span class="fs-audio-kind generated">● Censorarr · ${esc(featureLabel(a.feature))}</span>`:`<span class="fs-audio-kind protected">🔒 Original / pre-existing</span>`}</td>
          <td>${a.default?'Yes':'—'}</td>
          <td>${a.removable?`<button class="small danger fs-audio-remove" data-stream="${Number(a.stream_index)}">Remove</button>`:`<button class="small fs-audio-remove" disabled title="Original/pre-existing tracks cannot be removed">Protected</button>`}</td>
        </tr>`).join('')||'<tr><td colspan="7" class="muted">No audio streams found.</td></tr>'}
        </tbody></table></div>`;
      qa('.fs-audio-remove:not([disabled])',section).forEach(btn=>btn.addEventListener('click',e=>{e.stopPropagation();removeTrack(path,Number(btn.dataset.stream),btn)}));
      qa('.fs-audio-row.removable',section).forEach(row=>row.addEventListener('click',e=>{if(e.target.closest('button'))return;removeTrack(path,Number(row.dataset.stream),q('.fs-audio-remove',row))}));
    }catch(e){section.innerHTML=`<h3>Audio tracks</h3><div class="warning">Could not inspect protected audio tracks: ${esc(e.message)}</div>`}
  }

  function showProgress(title){
    const section=audioSection();if(!section)return null;
    q('.fs-audio-progress',section)?.remove();
    const box=document.createElement('div');box.className='fs-audio-progress';
    box.innerHTML=`<div class="fs-audio-progress-head"><b>Removing ${esc(title)}</b><span class="fs-audio-progress-pct">0%</span></div>
      <div class="fs-audio-progress-stage">Preparing safe stream-copy remux…</div>
      <div class="fs-audio-progress-bar"><span></span></div>
      <div class="fs-audio-progress-meta"><span data-elapsed>Elapsed 0s</span><span data-eta>ETA calculating…</span><span>Original audio protected</span></div>`;
    const note=q('.fs-audio-manager-note',section);if(note)note.insertAdjacentElement('afterend',box);else section.insertBefore(box,section.children[1]||null);
    return box;
  }

  function paintProgress(box,job){
    if(!box)return;
    const pct=Math.max(0,Math.min(100,Number(job.progress)||0));
    q('.fs-audio-progress-pct',box).textContent=`${pct.toFixed(pct<10&&pct%1?1:0)}%`;
    q('.fs-audio-progress-stage',box).textContent=job.stage||'Working…';
    q('.fs-audio-progress-bar>span',box).style.width=`${pct}%`;
    q('[data-elapsed]',box).textContent=`Elapsed ${fmtTime(job.elapsed_seconds)}`;
    q('[data-eta]',box).textContent=job.eta_seconds!=null&&job.status==='running'?`ETA ~${fmtTime(job.eta_seconds)}`:(job.status==='complete'?'Finished':'ETA calculating…');
    box.classList.toggle('error',job.status==='error');
    box.classList.toggle('complete',job.status==='complete');
  }

  async function monitorRemoval(path,title,jobId,button){
    const box=showProgress(title);
    while(true){
      let payload;
      try{payload=await request('/api/audio-tracks/remove-job/'+encodeURIComponent(jobId))}
      catch(e){
        if(box){box.classList.add('error');q('.fs-audio-progress-stage',box).textContent='Could not read removal progress: '+e.message}
        if(button){button.disabled=false;button.textContent='Remove'}
        return;
      }
      const job=payload.job||{};paintProgress(box,job);
      if(job.status==='complete'){
        if(box){q('.fs-audio-progress-stage',box).textContent=job.message||'Audio track removed safely.'}
        await wait(700);
        await renderTracks(path);
        return;
      }
      if(job.status==='error'){
        const msg=job.error||'Audio-track removal failed.';
        if(box)q('.fs-audio-progress-stage',box).textContent=msg;
        if(button){button.disabled=false;button.textContent='Remove'}
        alert(`Could not remove ${title}:\n\n${msg}`);
        return;
      }
      await wait(500);
    }
  }

  async function removeTrack(path,streamIndex,button){
    const section=audioSection();
    const row=section&&q(`.fs-audio-row[data-stream="${streamIndex}"]`,section);
    const title=q('.fs-audio-title',row)?.textContent?.trim()||'this Censorarr audio track';
    const ok=confirm(`Remove ${title}?\n\nOnly this Censorarr-created audio stream will be removed. Original/pre-existing audio, video, subtitles and chapters are protected.\n\nCensorarr will remember this removal and automation will NOT recreate the track unless you manually Process/Reprocess this movie.`);
    if(!ok)return;
    qa('.fs-audio-remove:not([disabled])',section).forEach(x=>x.disabled=true);
    if(button)button.textContent='Starting…';
    try{
      const result=await request('/api/audio-tracks/remove-job',{method:'POST',body:JSON.stringify({path,stream_index:streamIndex})});
      if(button)button.textContent='Removing…';
      await monitorRemoval(path,title,result.job_id,button);
    }catch(e){
      alert(`Could not remove ${title}:\n\n${e.message}`);
      qa('.fs-audio-row.removable .fs-audio-remove',section).forEach(x=>{x.disabled=false;x.textContent='Remove'});
    }
  }

  function hookMovieDetail(){
    const old=window.renderMovieDetailPage;
    if(typeof old!=='function'||old.__fsAudioTrackManager)return false;
    const wrapped=function(d){
      const out=old.apply(this,arguments);
      if(d?.media_path)setTimeout(()=>renderTracks(d.media_path),0);
      return out;
    };
    wrapped.__fsAudioTrackManager=true;window.renderMovieDetailPage=wrapped;return true;
  }

  function hookManualProcess(){
    const old=window.reprocess;
    if(typeof old!=='function'||old.__fsSuppressionAware)return false;
    const wrapped=async function(path){
      if(!confirm('Force reprocess '+String(path||'').replace(/\\/g,'/').split('/').pop()+'? Existing Censorarr tracks will be replaced, not duplicated.\n\nAny audio feature you previously removed manually will be allowed to run again for this movie.'))return;
      try{
        await request('/api/audio-tracks/unsuppress',{method:'POST',body:JSON.stringify({path})});
        const result=await request('/api/process',{method:'POST',body:JSON.stringify({path})});
        if(typeof window.refreshQueueMini==='function')await window.refreshQueueMini();
        if(typeof window.refresh==='function')window.refresh();
        return result;
      }catch(e){
        alert('Could not process '+String(path||'').replace(/\\/g,'/').split('/').pop()+':\n\n'+(e?.message||String(e)));
        throw e;
      }
    };
    wrapped.__fsSuppressionAware=true;window.reprocess=wrapped;return true;
  }

  function boot(){
    styles();
    let tries=0;const timer=setInterval(()=>{tries++;const a=hookMovieDetail(),b=hookManualProcess();if((a||window.renderMovieDetailPage?.__fsAudioTrackManager)&&(b||window.reprocess?.__fsSuppressionAware)||tries>30)clearInterval(timer)},120);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot);else boot();
})();
