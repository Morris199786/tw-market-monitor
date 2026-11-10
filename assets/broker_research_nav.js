/* 券商研究中心分頁：獨立讀取，只使用既有資料，不修改任何資料或舊功能。 */
(()=>{'use strict';
  const section=document.getElementById('brokerResearch');
  const frame=document.getElementById('brokerResearchFrame');
  const status=document.getElementById('brokerResearchLoadStatus');
  if(!section||!frame||!status)return;
  let started=false;
  function loadOnce(){
    if(started||!section.classList.contains('active'))return;
    started=true;
    status.textContent='正在載入券商研究中心…';
    frame.addEventListener('load',()=>{status.textContent='資料由現有 JSON 唯讀載入；如有解析疑慮，請核對報告 PDF。';},{once:true});
    frame.src='./broker_research.html';
  }
  // 首次點入才載入：不增加其他分頁初始化時的網路負擔。
  const obs=new MutationObserver(loadOnce);
  obs.observe(section,{attributes:true,attributeFilter:['class']});
  loadOnce();
})();
