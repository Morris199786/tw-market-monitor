/* 券商研究中心：首次進入才載入；不更動報告／財測。 */
(()=>{'use strict';
  const section=document.getElementById('brokerResearch');
  const frame=document.getElementById('brokerResearchFrame');
  const status=document.getElementById('brokerResearchLoadStatus');
  if(!section||!frame||!status)return;
  let started=false;
  function loadOnce(){
    if(started||!section.classList.contains('active'))return;
    started=true;
    status.hidden=true;status.textContent='';status.style.display='none';
    frame.addEventListener('load',()=>{
      status.textContent='';
      status.hidden=true;
      status.style.display='none';
    },{once:true});
    frame.src='./broker_research.html';
  }
  new MutationObserver(loadOnce).observe(section,{attributes:true,attributeFilter:['class']});
  loadOnce();
})();

/* iPhone / mobile: keep global overview and back-to-top buttons fixed
   to the actual viewport bottom, instead of recalculating an inline top
   coordinate on each visualViewport scroll.  Scoped to the two buttons. */
(()=>{'use strict';
  const ids=['backHomeBtn','toTop'];
  const mobile=()=>window.matchMedia('(max-width:900px)').matches;
  const observers=new Map();
  const targets={
    backHomeBtn:{top:'auto',bottom:'calc(16px + env(safe-area-inset-bottom, 0px))',left:'calc(16px + env(safe-area-inset-left, 0px))',right:'auto'},
    toTop:{top:'auto',bottom:'calc(16px + env(safe-area-inset-bottom, 0px))',left:'auto',right:'calc(16px + env(safe-area-inset-right, 0px))'}
  };
  function anchor(btn,id){
    if(!mobile())return;
    const style=btn.style;
    style.setProperty('position','fixed','important');
    for(const [prop,val] of Object.entries(targets[id])){
      if(style.getPropertyValue(prop)!==val||style.getPropertyPriority(prop)!=='important'){
        style.setProperty(prop,val,'important');
      }
    }
  }
  function attach(){
    for(const id of ids){
      const el=document.getElementById(id);
      const prior=observers.get(id);
      if(prior?.el===el)continue;
      prior?.observer.disconnect();
      observers.delete(id);
      if(!el)continue;
      const observer=new MutationObserver(()=>anchor(el,id));
      observer.observe(el,{attributes:true,attributeFilter:['style']});
      observers.set(id,{el,observer});
      anchor(el,id);
    }
  }
  new MutationObserver(attach).observe(document.body,{childList:true,subtree:false});
  window.addEventListener('resize',()=>{attach();for(const id of ids){const el=document.getElementById(id);if(el)anchor(el,id)}},{passive:true});
  attach();
})();
