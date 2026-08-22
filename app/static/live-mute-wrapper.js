(() => {
  function load(src){
    return new Promise((resolve,reject)=>{
      const s=document.createElement('script');
      s.src=src;
      s.async=false;
      s.onload=resolve;
      s.onerror=()=>reject(new Error(`Could not load ${src}`));
      document.head.appendChild(s);
    });
  }
  (async()=>{
    try{
      await load('/live-mute-base.js');
      await load('/live-mute-sim.js');
    }catch(err){
      console.error('Censorarr Live Mute UI loader failed',err);
    }
  })();
})();
