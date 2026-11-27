/* Read-only company meeting integration. Never feeds broker consensus. */
(()=>{'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let meetings=[],loaded=false,failed=false,registry={};
const codes=r=>String(r.ticker||'').split(/[、,;\/\s]+/).map(x=>x.replace(/\.(TW|TWO)$/i,'')).filter(x=>/^\d{4}$/.test(x));
const date=r=>/^\d{4}-\d{2}-\d{2}$/.test(r.meeting_date||'')?r.meeting_date:String(r.date||'');
const label=r=>r.meeting_date?'會議日期':'資料日期（會議日期未確認）';
const link=r=>'./index.html?page=reports&research_id='+encodeURIComponent(r.id);
const paragraphs=r=>String(r.story||'').split(/\n+/).filter(Boolean);
const card=r=>'<article class="meeting-card"><small>法說／訪談 · '+esc(label(r))+' '+esc(date(r))+' · '+esc(r.source||'來源未標示')+'</small><h3>'+esc(r.title||r.company)+'</h3>'+paragraphs(r).map(x=>'<p>'+esc(x)+'</p>').join('')+'<a href="'+esc(link(r))+'" target="_top">查看完整法說／訪談 ↗</a></article>';
const style=document.createElement('style');style.textContent='.meeting-research{margin:14px 0 20px}.meeting-research h2{margin:0 0 8px}.meeting-research .meeting-note{font-size:13px;color:#64748b;line-height:1.6}.meeting-card{padding:14px;border:1px solid #dce4ef;border-radius:12px;background:#fff;margin:10px 0;color:#243040;overflow-wrap:anywhere}.meeting-card small{color:#64748b;font-size:12px}.meeting-card h3{font-size:15px;margin:8px 0}.meeting-card p{font-size:14px;line-height:1.7;margin:8px 0}.meeting-card a{font-size:13px;font-weight:650}.meeting-research details>summary{cursor:pointer;font-weight:650;color:#245c91}.meeting-history-tag{color:#245c91;font-weight:700;font-size:12px}';document.head.append(style);
function ensureOptions(){
 const select=$('ticker'),list=$('stocks');if(!select||!select.options.length)return;
 const existing=new Set([...select.options].map(o=>o.value)),suggestions=new Set([...list.options].map(o=>o.value));
 for(const r of meetings){for(const code of codes(r)){
  const name=registry[code]?.name||(!r.is_multi_company&&codes(r).length===1?r.company:'')||code;
  if(!existing.has(code)){const o=new Option(name+'　'+code,code);select.add(o);existing.add(code)}
  for(const value of [code,name])if(value&&!suggestions.has(value)){list.append(new Option(value));suggestions.add(value)}
 }}
}
function history(rows){
 const target=$('reports');if(!target)return;
 let list=target.querySelector('.br-history-list');
 target.querySelectorAll('[data-meeting-history]').forEach(el=>el.remove());
 if(!rows.length)return;
 if(!list){target.querySelector('.br-history-empty')?.remove();list=document.createElement('div');list.className='br-history-list';target.append(list);}
 for(const r of rows){
  const el=document.createElement('article');el.className='br-history-item';el.dataset.meetingHistory='1';
  el.innerHTML='<div class="br-history-broker"><span class="meeting-history-tag">法說／訪談</span> '+esc(r.title||r.company)+'<small style="display:block;color:#64748b">'+esc(r.source||'')+'</small></div><div class="br-history-date">'+esc(date(r))+'</div><a class="br-history-link" href="'+esc(link(r))+'" target="_top">完整紀錄 ↗</a>';
  const before=[...list.children].find(x=>String(x.querySelector('.br-history-date')?.textContent||'').trim()<date(r));list.insertBefore(el,before||null);
 }
}
function render(){
 const t=$('ticker')?.value||'', views=$('meetingViews'),guidance=$('meetingGuidance');if(!views||!guidance)return;
 if(!loaded){views.textContent=failed?'法說／訪談資料暫時無法載入':'載入法說／訪談…';return;}
 ensureOptions();
 const rows=meetings.filter(r=>codes(r).includes(t)).sort((a,b)=>date(b).localeCompare(date(a))||String(a.id).localeCompare(String(b.id)));
 views.innerHTML='<h2>法說／訪談研究觀點</h2><p class="meeting-note">依現有解析呈現，可能同時包含管理層說法及券商解讀，依原文歸屬，不計入下方跨券商統計。</p>'+(rows.length?card(rows[0])+(rows.length>1?'<details><summary>其他法說／訪談（'+(rows.length-1)+' 份）</summary>'+rows.slice(1).map(card).join('')+'</details>':''):'<p class="meeting-note">目前沒有此公司的已解析法說／訪談。</p>');
 // Keep whole source paragraphs and ranges; never transform ambiguous
 // financial extraction into management-issued numerical forecasts.
 const explicit=rows.flatMap(r=>paragraphs(r).filter(p=>/(公司|管理層|董事長|總經理|財務長).{0,18}(預估|預期|指引|展望|目標|估計|看好|預計|規劃|預測)|公司指引|管理層指引/.test(p)&&/營收|毛利|營益|獲利|EPS|資本支出|淨利|成長率|產能/.test(p)).map(p=>({r,p})));
 guidance.innerHTML='<h2>公司展望與財測相關說法</h2><p class="meeting-note">摘錄含管理層展望的原有摘要段落，保留區間與上下文；段內可能另有券商估計，不視為公司正式財測，不納入券商共識。</p>'+(explicit.length?explicit.slice(0,6).map(({r,p})=>'<article class="meeting-card"><small>'+esc(date(r))+' · '+esc(r.source||'')+'</small><p>'+esc(p)+'</p><a href="'+esc(link(r))+'" target="_top">查看來源 ↗</a></article>').join('')+(explicit.length>6?'<details><summary>其他相關段落（'+(explicit.length-6)+'）</summary>'+explicit.slice(6).map(({r,p})=>'<article class="meeting-card"><small>'+esc(date(r))+'</small><p>'+esc(p)+'</p><a href="'+esc(link(r))+'" target="_top">查看來源 ↗</a></article>').join('')+'</details>':''):'<p class="meeting-note">目前無明確可辨識的相關摘要段落。</p>');
 history(rows);
 window.__resizeBrokerFrame?.();
}
let timer;function schedule(){clearTimeout(timer);timer=setTimeout(render,150)}
 $('ticker')?.addEventListener('change',schedule);document.addEventListener('broker-reports-ready',schedule);
 document.querySelectorAll('.research-tab').forEach(b=>b.addEventListener('click',schedule));
 const target=$('reports');if(target)new MutationObserver(records=>{if(records.some(m=>[...m.removedNodes,...m.addedNodes].some(n=>n.nodeType===1&&!n.hasAttribute('data-meeting-history'))))schedule()}).observe(target,{childList:true});
 Promise.all([fetch('./data/research_meta.json',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error(r.status);return r.json()}),fetch('./data/report_company_registry.json',{cache:'no-store'}).then(r=>r.json()).catch(()=>({}))]).then(([data,reg])=>{if(!Array.isArray(data))throw Error('invalid meeting index');registry=reg;meetings=[...new Map(data.filter(r=>r.source_kind==='line'&&r.category==='法說／訪談'&&r.ai_processed===true&&r.id&&codes(r).length&&r.story).map(r=>[r.id,r])).values()];loaded=true;render();setTimeout(schedule,1200)}).catch(e=>{failed=true;console.warn('Meeting research unavailable',e);render()});
})();