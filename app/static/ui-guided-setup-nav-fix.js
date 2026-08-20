(() => {
  /* The legacy wizard stores WIZARD_STEP as a global lexical binding (let), not a
     window property. The guided layer boots shortly after DOMContentLoaded, so apply
     this bridge after that boot has finished and make first-run auto-open safe too. */
  if (window.__fsGuidedWizardLexicalFixScheduled) return;
  window.__fsGuidedWizardLexicalFixScheduled = true;

  const q=(s,r=document)=>r.querySelector(s);
  const $=id=>document.getElementById(id);
  const selected=(name,fallback='')=>q(`input[name="${name}"]:checked`)?.value||fallback;
  const setRadio=(name,value)=>{const x=q(`input[name="${name}"][value="${value}"]`);if(x)x.checked=true};

  function seedIfNeeded(){
    if(!q('input[name="fsGoal"]')||q('input[name="fsGoal"]:checked'))return;
    const prof=q('.fsProfanityToggle')?.checked!==false;
    const dial=!!q('.fsDialogueToggle')?.checked;
    setRadio('fsGoal',prof&&dial?'both':dial?'dialogue':'clean');
    setRadio('fsLibraries',$('wTvEnabled')?.value==='true'?'both':'movies');
    setRadio('fsPlex',$('wPlexEnabled')?.value==='true'?'yes':'no');
    setRadio('fsRadarr',$('wRadEnabled')?.value==='true'?'yes':'no');
    setRadio('fsSonarr',$('wSonEnabled')?.value==='true'?'yes':'no');
    setRadio('fsBazarr',$('wBazEnabled')?.value==='true'?'yes':'no');
    setRadio('fsGpu',$('wAsrBackend')?.value==='local'?'no':'yes');
    setRadio('fsExisting',$('wProcessExisting')?.value==='false'?'no':'yes');
    setRadio('fsRatings',($('wMovieRatingEnabled')?.value==='true'||$('wTvRatingEnabled')?.value==='true')?'family':'all');
    setRadio('fsPausePlex',$('wPlexPause')?.value==='true'?'yes':'no');
    q('input[name="fsGoal"]')?.dispatchEvent(new Event('change',{bubbles:true}));
  }

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

  function applyFix(){
    if(window.__fsGuidedWizardLexicalFix)return;
    window.__fsGuidedWizardLexicalFix=true;
    seedIfNeeded();

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

    if($('setupModal')?.classList.contains('open'))window.wizardRender?.();
  }

  setTimeout(applyFix,1400);
})();
