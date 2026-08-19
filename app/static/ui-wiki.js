(() => {
  const q=(s,r=document)=>r.querySelector(s),qa=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let wikiPages=[],currentSlug='Home',pageCache=new Map();

  function addStyles(){
    if(q('#fsWikiStyles'))return;
    const s=document.createElement('style');s.id='fsWikiStyles';s.textContent=`
      .fs-wiki-shell{display:grid;grid-template-columns:285px minmax(0,1fr);gap:14px;min-height:700px}
      .fs-wiki-nav,.fs-wiki-article{background:var(--panel);border:1px solid var(--line);border-radius:9px;color:var(--text)}
      .fs-wiki-nav{padding:14px;align-self:start;position:sticky;top:86px;max-height:calc(100vh - 105px);overflow:auto;scrollbar-width:thin}
      .fs-wiki-brand{display:flex;align-items:center;gap:10px;margin-bottom:12px}.fs-wiki-brand img{width:35px;height:35px}.fs-wiki-brand h2{margin:0;font-size:18px}.fs-wiki-brand span{display:block;color:var(--muted);font-size:11px}
      .fs-wiki-search{width:100%;min-width:0!important;margin-bottom:10px}
      .fs-wiki-list{display:grid;gap:2px}.fs-wiki-item{width:100%;border:0!important;background:transparent!important;display:grid!important;grid-template-columns:26px minmax(0,1fr)!important;gap:8px!important;align-items:center!important;text-align:left!important;padding:9px!important;border-radius:6px!important;color:var(--text)!important}
      .fs-wiki-item:hover{background:var(--panel2)!important}.fs-wiki-item.active{background:color-mix(in srgb,var(--accent2) 16%,var(--panel2))!important;box-shadow:inset 3px 0 0 var(--accent2)}.fs-wiki-item b{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fs-wiki-item span:first-child{color:var(--accent2);text-align:center}
      .fs-wiki-article{padding:27px 32px;line-height:1.65;min-width:0}.fs-wiki-article h1{font-size:30px;margin:0 0 8px;line-height:1.2}.fs-wiki-article h2{font-size:21px;margin:30px 0 10px;border-bottom:1px solid var(--line);padding-bottom:7px}.fs-wiki-article h3{font-size:16px;margin:23px 0 7px}.fs-wiki-article h4{font-size:14px;margin:19px 0 6px}.fs-wiki-article p{max-width:980px;margin:8px 0 13px}.fs-wiki-article ul,.fs-wiki-article ol{padding-left:25px;max-width:980px}.fs-wiki-article li{margin:4px 0}.fs-wiki-article a{color:var(--accent2);text-decoration:none}.fs-wiki-article a:hover{text-decoration:underline}.fs-wiki-article code{background:var(--panel3);border:1px solid var(--line);padding:1px 5px;border-radius:4px;font:12px ui-monospace,SFMono-Regular,Consolas,monospace}.fs-wiki-article pre{background:#071018;color:#d9e8f2;border:1px solid #203548;border-radius:7px;padding:13px;overflow:auto;max-width:100%}.fs-wiki-article pre code{background:transparent;border:0;padding:0;color:inherit}.fs-wiki-article blockquote{margin:14px 0;padding:10px 14px;border-left:3px solid var(--accent2);background:color-mix(in srgb,var(--accent2) 7%,var(--panel2));color:var(--muted)}
      .fs-wiki-table{overflow:auto;border:1px solid var(--line);border-radius:7px;margin:13px 0 18px}.fs-wiki-table table{width:100%;border-collapse:collapse}.fs-wiki-table th,.fs-wiki-table td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}.fs-wiki-table th{background:var(--panel2);color:var(--text);font-size:12px;text-transform:none;letter-spacing:0;position:static}.fs-wiki-table tr:last-child td{border-bottom:0}
      .fs-wiki-article img{display:block;max-width:100%;height:auto;border-radius:8px;border:1px solid var(--line);margin:14px 0 20px;box-shadow:0 8px 30px rgba(0,0,0,.15)}.fs-wiki-loading{padding:50px;text-align:center;color:var(--muted)}.fs-wiki-error{padding:15px;border:1px solid color-mix(in srgb,var(--bad) 45%,var(--line));background:color-mix(in srgb,var(--bad) 8%,var(--panel));border-radius:7px;color:var(--bad)}
      .fs-wiki-source{display:flex;align-items:center;gap:8px;margin-top:28px;padding-top:14px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}
      @media(max-width:900px){.fs-wiki-shell{grid-template-columns:1fr}.fs-wiki-nav{position:static;max-height:none}.fs-wiki-list{grid-template-columns:repeat(2,minmax(0,1fr))}.fs-wiki-article{padding:20px}}
    `;document.head.appendChild(s);
  }

  function iconFor(slug){
    const s=String(slug).toLowerCase();
    if(s==='home')return'⌂';if(s.includes('quick'))return'⚡';if(s.includes('install')||s.includes('docker')||s.includes('synology'))return'⇩';if(s.includes('setup'))return'✦';if(s.includes('media-folder'))return'▦';if(s.includes('transcription')||s.includes('gpu'))return'⚙';if(s.includes('profanity'))return'◇';if(s.includes('plex'))return'▶';if(s.includes('radarr')||s.includes('sonarr'))return'◉';if(s.includes('bazarr')||s.includes('subtitle'))return'CC';if(s.includes('notification')||s.includes('schedule'))return'◷';if(s.includes('security'))return'♢';if(s.includes('trouble'))return'?';if(s.includes('config'))return'☷';if(s.includes('update'))return'↻';return'•';
  }

  function titleFromSlug(slug){return String(slug||'').replaceAll('-',' ');}
  function showOnlyPane(id){qa('.pane').forEach(p=>p.classList.remove('active'));q('#'+id)?.classList.add('active');}

  function ensurePane(){
    let pane=q('#helpPane');
    if(!pane){pane=document.createElement('section');pane.id='helpPane';pane.className='pane';q('.wrap')?.appendChild(pane);}
    if(pane.dataset.fullWiki==='1')return pane;
    pane.dataset.fullWiki='1';
    pane.innerHTML=`<div class="fs-wiki-shell"><aside class="fs-wiki-nav"><div class="fs-wiki-brand"><img src="/assets/censorarr-favicon-wave.svg?v=7"><div><h2>Censorarr Wiki</h2><span>Full documentation inside Censorarr</span></div></div><input id="fsWikiSearch" class="fs-wiki-search" placeholder="Search wiki pages…"><div id="fsWikiList" class="fs-wiki-list"><div class="fs-wiki-loading">Loading pages…</div></div></aside><article id="fsWikiArticle" class="fs-wiki-article"><div class="fs-wiki-loading">Loading documentation…</div></article></div>`;
    q('#fsWikiSearch').addEventListener('input',renderPageList);
    return pane;
  }

  async function loadIndex(force=false){
    if(wikiPages.length&&!force)return wikiPages;
    const r=await fetch('/api/help/wiki'+(force?'?force=true':''),{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw new Error(`Wiki index HTTP ${r.status}`);
    const data=await r.json();wikiPages=data.pages||[];renderPageList();return wikiPages;
  }

  function renderPageList(){
    const box=q('#fsWikiList');if(!box)return;
    const search=(q('#fsWikiSearch')?.value||'').trim().toLowerCase();
    const pages=wikiPages.filter(p=>!search||String(p.title||p.slug).toLowerCase().includes(search)||String(p.slug).toLowerCase().includes(search));
    box.innerHTML=pages.length?pages.map(p=>`<button class="fs-wiki-item ${p.slug===currentSlug?'active':''}" data-wiki-slug="${esc(p.slug)}"><span>${iconFor(p.slug)}</span><b title="${esc(p.title||titleFromSlug(p.slug))}">${esc(p.title||titleFromSlug(p.slug))}</b></button>`).join(''):'<div class="fs-wiki-loading">No matching pages.</div>';
    qa('[data-wiki-slug]',box).forEach(b=>b.onclick=()=>loadPage(b.dataset.wikiSlug));
  }

  function inlineMd(raw){
    let s=esc(raw);
    const stash=[];
    s=s.replace(/`([^`]+)`/g,(_,x)=>{const k=`@@CODE${stash.length}@@`;stash.push(`<code>${x}</code>`);return k;});
    s=s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g,(_,alt,url)=>`<img src="${url}" alt="${alt}" loading="lazy">`);
    s=s.replace(/\[([^\]]+)\]\(([^)]+)\)/g,(_,label,target)=>{
      let t=target.replaceAll('&amp;','&').trim();
      const md=t.match(/(?:^|\/)([A-Za-z0-9_-]+)\.md(?:#.*)?$/);const gh=t.match(/github\.com\/leestow\/Censorarr\/wiki\/([A-Za-z0-9_-]+)/i);
      if(md||gh){const slug=(md?.[1]||gh?.[1]);return `<a href="#" data-wiki-link="${esc(slug)}">${label}</a>`;}
      return `<a href="${esc(t)}" ${/^https?:/i.test(t)?'target="_blank" rel="noopener"':''}>${label}</a>`;
    });
    s=s.replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/__([^_]+)__/g,'<strong>$1</strong>');
    s=s.replace(/(^|[^*])\*([^*]+)\*/g,'$1<em>$2</em>').replace(/(^|[^_])_([^_]+)_/g,'$1<em>$2</em>');
    stash.forEach((v,i)=>{s=s.replace(`@@CODE${i}@@`,v);});return s;
  }

  function isTableDivider(line){return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);}
  function cells(line){return line.trim().replace(/^\||\|$/g,'').split('|').map(x=>x.trim());}

  function markdown(md){
    const lines=String(md||'').replace(/\r/g,'').split('\n');let out='',i=0;
    while(i<lines.length){let line=lines[i];
      if(/^```/.test(line.trim())){const lang=line.trim().slice(3).trim();i++;const code=[];while(i<lines.length&&!/^```/.test(lines[i].trim()))code.push(lines[i++]);if(i<lines.length)i++;out+=`<pre><code${lang?` data-language="${esc(lang)}"`:''}>${esc(code.join('\n'))}</code></pre>`;continue;}
      if(!line.trim()){i++;continue;}
      const h=line.match(/^(#{1,4})\s+(.+)$/);if(h){const n=h[1].length;out+=`<h${n}>${inlineMd(h[2])}</h${n}>`;i++;continue;}
      if(/^\s*(---+|___+|\*\*\*+)\s*$/.test(line)){out+='<hr>';i++;continue;}
      if(i+1<lines.length&&line.includes('|')&&isTableDivider(lines[i+1])){const head=cells(line);i+=2;const rows=[];while(i<lines.length&&lines[i].trim()&&lines[i].includes('|'))rows.push(cells(lines[i++]));out+=`<div class="fs-wiki-table"><table><thead><tr>${head.map(x=>`<th>${inlineMd(x)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${head.map((_,j)=>`<td>${inlineMd(r[j]||'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;continue;}
      if(/^\s*>/.test(line)){const rows=[];while(i<lines.length&&/^\s*>/.test(lines[i]))rows.push(lines[i++].replace(/^\s*>\s?/,''));out+=`<blockquote>${rows.map(inlineMd).join('<br>')}</blockquote>`;continue;}
      if(/^\s*[-*+]\s+/.test(line)){const rows=[];while(i<lines.length&&/^\s*[-*+]\s+/.test(lines[i]))rows.push(lines[i++].replace(/^\s*[-*+]\s+/,''));out+=`<ul>${rows.map(x=>`<li>${inlineMd(x)}</li>`).join('')}</ul>`;continue;}
      if(/^\s*\d+[.)]\s+/.test(line)){const rows=[];while(i<lines.length&&/^\s*\d+[.)]\s+/.test(lines[i]))rows.push(lines[i++].replace(/^\s*\d+[.)]\s+/,''));out+=`<ol>${rows.map(x=>`<li>${inlineMd(x)}</li>`).join('')}</ol>`;continue;}
      const para=[line];i++;while(i<lines.length&&lines[i].trim()&&!/^(#{1,4})\s+/.test(lines[i])&&!/^```/.test(lines[i].trim())&&!/^\s*[-*+]\s+/.test(lines[i])&&!/^\s*\d+[.)]\s+/.test(lines[i])&&!/^\s*>/.test(lines[i])&&!(i+1<lines.length&&lines[i].includes('|')&&isTableDivider(lines[i+1])))para.push(lines[i++]);out+=`<p>${inlineMd(para.join(' '))}</p>`;
    }
    return out;
  }

  async function loadPage(slug){
    currentSlug=slug||'Home';renderPageList();const article=q('#fsWikiArticle');if(!article)return;
    article.innerHTML='<div class="fs-wiki-loading">Loading documentation…</div>';
    try{
      let data=pageCache.get(currentSlug);
      if(!data){const r=await fetch('/api/help/wiki/'+encodeURIComponent(currentSlug),{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw new Error(`Wiki page HTTP ${r.status}`);data=await r.json();pageCache.set(currentSlug,data);}
      article.innerHTML=markdown(data.markdown||'')+`<div class="fs-wiki-source"><span>Documentation source:</span><b>${esc(data.title||currentSlug)}</b>${data.cached?'<span>· cached copy</span>':''}</div>`;
      qa('[data-wiki-link]',article).forEach(a=>a.onclick=e=>{e.preventDefault();loadPage(a.dataset.wikiLink);});
      article.scrollTop=0;renderPageList();
    }catch(err){article.innerHTML=`<div class="fs-wiki-error"><b>Could not load this Wiki page.</b><br>${esc(err.message||err)}</div>`;}
  }

  async function showWiki(slug='Home'){
    ensurePane();showOnlyPane('helpPane');qa('.side-nav .nav-item').forEach(x=>x.classList.remove('active'));
    const title=q('#pageTitle'),sub=q('#pageSubtitle');if(title)title.textContent='Help & Wiki';if(sub)sub.textContent='Full Censorarr documentation, displayed inside the app';
    try{await loadIndex();await loadPage(slug);}catch(err){q('#fsWikiArticle').innerHTML=`<div class="fs-wiki-error"><b>Wiki unavailable.</b><br>${esc(err.message||err)}</div>`;}
  }
  window.CensorarrShowWiki=showWiki;

  function wire(){
    addStyles();ensurePane();
    const help=q('#fsHelpBtn');if(help)help.onclick=e=>{e.preventDefault();showWiki('Home');};
  }

  function boot(){wire();setTimeout(wire,900);setTimeout(wire,1800);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(boot,450));else setTimeout(boot,450);
})();
