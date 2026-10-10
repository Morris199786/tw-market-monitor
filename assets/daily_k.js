/* 日K：獨立靜態行情檔、原生 Canvas；不額外呼叫 AI */
(function(){
'use strict';
const periods=[5,10,20,60,120,240],colors=['#ffd54a','#f574dd','#55e4e8','#f5ae7e','#9e99ff','#eb7582'];
let active=null;const cache=new Map();
function movingAverage(bars,n,gaps=[]){let sum=0,queue=[];return bars.map((b,i)=>{if(i && gaps.some(d=>d>bars[i-1].time && d<b.time)){sum=0;queue=[];}sum+=b.close;queue.push(b.close);if(queue.length>n)sum-=queue.shift();return queue.length===n?sum/n:null;});}
function validBars(input){if(!Array.isArray(input))return [];let last='';return input.filter(b=>{const ok=/^\d{4}-\d{2}-\d{2}$/.test(b.time)&&b.time>last&&['open','high','low','close','volume'].every(k=>typeof b[k]==='number'&&Number.isFinite(b[k]))&&b.low>0&&b.volume>=0&&b.low<=Math.min(b.open,b.close)&&b.high>=Math.max(b.open,b.close);if(ok)last=b.time;return ok;});}
function destroy(){if(active){active.cleanup();active=null;}}
function style(){if(document.getElementById('dailyKStyle'))return;const el=document.createElement('style');el.id='dailyKStyle';el.textContent=`
#dailyKHost{min-width:0;color:#eef3ff;background:#101826;border-radius:14px;padding:12px;overflow:hidden}
#dailyKHost *{box-sizing:border-box}#dailyKHost button{font:inherit;font-size:14px;min-height:40px;border:1px solid #536078;border-radius:8px;padding:7px 10px;background:#202d40;color:#fff;cursor:pointer}
#dailyKHost button[aria-pressed="true"]{background:#315b88;border-color:#8ac4ff}
#dailyKHost .dk-tools{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}#dailyKHost .dk-info{font-size:13px;line-height:1.7;font-variant-numeric:tabular-nums;min-height:45px}
#dailyKHost .dk-ma{display:flex;gap:6px 12px;flex-wrap:wrap;font-size:13px;line-height:1.8;margin:8px 0}#dailyKHost .dk-ma label{white-space:nowrap}#dailyKHost .dk-ma input{accent-color:currentColor}
#dailyKHost canvas{display:block;width:100%;height:440px;touch-action:none;outline:none}#dailyKHost canvas:focus-visible{outline:2px solid #80c9ff}
#dailyKHost .dk-note{font-size:12px;line-height:1.7;color:#b2bfd1;margin-top:8px}#dailyKHost .dk-warning{color:#ffdc88;font-size:13px}
#stockDetailBody:has(#dailyKHost) .stock-detail-periods{display:none}#stockDetailBody .stock-detail-tabs{grid-template-columns:repeat(3,minmax(0,1fr))}
@media(max-width:480px){#stockDetailBody:has(#dailyKHost) .stock-detail-card{padding:4px}#dailyKHost{padding:8px}#dailyKHost canvas{height:440px}}
`;document.head.appendChild(el);}
async function mount(host,ticker){
 destroy();style();const token={cleanup:()=>{token.dead=true;}};active=token;host.innerHTML='<div class="dk-note">載入日 K 行情…</div>';
 try{
 const cached=cache.get(ticker);let result=cached && Date.now()-cached.at<300000 ? cached.data : null;
 if(!result){const response=await fetch('./data/daily_k/'+encodeURIComponent(ticker)+'.json?v='+new Date().toISOString().slice(0,10),{cache:'no-cache'});if(!response.ok)throw new Error('行情檔尚未建立或讀取失敗');result=await response.json();cache.set(ticker,{at:Date.now(),data:result});}
 if(token.dead||!host.isConnected)return;
 if(String(result.ticker)!==String(ticker))throw new Error('股票代號不符');
 const bars=validBars(result.bars);if(!bars.length||bars.length!==result.bars.length)throw new Error('開高低收資料不完整');
 create(host,bars,result,token);
 }catch(e){if(!token.dead&&host.isConnected){host.replaceChildren();const p=document.createElement('p');p.className='dk-warning';p.textContent='日 K 暫時無法顯示：'+e.message+'，請確認 Daily K charts 已執行成功';host.append(p);}}
}
function create(host,bars,metadata,token){
 const ma=Object.fromEntries(periods.map(n=>[n,movingAverage(bars,n,metadata.missing_dates || [])]));const enabled=new Set(periods);
 let count=Math.min(90,bars.length),end=bars.length,selected=bars.length-1,crossY=null,mode='inspect',size={w:400,h:440},frame=0;
 const pointers=new Map();let drag=null,pinch=null;
 host.innerHTML=`<div class="dk-info" aria-live="off"></div><div class="dk-ma">${periods.map((n,i)=>`<label style="color:${colors[i]}"><input type="checkbox" data-ma="${n}" checked>MA${n} <span data-value="${n}">—</span></label>`).join('')}</div><div class="dk-tools"><button data-tool="inspect" aria-pressed="true">十字查價</button><button data-tool="pan" aria-pressed="false">拖曳平移</button><button data-tool="in" aria-label="放大日K">＋</button><button data-tool="out" aria-label="縮小日K">－</button><button data-tool="left" aria-label="較早行情">◀</button><button data-tool="right" aria-label="較新行情">▶</button><button data-tool="reset">最新</button></div><canvas tabindex="0" aria-label="日K及成交量，十字查價模式拖曳查看價格，雙指縮放，鍵盤左右查價、加減縮放"></canvas><div class="dk-note"></div>`;
 host.querySelector('.dk-note').textContent=`資料截至 ${bars.at(-1).time}｜${metadata.source || 'Yahoo Finance'}｜成交量：張\n已收盤日 K，非即時報價；採來源 OHLC/Close，非 Adj Close（可能調整拆股）\n單指查價／切換平移，雙指或＋－縮放；MA 為收盤價簡單平均，資料不足顯示 —`;
 if(metadata.missing_dates?.length)host.querySelector('.dk-note').textContent+=`\n來源有 ${metadata.missing_dates.length} 筆無報價日，未補值，均線跨缺漏後重新累積` ;
 host.querySelector('.dk-note').style.whiteSpace='pre-line';
 const canvas=host.querySelector('canvas'),ctx=canvas.getContext('2d');
 const fmt=(v,d=2)=>v==null?'—':v.toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d});
 function bounds(){count=Math.max(Math.min(10,bars.length),Math.min(bars.length,Math.round(count)));end=Math.max(count,Math.min(bars.length,Math.round(end)));}
 function schedule(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;draw();});}
 function geometry(){const left=8,right=size.w-58,top=24,bottom=290,vtop=318,vbottom=size.h-30,start=end-count;const visible=bars.slice(start,end);let lo=Math.min(...visible.map(b=>b.low)),hi=Math.max(...visible.map(b=>b.high));for(const n of enabled)for(let i=start;i<end;i++){const v=ma[n][i];if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v);}}const pad=Math.max((hi-lo)*.07,hi*.003,.01);lo=Math.max(0,lo-pad);hi+=pad;return {left,right,top,bottom,vtop,vbottom,start,lo,hi,step:(right-left)/count,maxVol:Math.max(1,...visible.map(b=>b.volume))};}
 function draw(){if(token.dead||!host.isConnected)return;bounds();const g=geometry(),{left,right,top,bottom,vtop,vbottom,start,lo,hi,step}=g;ctx.clearRect(0,0,size.w,size.h);ctx.fillStyle='#101826';ctx.fillRect(0,0,size.w,size.h);ctx.font='12px system-ui';ctx.textBaseline='middle';
 const px=i=>left+(i-start+.5)*step,py=v=>bottom-(v-lo)/(hi-lo)*(bottom-top);
 ctx.strokeStyle='#334052';ctx.fillStyle='#b2bfd1';ctx.lineWidth=1;
 for(let i=0;i<=4;i++){const y=top+(bottom-top)*i/4;ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(fmt(hi-(hi-lo)*i/4),right+4,y);}
 ctx.fillText('成交量（張）',left,vtop-10);ctx.fillText(fmt(g.maxVol/1000,0),right+3,vtop);
 ctx.save();ctx.beginPath();ctx.rect(left,top,right-left,vbottom-top);ctx.clip();
 for(let i=start;i<end;i++){const b=bars[i],x=px(i),up=b.close>=b.open,color=up?'#ff485c':'#45c787',width=Math.max(1,step*.65);ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,py(b.high));ctx.lineTo(x,py(b.low));ctx.stroke();ctx.fillRect(x-width/2,Math.min(py(b.open),py(b.close)),width,Math.max(1,Math.abs(py(b.open)-py(b.close))));const h=b.volume/g.maxVol*(vbottom-vtop);ctx.fillRect(x-width/2,vbottom-h,width,h);}
 periods.forEach((n,j)=>{if(!enabled.has(n))return;ctx.strokeStyle=colors[j];ctx.lineWidth=1.5;ctx.beginPath();let started=false;for(let i=start;i<end;i++){if(ma[n][i]==null){started=false;continue;}if(!started){ctx.moveTo(px(i),py(ma[n][i]));started=true;}else ctx.lineTo(px(i),py(ma[n][i]));}ctx.stroke();});ctx.restore();
 ctx.fillStyle='#b2bfd1';ctx.textAlign='center';for(let j=0;j<4;j++){const i=Math.min(end-1,start+Math.round((count-1)*j/3));ctx.fillText(bars[i].time.slice(5),px(i),size.h-12);}ctx.textAlign='left';
 if(selected>=start&&selected<end){const b=bars[selected],x=px(selected),cy=crossY==null?py(b.close):Math.max(top,Math.min(vbottom,crossY));ctx.strokeStyle='#fff';ctx.lineWidth=1;ctx.setLineDash([4,3]);ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,vbottom);ctx.moveTo(left,cy);ctx.lineTo(right,cy);ctx.stroke();ctx.setLineDash([]);
 const label=cy<=bottom?fmt(hi-(cy-top)/(bottom-top)*(hi-lo)):cy>=vtop?fmt((vbottom-cy)/(vbottom-vtop)*g.maxVol/1000,0):'';
 if(label){ctx.fillStyle='#edf3ff';ctx.fillRect(right,cy-10,58,20);ctx.fillStyle='#101826';ctx.fillText(label,right+3,cy);}
 ctx.fillStyle='#edf3ff';const tx=Math.max(0,Math.min(size.w-88,x-44));ctx.fillRect(tx,size.h-24,88,24);ctx.fillStyle='#101826';ctx.fillText(b.time,tx+3,size.h-12);
 }
 const b=bars[selected];host.querySelector('.dk-info').textContent=`${b.time}　開 ${fmt(b.open)}　高 ${fmt(b.high)}　低 ${fmt(b.low)}　收 ${fmt(b.close)}　量 ${fmt(b.volume/1000,0)} 張`;
 periods.forEach(n=>host.querySelector(`[data-value="${n}"]`).textContent=fmt(ma[n][selected]));
 }
 function zoom(factor,anchor=.5){const old=count,start=end-count,pivot=start+old*anchor;count=Math.max(Math.min(10,bars.length),Math.min(bars.length,Math.round(old*factor)));end=Math.round(pivot+count*(1-anchor));bounds();schedule();}
 const local=e=>{const r=canvas.getBoundingClientRect();return {x:e.clientX-r.left,y:e.clientY-r.top};};
 function inspect(p){const g=geometry();selected=Math.max(g.start,Math.min(end-1,g.start+Math.floor((p.x-g.left)/g.step)));crossY=p.y;schedule();}
 canvas.onpointerdown=e=>{e.preventDefault();canvas.setPointerCapture(e.pointerId);const p=local(e);pointers.set(e.pointerId,p);if(pointers.size===1){drag={x:p.x,end};if(mode==='inspect')inspect(p);}if(pointers.size===2){const a=[...pointers.values()];pinch={distance:Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y),count,end};}};
 canvas.onpointermove=e=>{const p=local(e);if(pointers.has(e.pointerId))pointers.set(e.pointerId,p);if(pointers.size>=2&&pinch){const a=[...pointers.values()],distance=Math.hypot(a[0].x-a[1].x,a[0].y-a[1].y);if(distance>8){count=pinch.count;end=pinch.end;zoom(pinch.distance/distance,(a[0].x+a[1].x)/2/size.w);}return;}if(pointers.size===1&&mode==='pan'&&drag){end=drag.end-Math.round((p.x-drag.x)/geometry().step);bounds();crossY=null;schedule();}else if(mode==='inspect'&&(pointers.size===1||e.pointerType==='mouse'))inspect(p);};
 const release=e=>{pointers.delete(e.pointerId);pinch=null;drag=null;if(pointers.size===1){const p=[...pointers.values()][0];drag={x:p.x,end};}};canvas.onpointerup=release;canvas.onpointercancel=release;
 const wheel=e=>{e.preventDefault();zoom(e.deltaY>0?1.15:1/1.15,Math.max(0,Math.min(1,local(e).x/size.w)));};canvas.addEventListener('wheel',wheel,{passive:false});
 canvas.onkeydown=e=>{if(['ArrowLeft','ArrowRight','+','-','='].includes(e.key)){e.preventDefault();if(e.key==='+'||e.key==='=')zoom(.8);else if(e.key==='-')zoom(1.25);else{selected=Math.max(0,Math.min(bars.length-1,selected+(e.key==='ArrowLeft'?-1:1)));if(selected<end-count)end=selected+count;if(selected>=end)end=selected+1;crossY=null;schedule();}}};
 host.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>{const t=b.dataset.tool;if(t==='inspect'||t==='pan'){mode=t;host.querySelectorAll('[aria-pressed]').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.tool===t)));}else if(t==='in')zoom(.8);else if(t==='out')zoom(1.25);else{if(t==='reset'){count=Math.min(90,bars.length);end=bars.length;selected=bars.length-1;}else end+=(t==='left'?-1:1)*Math.max(1,Math.round(count*.5));bounds();crossY=null;schedule();}});
 host.querySelectorAll('[data-ma]').forEach(b=>b.onchange=()=>{const n=Number(b.dataset.ma);b.checked?enabled.add(n):enabled.delete(n);schedule();});
 const resize=new ResizeObserver(()=>{size={w:Math.max(220,canvas.clientWidth),h:440};const dpr=window.devicePixelRatio||1;canvas.width=Math.round(size.w*dpr);canvas.height=Math.round(size.h*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);schedule();});resize.observe(canvas);
 token.cleanup=()=>{token.dead=true;resize.disconnect();if(frame)cancelAnimationFrame(frame);canvas.removeEventListener('wheel',wheel);pointers.clear();};
}
window.DailyK={mount,destroy,movingAverage,validBars};
})();
