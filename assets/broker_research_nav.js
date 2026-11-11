/* 券商研究中心：首次進入才載入；不更動報告／財測。 */
(()=>{'use strict';
  const section=document.getElementById('brokerResearch');
  const frame=document.getElementById('brokerResearchFrame');
  const status=document.getElementById('brokerResearchLoadStatus');
  if(!section||!frame||!status)return;
  let started=false;
  function loadOnce(){
    if(started||section.hidden || !document.getElementById('reports')?.classList.contains('active'))return;
    started=true;
    status.hidden=true;status.textContent='';status.style.display='none';
    frame.addEventListener('load',()=>{
      status.textContent='';
      status.hidden=true;
      status.style.display='none';
    },{once:true});
    frame.src='./broker_research.html';
  }
  new MutationObserver(loadOnce).observe(section,{attributes:true,attributeFilter:['hidden']});
  document.addEventListener('research-mode-change',loadOnce);
  new MutationObserver(loadOnce).observe(document.getElementById('reports'),{attributes:true,attributeFilter:['class']});
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

/* 券商研究中心視覺化精簡增強 v1
 * 不替換既有報告、券商財測與圖表；僅在同源 iframe 中加入可選的分析視圖。
 * 預設保留原有長條圖及原始報告連結。
 */
(()=>{'use strict';
  const frame=document.getElementById('brokerResearchFrame');
  if(!frame)return;
  const COLORS={point:'#297bbd',guide:'#b8c4d1',median:'#c98a23',positive:'#c34c5a',negative:'#27866d',ink:'#344154'};
  const numberFrom=text=>{
    const s=String(text||'').replace(/[，,\s]/g,'');
    const m=s.match(/[-+]?\d+(?:\.\d+)?/);
    return m?Number(m[0]):NaN;
  };
  const fmt=(x,d=1)=>Number(x).toLocaleString('zh-TW',{maximumFractionDigits:d,minimumFractionDigits:d});
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function attach(){
    let doc;
    try{doc=frame.contentDocument;if(!doc?.body)return;}catch(e){return;}
    if(doc.getElementById('tw-broker-minimal-enhance'))return;
    const css=doc.createElement('style');css.id='tw-broker-minimal-enhance';
    css.textContent=`
      .tw-chart-dots[hidden],.tw-chart-switch[hidden],#tp-compare[hidden],#uf-chart[hidden]{display:none!important}
      .tw-chart-switch{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 12px;align-items:center}
      .tw-chart-switch button{border:1px solid #dfe4eb;border-radius:999px;padding:7px 11px;background:#fff;color:#536172;font-size:12px;font-weight:650;min-height:34px;cursor:pointer}
      .tw-chart-switch button[aria-pressed="true"]{background:#21344b;color:#fff;border-color:#21344b}
      .tw-chart-dots{overflow-x:auto;max-width:100%;-webkit-overflow-scrolling:touch}
      .tw-chart-dots svg{display:block;max-width:100%;height:auto;margin:0 auto}
      .tw-chart-dots .tw-svg-label{font-family:-apple-system,BlinkMacSystemFont,"Noto Sans TC",sans-serif;fill:#526073;font-size:12px}
      .tw-chart-caption{font-size:12px;color:#7b8591;margin:6px 0 10px;line-height:1.5}
      .tw-chart-empty{padding:15px;color:#7b8591;font-size:12px;background:#f6f8fa;border-radius:10px}
      @media(max-width:600px){.tw-chart-switch button{font-size:12px}.tw-chart-dots svg{min-width:530px}}
    `;
    doc.head.appendChild(css);
    function makeToggle(host,wrap,title){
      const bar=doc.createElement('div');bar.className='tw-chart-switch';
      const original=doc.createElement('button'),alternative=doc.createElement('button');
      original.type=alternative.type='button';original.textContent='原始長條';alternative.textContent=title;
      bar.append(original,alternative);host.parentNode.insertBefore(bar,host);
      const view=doc.createElement('div');view.className='tw-chart-dots';host.insertAdjacentElement('afterend',view);
      let mode='original';
      const sync=()=>{
        original.setAttribute('aria-pressed',String(mode==='original'));
        alternative.setAttribute('aria-pressed',String(mode==='alternative'));
        host.hidden=mode!=='original';view.hidden=mode==='original';
      };
      original.onclick=()=>{mode='original';sync();notifyResize()};
      alternative.onclick=()=>{mode='alternative';wrap(view);sync();notifyResize()};
      sync();
      return {view,bar,alternative,reset:()=>{mode='original';sync();notifyResize()},update:()=>{if(mode==='alternative'){wrap(view);notifyResize()}}};
    }
    function notifyResize(){
      try{doc.defaultView?.__resizeBrokerFrame?.();}catch(e){}
      const height=doc.documentElement.scrollHeight;
      if(Number.isFinite(height)&&height>300)frame.style.height=Math.ceil(height+25)+'px';
    }
    function plot(view,records,opts){
      if(records.length<2){view.innerHTML='<div class="tw-chart-empty">至少需要兩家有效券商，才適合比較分布。</div>';return;}
      const W=620,L=125,R=56,T=26,B=42,row=29,H=T+B+row*records.length;
      const values=records.map(r=>r.value).concat(Number.isFinite(opts.reference)?[opts.reference]:[]);
      const min=Math.min(...values),max=Math.max(...values),spread=max-min;
      const pad=Math.max(spread*.14,Math.abs(max)*.025,.2);
      let lo=min-pad,hi=max+pad;
      if(opts.centerZero){const size=Math.max(Math.abs(lo),Math.abs(hi),.25);lo=-size;hi=size;}
      const x=v=>L+(v-lo)/(hi-lo)*(W-L-R);
      const ticks=4;
      let z=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${esc(opts.aria)}">`;
      for(let i=0;i<=ticks;i++){
        const v=lo+(hi-lo)*i/ticks,xx=x(v);
        z+=`<line x1="${xx}" y1="${T-10}" x2="${xx}" y2="${H-B+5}" stroke="${COLORS.guide}" opacity=".42" stroke-dasharray="3 4"/>`;
        z+=`<text class="tw-svg-label" text-anchor="middle" x="${xx}" y="${H-10}">${fmt(v)}</text>`;
      }
      if(Number.isFinite(opts.reference)){
        const xx=x(opts.reference);
        z+=`<line x1="${xx}" x2="${xx}" y1="${T-12}" y2="${H-B+6}" stroke="${COLORS.median}" stroke-width="2" stroke-dasharray="5 4"/>`;
      }
      records.forEach((r,i)=>{
        const yy=T+row*i+6,xx=x(r.value),color=r.value>0&&opts.centerZero?COLORS.positive:r.value<0&&opts.centerZero?COLORS.negative:COLORS.point;
        z+=`<text class="tw-svg-label" x="${L-12}" y="${yy+4}" text-anchor="end">${esc(r.label.length>13?r.label.slice(0,12)+'…':r.label)}</text>`;
        if(opts.centerZero)z+=`<line x1="${x(0)}" y1="${yy}" x2="${xx}" y2="${yy}" stroke="${color}" stroke-width="5" opacity=".45"/>`;
        z+=`<circle cx="${xx}" cy="${yy}" r="6" fill="${color}"><title>${esc(r.label)}：${fmt(r.value,2)}</title></circle>`;
        z+=`<text x="${W-R+9}" y="${yy+4}" font-family="sans-serif" font-size="12" fill="${color}">${r.value>0&&opts.centerZero?'+':''}${fmt(r.value,2)}</text>`;
      });
      z+='</svg>';
      view.innerHTML=z+`<p class="tw-chart-caption">${esc(opts.caption)}</p>`;
    }
    const target=doc.getElementById('tp-compare');
    if(target){
      const draw=view=>{
        const rows=[...target.querySelectorAll('.tp-row')].map(row=>({label:row.querySelector('.tp-label')?.textContent?.trim()||'',value:numberFrom(row.querySelector('.tp-val')?.textContent)})).filter(r=>r.label&&Number.isFinite(r.value));
        const med=numberFrom(doc.getElementById('tp-med')?.textContent);
        plot(view,rows,{reference:med,centerZero:false,aria:'各券商最新目標價分布圖',caption:'虛線為最新目標價中位數；詳細數字、日期與 PDF 連結保留在原始長條清單。'});
      };
      const toggle=makeToggle(target,draw,'目標價分布');
      new MutationObserver(toggle.update).observe(target,{childList:true});
    }
    const financial=doc.getElementById('uf-chart');
    if(financial){
      const available=()=>{
        const isEPS=doc.getElementById('uf-metric')?.value==='eps';
        const actualText=doc.getElementById('uf-actual')?.textContent||'';
        const actual=/實際\s*EPS/.test(actualText)?numberFrom(actualText.split('：').pop()):NaN;
        return isEPS && Number.isFinite(actual) && financial.querySelectorAll('.uf-line').length>=2;
      };
      const draw=view=>{
        const isEPS=doc.getElementById('uf-metric')?.value==='eps';
        const actualText=doc.getElementById('uf-actual')?.textContent||'';
        const actual=/實際\s*EPS/.test(actualText)?numberFrom(actualText.split('：').pop()):NaN;
        if(!isEPS||!Number.isFinite(actual)){
          view.innerHTML='<div class="tw-chart-empty">僅當選擇「季度 EPS」且已有實際公布值時，才顯示各券商預估誤差；其他指標維持原始長條比較。</div>';return;
        }
        const rows=[...financial.querySelectorAll('.uf-line')].map(row=>({label:row.querySelector('span')?.textContent?.trim()||'',value:numberFrom(row.querySelector('strong')?.textContent)})).filter(r=>r.label&&Number.isFinite(r.value)).map(r=>({...r,value:r.value-actual}));
        plot(view,rows,{reference:0,centerZero:true,aria:'券商 EPS 預估與實際 EPS 差距',caption:`實際 EPS ${fmt(actual,2)} 元；正值代表券商預估高於實際，負值代表低於實際。單位：元／股。`});
      };
      const toggle=makeToggle(financial,draw,'對實際 EPS 誤差');
      const syncAvailable=()=>{
        const yes=available();
        toggle.bar.hidden=!yes;
        if(!yes)toggle.reset();
        else toggle.update();
      };
      new MutationObserver(syncAvailable).observe(financial,{childList:true});
      for(const id of ['uf-metric','uf-period','uf-kind'])doc.getElementById(id)?.addEventListener('change',()=>setTimeout(syncAvailable,0));
      syncAvailable();
    }
    notifyResize();
  }
  frame.addEventListener('load',attach);
  try{if(frame.contentDocument?.readyState==='complete'&&frame.contentDocument?.body)attach();}catch(e){}
})();
