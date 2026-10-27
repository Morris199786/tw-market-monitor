/* Broker Report visualizations — optional, read-only renderer.
 * AI output contract: report.visualizations = [{type,title,labels,values,unit,series?,headers?,rows?}]
 * This file never fetches reports, invokes APIs, or mutates report data.
 * Integration: BrokerReportCharts.render(container, report.visualizations)
 */
(function (global) {
  'use strict';
  const TYPES = new Set(['table', 'bar', 'line', 'pie', 'kpi', 'stacked_bar', 'waterfall', 'dual_axis', 'timeline', 'flow', 'scatter', 'heatmap']);
  const NS = 'http://www.w3.org/2000/svg';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number = v => (typeof v === 'number' || (typeof v === 'string' && v.trim())) && Number.isFinite(Number(v)) ? Number(v) : null;
  const fmt = v => { const n = number(v); return n === null ? String(v ?? '—') : n.toLocaleString('zh-TW', {maximumFractionDigits: 3}); };
  const palette = ['#2563eb','#d97706','#059669','#7c3aed','#dc2626','#0891b2','#be185d','#64748b'];
  function svgEl(tag, attrs, text) {
    const el = document.createElementNS(NS, tag);
    for (const [k,v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
    if (text !== undefined) el.textContent = String(text);
    return el;
  }
  function normalized(item) {
    if (!item || typeof item !== 'object' || !TYPES.has(item.type)) return null;
    const labels = Array.isArray(item.labels) ? item.labels.slice(0,32).map(String) : [];
    const values = Array.isArray(item.values) ? item.values.slice(0,32).map(number) : [];
    const series = Array.isArray(item.series) ? item.series.slice(0,6).map(s => ({name:String(s.name||''), values:Array.isArray(s.values)?s.values.slice(0,32).map(number):[]})) : [];
    return {...item, labels, values, series};
  }
  function table(box, item) {
    const headers = Array.isArray(item.headers) ? item.headers.slice(0,16) : [];
    const rows = Array.isArray(item.rows) ? item.rows.slice(0,80) : [];
    if (!headers.length || !rows.length) return;
    const wrap = document.createElement('div'); wrap.className = 'brv-scroll';
    const t = document.createElement('table'); t.className = 'brv-table';
    const thead = t.createTHead(), tr = thead.insertRow();
    headers.forEach(h => { const th=document.createElement('th'); th.textContent=String(h??''); tr.appendChild(th); });
    const body=t.createTBody();
    rows.forEach(row => { if (!Array.isArray(row)) return; const tr=body.insertRow(); row.slice(0,headers.length).forEach(v=>{ const td=tr.insertCell(); td.textContent=fmt(v); }); });
    wrap.appendChild(t);box.appendChild(wrap);
  }
  function kpi(box,item) {
    const values=Array.isArray(item.items)?item.items.slice(0,8):[];
    if (!values.length) return;
    const grid=document.createElement('div');grid.className='brv-kpis';
    values.forEach(v=>{const c=document.createElement('div');c.className='brv-kpi';const name=document.createElement('small');name.textContent=String(v.label??'');const val=document.createElement('strong');val.textContent=fmt(v.value)+(v.unit?' '+v.unit:'');c.append(name,val);grid.appendChild(c);});
    box.appendChild(grid);
  }
  function chart(box,item) {
    const labels=item.labels, multi=item.series.length?item.series:[{name:item.title||'',values:item.values}];
    if (!labels.length || !multi.length || multi.some(s=>s.values.length!==labels.length || s.values.some(v=>v===null))) return;
    const width=760,height=320,left=68,right=26,top=22,bottom=labels.length>12?84:65;
    const svg=svgEl('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':item.title||item.type,style:'width:100%;height:auto;display:block'});
    const all=multi.flatMap(s=>s.values),max=Math.max(0,...all),min=Math.min(0,...all);
    const ymax=max===min?max+1:max+(max-min)*.08,ymin=Math.min(0,min),pw=width-left-right,ph=height-top-bottom;
    const x=i=>left+pw*(i+.5)/labels.length,y=v=>top+ph*(ymax-v)/(ymax-ymin||1);
    for(let k=0;k<=4;k++){const v=ymin+(ymax-ymin)*k/4,yy=y(v);svg.appendChild(svgEl('line',{x1:left,y1:yy,x2:width-right,y2:yy,stroke:'currentColor','stroke-opacity':'.13'}));svg.appendChild(svgEl('text',{x:left-8,y:yy+4,'text-anchor':'end','font-size':11,fill:'currentColor'},fmt(v)));}
    if(item.type==='bar') {
      const groupWidth=pw/labels.length*.78,bw=groupWidth/multi.length;
      multi.forEach((s,j)=>s.values.forEach((v,i)=>{const zero=y(0),yy=y(v);svg.appendChild(svgEl('rect',{x:x(i)-groupWidth/2+j*bw,y:Math.min(zero,yy),width:Math.max(2,bw-2),height:Math.max(1,Math.abs(zero-yy)),rx:2,fill:palette[j%palette.length]}));}));
    } else {
      multi.forEach((s,j)=>{const pts=s.values.map((v,i)=>`${x(i)},${y(v)}`).join(' ');svg.appendChild(svgEl('polyline',{points:pts,fill:'none',stroke:palette[j%palette.length],'stroke-width':2.5,'stroke-linejoin':'round'}));s.values.forEach((v,i)=>svg.appendChild(svgEl('circle',{cx:x(i),cy:y(v),r:3,fill:palette[j%palette.length]})));});
    }
    labels.forEach((lab,i)=>{const txt=svgEl('text',{x:x(i),y:height-bottom+18,'text-anchor':'end','font-size':11,fill:'currentColor',transform:`rotate(-35 ${x(i)} ${height-bottom+18})`},lab.slice(0,20));svg.appendChild(txt);});
    box.appendChild(svg);
    if(multi.length>1){const legend=document.createElement('div');legend.className='brv-legend';multi.forEach((s,j)=>{const e=document.createElement('span');e.innerHTML=`<i style="background:${palette[j%palette.length]}"></i>${esc(s.name||`系列 ${j+1}`)}`;legend.appendChild(e);});box.appendChild(legend);}
  }
  function pie(box,item){
    const a=item.values;if(!item.labels.length || item.labels.length!==a.length || a.some(v=>v===null||v<0))return;
    const sum=a.reduce((p,c)=>p+c,0);if(sum<=0)return;
    let cursor=-Math.PI/2;const svg=svgEl('svg',{viewBox:'0 0 440 270',role:'img','aria-label':item.title||'占比',style:'width:100%;max-width:440px;height:auto;display:block;margin:auto'});
    a.forEach((v,i)=>{if(v===0)return;const start=cursor,end=cursor+v/sum*Math.PI*2;cursor=end;const cx=155,cy=135,r=108;const pt=t=>[cx+r*Math.cos(t),cy+r*Math.sin(t)];const p1=pt(start),p2=pt(end),large=end-start>Math.PI?1:0;const path=v===sum?`M ${cx-r} ${cy} a ${r} ${r} 0 1 0 ${r*2} 0 a ${r} ${r} 0 1 0 ${-r*2} 0`:`M ${cx} ${cy} L ${p1[0]} ${p1[1]} A ${r} ${r} 0 ${large} 1 ${p2[0]} ${p2[1]} Z`;svg.appendChild(svgEl('path',{d:path,fill:palette[i%palette.length]}));});
    box.appendChild(svg);const legend=document.createElement('div');legend.className='brv-legend';item.labels.forEach((lab,i)=>{const e=document.createElement('span');e.innerHTML=`<i style="background:${palette[i%palette.length]}"></i>${esc(lab)}：${(a[i]/sum*100).toFixed(1)}%`;legend.appendChild(e);});box.appendChild(legend);
  }

  // Extended visualizations: all data must be explicitly supplied by the AI.
  const svgBase=(title,w=760,h=330)=>svgEl('svg',{viewBox:`0 0 ${w} ${h}`,role:'img','aria-label':title||'圖表',style:'width:100%;height:auto;display:block'});
  const txt=(svg,x,y,t,extra={})=>svg.appendChild(svgEl('text',{x,y,'font-size':12,fill:'currentColor',...extra},String(t).slice(0,45)));
  const line=(svg,x1,y1,x2,y2,extra={})=>svg.appendChild(svgEl('line',{x1,y1,x2,y2,stroke:'currentColor','stroke-opacity':'.22',...extra}));
  function stackedBar(box,item){
    const labs=item.labels, ss=item.series;if(!labs.length||!ss.length||ss.some(s=>s.values.length!==labs.length||s.values.some(v=>v===null||v<0)))return;
    const sums=labs.map((_,i)=>ss.reduce((a,s)=>a+s.values[i],0)),max=Math.max(...sums,1),svg=svgBase(item.title),left=66,base=265,plot=220,w=660/labs.length;
    [0,.25,.5,.75,1].forEach(t=>{const y=base-t*plot;line(svg,left,y,740,y);txt(svg,58,y+4,fmt(max*t),{'text-anchor':'end'});});
    labs.forEach((lab,i)=>{let acc=0;ss.forEach((ser,j)=>{const v=ser.values[i],h=v/max*plot;svg.appendChild(svgEl('rect',{x:left+i*w+w*.18,y:base-(acc+v)/max*plot,width:w*.64,height:h,fill:palette[j%palette.length]}));acc+=v;});txt(svg,left+(i+.5)*w,285,lab,{'text-anchor':'middle'});});box.appendChild(svg);legend(box,ss.map(s=>s.name));
  }
  function legend(box,names){const d=document.createElement('div');d.className='brv-legend';names.forEach((name,i)=>{const x=document.createElement('span'),sw=document.createElement('i');sw.style.background=palette[i%palette.length];x.append(sw,document.createTextNode(String(name||`系列${i+1}`)));d.appendChild(x);});box.appendChild(d);}
  function waterfall(box,item){
    const labs=item.labels,vals=item.values;if(!labs.length||labs.length!==vals.length||vals.some(v=>v===null))return;
    const starts=[],ends=[];let acc=0;vals.forEach((v,i)=>{const total=Array.isArray(item.totals)&&item.totals[i]===true;starts.push(total?0:acc);ends.push(total?v:acc+v);acc=ends[i];});
    const lo=Math.min(0,...starts,...ends),hi=Math.max(1,...starts,...ends),svg=svgBase(item.title),left=65,base=268,plot=220,w=670/labs.length,y=v=>base-(v-lo)/(hi-lo||1)*plot;
    line(svg,left,y(0),745,y(0));labs.forEach((lab,i)=>{const top=Math.min(y(starts[i]),y(ends[i])),h=Math.abs(y(starts[i])-y(ends[i]));svg.appendChild(svgEl('rect',{x:left+i*w+w*.18,y:top,width:w*.64,height:Math.max(h,1),fill:Array.isArray(item.totals)&&item.totals[i]===true?palette[0]:vals[i]>=0?palette[2]:palette[4]}));txt(svg,left+(i+.5)*w,top-6,fmt(vals[i]),{'text-anchor':'middle'});txt(svg,left+(i+.5)*w,292,lab,{'text-anchor':'middle'});});box.appendChild(svg);
  }
  function dualAxis(box,item){
    const labs=item.labels,ss=item.series;if(!labs.length||ss.length!==2||ss.some(s=>s.values.length!==labs.length||s.values.some(v=>v===null)))return;
    const svg=svgBase(item.title),left=70,right=690,top=35,base=270,x=i=>left+(right-left)*(i+.5)/labs.length;
    ss.forEach((ser,j)=>{const a=ser.values,min=Math.min(0,...a),max=Math.max(1,...a),y=v=>base-(v-min)/(max-min||1)*(base-top);const pts=a.map((v,i)=>`${x(i)},${y(v)}`).join(' ');svg.appendChild(svgEl('polyline',{points:pts,fill:'none',stroke:palette[j], 'stroke-width':3}));a.forEach((v,i)=>svg.appendChild(svgEl('circle',{cx:x(i),cy:y(v),r:3,fill:palette[j]})));txt(svg,j?745:12,20,`${ser.name||'系列'} (${ser.unit||''})`,{'text-anchor':j?'end':'start'});});labs.forEach((lab,i)=>txt(svg,x(i),292,lab,{'text-anchor':'middle'}));box.appendChild(svg);legend(box,ss.map(s=>`${s.name}${s.unit?' ('+s.unit+')':''}`));
  }
  function timeline(box,item){
    const events=Array.isArray(item.events)?item.events:[];if(!events.length)return;const list=document.createElement('ol');list.className='brv-timeline';events.slice(0,40).forEach(e=>{if(!e||!e.date||!e.label)return;const li=document.createElement('li'),date=document.createElement('time'),strong=document.createElement('strong');date.textContent=String(e.date);strong.textContent=String(e.label);li.append(date,strong);if(e.description){const p=document.createElement('p');p.textContent=String(e.description);li.append(p);}list.appendChild(li);});if(list.children.length)box.appendChild(list);
  }
  function flow(box,item){
    const nodes=Array.isArray(item.nodes)?item.nodes:[],links=Array.isArray(item.links)?item.links:[];if(!nodes.length)return;
    const map=new Map(nodes.slice(0,30).filter(n=>n&&n.id&&n.label).map(n=>[String(n.id),n]));if(!map.size)return;
    const wrap=document.createElement('div');wrap.className='brv-flow';for(const n of map.values()){const card=document.createElement('div');card.className='brv-flow-node';const head=document.createElement('strong');head.textContent=String(n.label);card.appendChild(head);if(n.description){const sub=document.createElement('small');sub.textContent=String(n.description);card.appendChild(sub);}wrap.appendChild(card);}
    const valid=links.filter(l=>l&&map.has(String(l.from))&&map.has(String(l.to))).slice(0,50);if(valid.length){const title=document.createElement('p');title.className='brv-note';title.textContent='關係（僅列報告明確描述者）';box.appendChild(title);const ul=document.createElement('ul');ul.className='brv-flow-links';valid.forEach(l=>{const li=document.createElement('li');li.textContent=`${map.get(String(l.from)).label} → ${map.get(String(l.to)).label}${l.label?'：'+l.label:''}`;ul.appendChild(li);});box.append(wrap,ul);}else box.appendChild(wrap);
  }
  function scatter(box,item){
    const points=Array.isArray(item.points)?item.points:[];const a=points.slice(0,120).filter(p=>p&&number(p.x)!==null&&number(p.y)!==null);if(!a.length)return;
    const xs=a.map(p=>Number(p.x)),ys=a.map(p=>Number(p.y)),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),svg=svgBase(item.title),left=65,right=725,top=28,bottom=270;
    const x=v=>left+(v-xmin)/(xmax-xmin||1)*(right-left),y=v=>bottom-(v-ymin)/(ymax-ymin||1)*(bottom-top);line(svg,left,bottom,right,bottom);line(svg,left,top,left,bottom);
    a.forEach(p=>{const c=svgEl('circle',{cx:x(Number(p.x)),cy:y(Number(p.y)),r:5,fill:palette[0],opacity:.75});const t=svgEl('title',{},`${p.label||''}: (${fmt(p.x)}, ${fmt(p.y)})`);c.appendChild(t);svg.appendChild(c);});txt(svg,395,312,item.x_label||'X',{'text-anchor':'middle'});txt(svg,15,20,item.y_label||'Y');box.appendChild(svg);
  }
  function heatmap(box,item){
    const cols=Array.isArray(item.columns)?item.columns:[],rows=Array.isArray(item.rows)?item.rows:[];if(!cols.length||!rows.length)return;const nums=rows.flatMap(r=>Array.isArray(r.values)?r.values.map(number).filter(v=>v!==null):[]);if(!nums.length)return;const lo=Math.min(...nums),hi=Math.max(...nums),table=document.createElement('table');table.className='brv-table brv-heatmap',thead=table.createTHead(),tr=thead.insertRow();tr.insertCell().textContent='';cols.slice(0,20).forEach(c=>{const th=document.createElement('th');th.textContent=String(c);tr.appendChild(th);});const tbody=table.createTBody();rows.slice(0,40).forEach(r=>{if(!r||!Array.isArray(r.values))return;const row=tbody.insertRow();row.insertCell().textContent=String(r.label||'');r.values.slice(0,cols.length).forEach(raw=>{const td=row.insertCell(),v=number(raw);td.textContent=v===null?'—':fmt(v);if(v!==null){const t=(v-lo)/(hi-lo||1);td.style.background=`rgba(37,99,235,${(.08+.5*t).toFixed(2)})`;}});});const wrap=document.createElement('div');wrap.className='brv-scroll';wrap.appendChild(table);box.appendChild(wrap);
  }

  function render(container,visualizations){
    if(typeof container==='string')container=document.querySelector(container);
    if(!(container instanceof Element))return 0;
    container.querySelectorAll(':scope > .brv-root').forEach(n=>n.remove());
    if(!Array.isArray(visualizations)||!visualizations.length)return 0;
    const root=document.createElement('section');root.className='brv-root';let count=0;
    visualizations.slice(0,8).forEach(raw=>{const item=normalized(raw);if(!item)return;const card=document.createElement('section');card.className='brv-card';const title=document.createElement('h4');title.textContent=String(item.title||'數據視覺化');card.appendChild(title);const before=card.childElementCount;
      if(item.type==='table')table(card,item);else if(item.type==='kpi')kpi(card,item);else if(item.type==='pie')pie(card,item);else if(item.type==='stacked_bar')stackedBar(card,item);else if(item.type==='waterfall')waterfall(card,item);else if(item.type==='dual_axis')dualAxis(card,item);else if(item.type==='timeline')timeline(card,item);else if(item.type==='flow')flow(card,item);else if(item.type==='scatter')scatter(card,item);else if(item.type==='heatmap')heatmap(card,item);else chart(card,item);
      if(card.childElementCount===before)return;
      if(item.note){const p=document.createElement('p');p.className='brv-note';p.textContent=String(item.note);card.appendChild(p);}root.appendChild(card);count++;
    });
    if(count)container.appendChild(root);return count;
  }
  const style=document.createElement('style');style.textContent=`
    #reports .brv-root{display:grid;gap:14px;margin:18px 0}
    #reports .brv-card{min-width:0;padding:16px;border:1px solid var(--line,#d9e0e8);border-radius:14px;background:var(--card,#fff);color:var(--ink,#17202b)}
    #reports .brv-card h4{margin:0 0 14px;font-size:15px;font-weight:750}
    #reports .brv-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
    #reports .brv-table{width:100%;border-collapse:collapse;font-size:13px;min-width:380px}
    #reports .brv-table th,#reports .brv-table td{padding:9px 11px;border-bottom:1px solid var(--line,#e5e7eb);text-align:right;white-space:nowrap}
    #reports .brv-table th:first-child,#reports .brv-table td:first-child{text-align:left}
    #reports .brv-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:10px}
    #reports .brv-kpi{padding:13px;border-radius:10px;background:var(--soft,#f2f5f8);display:grid;gap:6px}
    #reports .brv-kpi small{font-size:12px;opacity:.7}#reports .brv-kpi strong{font-size:19px}
    #reports .brv-legend{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;margin-top:8px;font-size:12px}
    #reports .brv-legend span{display:inline-flex;gap:5px;align-items:center}
    #reports .brv-legend i{width:10px;height:10px;border-radius:3px;display:inline-block}
    #reports .brv-timeline{margin:0;padding-left:24px;border-left:2px solid var(--line,#d9e0e8);list-style:none}
    #reports .brv-timeline li{position:relative;margin:0 0 16px;display:grid;gap:3px}
    #reports .brv-timeline li:before{content:'';position:absolute;left:-31px;top:6px;width:11px;height:11px;border-radius:50%;background:#2563eb}
    #reports .brv-timeline time{font-size:12px;color:var(--muted,#64748b)}
    #reports .brv-timeline p{margin:0;font-size:13px;line-height:1.6}
    #reports .brv-flow{display:flex;flex-wrap:wrap;gap:10px}
    #reports .brv-flow-node{display:grid;gap:5px;padding:12px;border:1px solid var(--line,#d9e0e8);border-radius:10px;flex:1 1 150px;min-width:0}
    #reports .brv-flow-node small{line-height:1.5;color:var(--muted,#64748b)}
    #reports .brv-flow-links{font-size:13px;line-height:1.7;padding-left:20px}
    #reports .brv-heatmap td{min-width:62px}
    #reports .brv-note{font-size:12px;opacity:.75;line-height:1.6;margin:10px 0 0}
    @media(max-width:650px){#reports .brv-card{padding:12px}#reports .brv-card h4{font-size:14px}}
  `;
  (document.head||document.documentElement).appendChild(style);
  global.BrokerReportCharts=Object.freeze({render});
})(window);
