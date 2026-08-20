(() => {
  if (window.__censorarrWizardGuideImages) return;
  window.__censorarrWizardGuideImages = true;

  const q=(s,r=document)=>r.querySelector(s), qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const GUIDES={
    plex:{src:'/assets/guide-plex.svg',caption:'Plex: open the item menu → Get Info → View XML → copy only the X-Plex-Token value from the browser URL. Example token is fake.'},
    radarr:{src:'/assets/guide-radarr.svg',caption:'Radarr Settings → General → Security. The API key shown in this guide is a fake example.'},
    sonarr:{src:'/assets/guide-sonarr.svg',caption:'Sonarr Settings → General → Security. The API key shown in this guide is a fake example.'},
    bazarr:{src:'/assets/guide-bazarr.svg',caption:'Bazarr Settings → General. The API key shown in this guide is a fake example.'},
  };

  function kindFor(details){
    const text=(q('summary',details)?.textContent||'').toLowerCase();
    if(text.includes('plex'))return 'plex';
    if(text.includes('radarr'))return 'radarr';
    if(text.includes('sonarr'))return 'sonarr';
    if(text.includes('bazarr'))return 'bazarr';
    return '';
  }

  function enrich(root=document){
    qa('.fsw-guide',root).forEach(details=>{
      if(details.dataset.guideImage==='1')return;
      const kind=kindFor(details),guide=GUIDES[kind];if(!guide)return;
      details.dataset.guideImage='1';
      const wrap=document.createElement('div');wrap.className='fsw-shot-grid';
      wrap.innerHTML=`<div class="fsw-shot"><img src="${guide.src}" alt="${kind} setup guide"><small>${guide.caption}</small></div>`;
      details.appendChild(wrap);
    });
  }

  function boot(){
    enrich();
    new MutationObserver(muts=>{
      for(const m of muts)for(const node of m.addedNodes)if(node instanceof Element){
        if(node.matches?.('.fsw-guide'))enrich(node.parentElement||document);else if(node.querySelector?.('.fsw-guide'))enrich(node);
      }
    }).observe(document.body,{childList:true,subtree:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();