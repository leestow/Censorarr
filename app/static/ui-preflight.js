(() => {
  // ui-polish decorates the integration cards after the legacy dashboard renders them.
  // Its first implementation observed the card subtree and then rewrote that same subtree,
  // which could recursively trigger itself and peg the browser main thread. Keep normal
  // MutationObserver behavior everywhere else, but suppress that one self-observing target.
  if (window.__censorarrSafeMutationObserver || !window.MutationObserver) return;
  const NativeMutationObserver = window.MutationObserver;

  function SafeMutationObserver(callback) {
    const observer = new NativeMutationObserver(callback);
    const nativeObserve = observer.observe.bind(observer);
    observer.observe = function(target, options) {
      if (target && target.id === 'fsIntegrations') return;
      return nativeObserve(target, options);
    };
    return observer;
  }

  SafeMutationObserver.prototype = NativeMutationObserver.prototype;
  window.MutationObserver = SafeMutationObserver;
  window.__censorarrSafeMutationObserver = true;
})();

/* Wiki + General Settings organization pass. Kept in the preflight bundle so it runs
   after every source-only Synology update without requiring a separate asset route. */
(() => {
  const q=(s,r=document)=>r.querySelector(s), qa=(s,r=document)=>[...r.querySelectorAll(s)];

  function addStyles(){
    if(q('#fsLayoutPolishStyles')) return;
    const style=document.createElement('style');
    style.id='fsLayoutPolishStyles';
    style.textContent=`
      .fs-wiki-shell{grid-template-columns:320px minmax(0,1fr)!important;gap:16px!important}
      .fs-wiki-nav{padding:16px!important}
      .fs-wiki-brand{padding:0 2px 12px;margin-bottom:10px!important;border-bottom:1px solid var(--line)}
      .fs-wiki-search{margin:0 0 14px!important;height:40px}
      .fs-wiki-list{display:block!important}
      .fs-wiki-group{margin:0 0 15px}.fs-wiki-group:last-child{margin-bottom:0}
      .fs-wiki-group-title{padding:0 9px 6px;color:var(--muted);font-size:10px;font-weight:900;letter-spacing:.09em;text-transform:uppercase}
      .fs-wiki-group-items{display:grid;gap:2px}
      .fs-wiki-item{grid-template-columns:24px minmax(0,1fr)!important;gap:9px!important;padding:8px 10px!important;min-height:36px;border-radius:7px!important}
      .fs-wiki-item b{font-size:12px!important;font-weight:700!important;line-height:1.25}
      .fs-wiki-item span:first-child{font-size:13px;display:flex;align-items:center;justify-content:center;width:24px;min-width:24px}
      .fs-wiki-item.active{box-shadow:inset 3px 0 0 var(--accent2)!important}
      .fs-wiki-plumbing{display:none!important}

      .settings-page[data-settings="general"]{max-width:1320px!important;width:100%!important}
      .settings-page[data-settings="general"]>.section{margin-bottom:14px!important}
      .settings-page[data-settings="general"] [data-feature-panel]{margin-bottom:14px!important}
      .settings-page[data-settings="general"] .fs-source-rules,
      .settings-page[data-settings="general"] .fs-ai-dialogue-rules{max-width:none!important;margin-top:14px!important;padding:17px 18px!important;border-radius:10px!important;background:var(--panel)!important;border:1px solid var(--line)!important;box-shadow:none!important}
      .settings-page[data-settings="general"] .fs-source-rules-head,
      .settings-page[data-settings="general"] .fs-ai-dialogue-head{align-items:center!important;margin-bottom:14px!important;padding-bottom:11px;border-bottom:1px solid var(--line)}
      .settings-page[data-settings="general"] .fs-source-rules-head h3,
      .settings-page[data-settings="general"] .fs-ai-dialogue-head h3{font-size:16px!important;letter-spacing:0}
      .settings-page[data-settings="general"] .fs-source-rules-head p,
      .settings-page[data-settings="general"] .fs-ai-dialogue-head p{max-width:900px!important;font-size:11px!important;line-height:1.45}
      .settings-page[data-settings="general"] .fs-source-rules-grid,
      .settings-page[data-settings="general"] .fs-ai-dialogue-grid{gap:0!important;grid-template-columns:repeat(3,minmax(0,1fr))!important}
      .settings-page[data-settings="general"] .fs-source-rule,
      .settings-page[data-settings="general"] .fs-ai-rule{min-width:0;padding:2px 16px 5px!important;background:transparent!important;border:0!important;border-radius:0!important}
      .settings-page[data-settings="general"] .fs-source-rule:first-child,
      .settings-page[data-settings="general"] .fs-ai-rule:first-child{padding-left:0!important}
      .settings-page[data-settings="general"] .fs-source-rule+.fs-source-rule,
      .settings-page[data-settings="general"] .fs-ai-rule+.fs-ai-rule{border-left:1px solid var(--line)!important}
      .settings-page[data-settings="general"] .fs-source-rule label,
      .settings-page[data-settings="general"] .fs-ai-rule label{font-size:11px!important;margin-bottom:6px!important}
      .settings-page[data-settings="general"] .fs-source-rule small,
      .settings-page[data-settings="general"] .fs-ai-rule small{font-size:10px!important;line-height:1.4!important;margin-top:6px!important}
      .settings-page[data-settings="general"] .fs-ai-dialogue-grid+.fs-ai-dialogue-grid{margin-top:14px!important;padding-top:14px;border-top:1px solid var(--line)}
      .settings-page[data-settings="general"] .fs-ai-dialogue-grid+.fs-ai-dialogue-grid:before{content:'Behavior & fallback';grid-column:1/-1;color:var(--muted);font-size:10px;font-weight:900;letter-spacing:.08em;text-transform:uppercase;margin:0 0 10px}
      .settings-page[data-settings="general"] .fs-source-preview,
      .settings-page[data-settings="general"] .fs-ai-preview{margin-top:13px!important;padding:9px 11px!important;border-radius:6px;border-left-width:2px!important;font-size:10px!important}
      .settings-page[data-settings="general"] .fs-source-save,
      .settings-page[data-settings="general"] .fs-ai-worker{white-space:normal!important;text-align:right;max-width:340px;line-height:1.35}
      .settings-page[data-settings="general"] select{min-height:38px}
      @media(max-width:1050px){
        .fs-wiki-shell{grid-template-columns:285px minmax(0,1fr)!important}
        .settings-page[data-settings="general"] .fs-source-rules-grid,.settings-page[data-settings="general"] .fs-ai-dialogue-grid{grid-template-columns:1fr!important}
        .settings-page[data-settings="general"] .fs-source-rule,.settings-page[data-settings="general"] .fs-ai-rule{padding:12px 0!important;border-left:0!important;border-top:1px solid var(--line)!important}
        .settings-page[data-settings="general"] .fs-source-rule:first-child,.settings-page[data-settings="general"] .fs-ai-rule:first-child{border-top:0!important;padding-top:2px!important}
      }
      @media(max-width:900px){.fs-wiki-shell{grid-template-columns:1fr!important}.fs-wiki-nav{position:static!important;max-height:none!important}}
    `;
    document.head.appendChild(style);
  }

  const GROUPS=[
    ['Start Here',s=>/^(home|quick-start|setup-wizard)$/i.test(s)],
    ['Installation',s=>/(install|docker|linux|synology|windows|media-folder|permission)/i.test(s)],
    ['Media & Integrations',s=>/(plex|radarr|sonarr|bazarr|subtitle|transcription|gpu)/i.test(s)],
    ['Processing & Safety',s=>/(profanity|detect|clean-audio|review|config)/i.test(s)],
    ['Operations',s=>/(schedul|notification|security|secret|trouble|update|backup|log)/i.test(s)],
  ];

  function organizeWiki(){
    const box=q('#fsWikiList');
    if(!box||box.dataset.fsGrouped==='1')return;
    const buttons=qa('.fs-wiki-item[data-wiki-slug]',box);if(!buttons.length)return;
    const usable=[];
    for(const b of buttons){
      const slug=String(b.dataset.wikiSlug||'');
      if(/^_/.test(slug)||/^_?sidebar$/i.test(slug)||/^_?footer$/i.test(slug)){b.classList.add('fs-wiki-plumbing');continue}
      usable.push(b);
    }
    const frag=document.createDocumentFragment(),assigned=new Set();
    for(const [title,test] of GROUPS){
      const items=usable.filter(b=>!assigned.has(b)&&test(String(b.dataset.wikiSlug||'')));if(!items.length)continue;
      const group=document.createElement('div');group.className='fs-wiki-group';
      const head=document.createElement('div');head.className='fs-wiki-group-title';head.textContent=title;
      const list=document.createElement('div');list.className='fs-wiki-group-items';items.forEach(b=>{assigned.add(b);list.appendChild(b)});
      group.append(head,list);frag.appendChild(group);
    }
    const other=usable.filter(b=>!assigned.has(b));
    if(other.length){
      const group=document.createElement('div');group.className='fs-wiki-group';
      const head=document.createElement('div');head.className='fs-wiki-group-title';head.textContent='More Help';
      const list=document.createElement('div');list.className='fs-wiki-group-items';other.forEach(b=>list.appendChild(b));group.append(head,list);frag.appendChild(group);
    }
    box.innerHTML='';box.appendChild(frag);box.dataset.fsGrouped='1';
  }

  function polishGeneral(){const page=q('.settings-page[data-settings="general"]');if(page)page.classList.add('fs-general-polished')}
  function apply(){addStyles();const box=q('#fsWikiList');if(box&&box.dataset.fsGrouped!=='1')organizeWiki();polishGeneral()}

  const observer=new MutationObserver(muts=>{
    let wiki=false,general=false;
    for(const m of muts){const t=m.target instanceof Element?m.target:m.target?.parentElement;if(t?.id==='fsWikiList'||t?.closest?.('#fsWikiList'))wiki=true;if(t?.closest?.('.settings-page[data-settings="general"]'))general=true}
    if(wiki){const box=q('#fsWikiList');if(box)box.dataset.fsGrouped='0';queueMicrotask(organizeWiki)}
    if(general)queueMicrotask(polishGeneral);
  });

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>{apply();observer.observe(document.body,{childList:true,subtree:true})},{once:true});
  else{apply();observer.observe(document.body,{childList:true,subtree:true})}
  setTimeout(apply,700);setTimeout(apply,1800);
})();
