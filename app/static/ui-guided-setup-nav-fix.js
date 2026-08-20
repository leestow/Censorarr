(() => {
  /* The legacy wizard stores WIZARD_STEP as a global lexical binding (let), not a
     window property. The guided setup layer is intentionally kept separate from the
     legacy HTML, so bridge the real binding here after the guided layer loads. */
  if (window.__fsGuidedWizardLexicalFix) return;
  window.__fsGuidedWizardLexicalFix = true;

  const q=(s,r=document)=>r.querySelector(s);
  const $=id=>document.getElementById(id);
  const selected=(name,fallback='')=>q(`input[name="${name}"]:checked`)?.value||fallback;

  function steps(){
    const plex=selected('fsPlex',$('wPlexEnabled')?.value==='true'?'yes':'no')==='yes';
    const rad=selected('fsRadarr',$('wRadEnabled')?.value==='true'?'yes':'no')==='yes';
    const tv=selected('fsLibraries',$('wTvEnabled')?.value==='true'?'both':'movies')==='both';
    const son=tv&&selected('fsSonarr',$('wSonEnabled')?.value==='true'?'yes':'no')==='yes';
    const baz=selected('fsBazarr',$('wBazEnabled')?.value==='true'?'yes':'no')==='yes';
    const out=[0,1,2];
    if(plex)out.push(3);
    if(rad||son)out.push(4);
    if(baz)out.push(5);
    out.push(6);
    return out;
  }

  const guidedRender=window.wizardRender;
  if(typeof guidedRender==='function'){
    window.wizardRender=function(){
      window.WIZARD_STEP=WIZARD_STEP;
      const result=guidedRender();
      const active=steps();
      const idx=Math.max(0,active.indexOf(WIZARD_STEP));
      const label=$('wizardStepLabel');
      if(label)label.textContent=`Step ${idx+1} of ${active.length}`;
      const progress=$('wizardProgress');
      if(progress)progress.innerHTML=active.map((_,i)=>`<span class="${i<idx?'done':i===idx?'active':''}"></span>`).join('');
      return result;
    };
  }

  window.wizardNext=function(){
    const active=steps();
    let idx=active.indexOf(WIZARD_STEP);
    if(idx<0)idx=0;
    WIZARD_STEP=active[Math.min(active.length-1,idx+1)];
    window.WIZARD_STEP=WIZARD_STEP;
    window.wizardRender?.();
  };

  window.wizardBack=function(){
    const active=steps();
    let idx=active.indexOf(WIZARD_STEP);
    if(idx<0)idx=1;
    WIZARD_STEP=active[Math.max(0,idx-1)];
    window.WIZARD_STEP=WIZARD_STEP;
    window.wizardRender?.();
  };
})();
