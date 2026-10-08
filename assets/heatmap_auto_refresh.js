/* =========================================================
   Heatmap Auto Refresh / 價量切換
   2026-10-08

   量：
   - 盤中依累積成交額 / 五日全天均額（不預估）；盤後依較5日均
   - 資金流出＝族群下跌 + 成交動能較5日均放大至少10%
   - 先抽出資金流出，其餘依成交熱度動態分 Tier
   - 每頁最多 11 個族群，含資金流出；不顯示空頁
   ========================================================= */
(function(){
"use strict";

const CACHE_MS=60000;

const state={
  mode:"price",
  detail:null,
  detailAt:0,
  turnover:null,
  turnoverAt:0,
  renderingVolume:false,
  volumeRenderToken:0,
  observer:null,
  resizeTimer:null,
  goldTimer:null,
  selectedSector:null,
  volumeGroup:0,
  volumeGroupKey:null
};

const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>[...r.querySelectorAll(s)];

function n(v){
  if(v===null||v===undefined||v==="")return null;
  const x=Number(v);
  return Number.isFinite(x)?x:null
}

function esc(v){
  return String(v??"")
    .replace(/&/g,"&amp;")
    .replace(/</g,"&lt;")
    .replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;")
}

function grid(){
  return document.getElementById("heatGrid")
}

function activePeriod(){
  return typeof window.getHeatmapActivePeriod==="function"
    ?String(window.getHeatmapActivePeriod()||"1")
    :"1"
}

async function fetchJson(path,force=false){
  if(typeof window.J==="function")return window.J(path,{force});

  const r=await fetch(
    path+(path.includes("?")?"&":"?")+"v="+Date.now(),
    {cache:"no-store"}
  );

  if(!r.ok)throw new Error(`${path} HTTP ${r.status}`);
  return r.json()
}

async function loadDetail(force=false){
  if(
    !force &&
    state.detail &&
    Date.now()-state.detailAt<300000
  )return state.detail;

  state.detail=await fetchJson("./data/stock_detail.json",force);
  state.detailAt=Date.now();
  return state.detail
}

async function loadTurnover(force=false){
  if(
    !force &&
    state.turnover &&
    Date.now()-state.turnoverAt<CACHE_MS
  )return state.turnover;

  state.turnover=await fetchJson("./data/sector_turnover.json",force);
  state.turnoverAt=Date.now();
  return state.turnover
}


/* =========================================================
   STYLE
   ========================================================= */

function injectStyle(){

if($("#heatPvStyle"))return;

const s=document.createElement("style");

s.id="heatPvStyle";

s.textContent=`

#heatPvSwitch{
  display:flex;
  width:max-content;
  gap:3px;
  padding:3px;
  margin:0 0 12px;
  border:1px solid var(--line);
  border-radius:12px;
  background:var(--soft)
}

#heatPvSwitch button{
  min-width:72px;
  min-height:36px;
  padding:7px 18px;
  border:0;
  border-radius:9px;
  background:transparent;
  color:var(--muted);
  font:inherit;
  font-size:13px;
  font-weight:900;
  cursor:pointer
}

#heatPvSwitch button.active{
  background:var(--card);
  color:var(--ink);
  box-shadow:0 2px 8px rgba(15,23,42,.10)
}

#heatStrengthNote{
  display:flex;
  align-items:center;
  gap:7px;
  width:max-content;
  max-width:100%;
  margin:0 0 10px;
  padding:6px 9px;
  border:1px solid rgba(202,138,4,.25);
  border-radius:9px;
  background:rgba(254,243,199,.58);
  color:#765314;
  font-size:10px;
  font-weight:800
}

#heatStrengthNote i{
  display:block;
  width:10px;
  height:10px;
  border-radius:3px;
  background:#f5d76e
}

#heatGrid .heat-stock.heat-stock-top2{
  border-color:rgba(202,138,4,.42)!important;
  background:
    linear-gradient(
      135deg,
      rgba(254,243,199,.90),
      rgba(253,230,138,.60)
    )!important
}

#heatGrid .heat-strength-rank{
  display:inline-flex;
  margin-left:5px;
  padding:3px 6px;
  border:1px solid rgba(180,83,9,.24);
  border-radius:999px;
  background:rgba(255,251,235,.94);
  color:#92400e;
  font-size:9px;
  font-weight:900;
  line-height:1;
  white-space:nowrap
}

.turnover-head{
  display:flex;
  justify-content:space-between;
  align-items:flex-end;
  gap:10px;
  margin:0 0 10px
}

.turnover-head-main{
  font-size:14px;
  font-weight:900
}

.turnover-head-sub,
.turnover-date{
  color:var(--muted);
  font-size:11px;
  line-height:1.45
}


/* =========================================================
   判讀邏輯：預設收合
   ========================================================= */

.turnover-explain{
  margin:0 0 10px;
  border:1px solid var(--line);
  border-radius:11px;
  background:var(--soft);
  overflow:hidden
}

.turnover-explain summary{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:11px 13px;
  color:var(--ink);
  font-size:12px;
  font-weight:900;
  cursor:pointer;
  list-style:none;
  user-select:none
}

.turnover-explain summary::-webkit-details-marker{
  display:none
}

.turnover-explain summary::after{
  content:"點擊展開 ▾";
  color:var(--muted);
  font-size:10px;
  font-weight:800;
  white-space:nowrap
}

.turnover-explain[open] summary::after{
  content:"點擊收合 ▴"
}

.turnover-explain-body{
  padding:0 13px 12px;
  border-top:1px solid var(--line);
  color:var(--muted);
  font-size:10px;
  font-weight:800;
  line-height:1.7
}

.turnover-explain-body b{
  color:var(--ink)
}

.turnover-explain-body p{
  margin:10px 0 0
}

#heatGrid.heat-volume-mode{
  display:block!important
}

#heatGrid.heat-volume-mode>.turnover-head,
#heatGrid.heat-volume-mode>.turnover-explain,
#heatGrid.heat-volume-mode>.turnover-group-switch,
#heatGrid.heat-volume-mode>.turnover-map,
#heatGrid.heat-volume-mode>.turnover-detail{
  display:block;
  width:100%;
  max-width:none;
  box-sizing:border-box
}


/* =========================================================
   TIER / 資金流出按鈕
   ========================================================= */

.turnover-group-switch{
  display:grid!important;
  grid-template-columns:repeat(auto-fit,minmax(120px,1fr))!important;
  width:100%!important;
  height:auto!important;
  min-height:0!important;
  gap:6px;
  margin:0 0 10px
}

.turnover-group-switch button{
  display:block!important;
  position:static!important;
  width:auto!important;
  min-width:0!important;
  min-height:42px!important;
  padding:7px 5px;
  border:1px solid var(--line);
  border-radius:9px;
  background:var(--soft);
  color:var(--muted);
  font:inherit;
  font-size:10px;
  font-weight:900;
  line-height:1.2;
  cursor:pointer
}

.turnover-group-switch button.active{
  background:var(--card);
  color:var(--ink);
  box-shadow:0 2px 7px rgba(15,23,42,.08)
}

.turnover-group-switch button small{
  display:block;
  margin-top:2px;
  font-size:9px;
  font-weight:900;
  opacity:.68
}


/* =========================================================
   TREEMAP
   ========================================================= */

.turnover-map{
  position:relative;
  width:100%;
  height:720px;
  overflow:hidden;
  border-radius:14px;
  background:var(--soft)
}

.turnover-box{
  position:absolute;
  box-sizing:border-box;
  padding:2px
}

.turnover-inner{
  width:100%;
  height:100%;
  box-sizing:border-box;
  display:flex;
  flex-direction:column;
  justify-content:center;
  overflow:hidden;
  padding:10px;
  border:0;
  border-radius:8px;
  color:#fff;
  text-align:left;
  font:inherit;
  cursor:pointer;
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,.18)
}

.turnover-inner.r1{background:#a65d5d}
.turnover-inner.r2{background:#c84e4e}
.turnover-inner.r3{background:#dc3b3b}
.turnover-inner.r4{background:#e52626}

.turnover-inner.g1{background:#5b7f6d}
.turnover-inner.g2{background:#418c68}
.turnover-inner.g3{background:#29975e}
.turnover-inner.g4{background:#138348}

.turnover-inner.gray{background:#687386}

.turnover-name{
  display:-webkit-box;
  -webkit-box-orient:vertical;
  -webkit-line-clamp:2;
  overflow:hidden;
  font-size:16px;
  font-weight:950;
  line-height:1.12;
  margin-bottom:5px
}

.turnover-value{
  font-size:14px;
  font-weight:900
}

.turnover-progress{
  margin-top:3px;
  font-size:13px;
  font-weight:950
}

.turnover-avg,
.turnover-market{
  margin-top:3px;
  font-size:12px;
  font-weight:850
}

.turnover-status{
  position:absolute;
  inset:0;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:28px 16px;
  color:var(--muted);
  text-align:center;
  font-size:12px;
  font-weight:800
}


/* =========================================================
   DETAIL
   ========================================================= */

.turnover-detail{
  margin-top:12px;
  border:1px solid var(--line);
  border-radius:14px;
  background:var(--card);
  overflow:hidden
}

.turnover-detail-head{
  display:flex;
  justify-content:space-between;
  gap:12px;
  padding:14px;
  border-bottom:1px solid var(--line)
}

.turnover-detail-title{
  font-size:16px;
  font-weight:950
}

.turnover-detail-meta{
  margin-top:4px;
  color:var(--muted);
  font-size:11px;
  font-weight:800
}

.turnover-detail-close{
  border:1px solid var(--line);
  border-radius:9px;
  background:var(--soft);
  color:var(--ink);
  min-width:34px;
  min-height:34px;
  font-size:18px
}

.turnover-stock{
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  gap:10px;
  align-items:center;
  padding:11px 14px;
  border-bottom:1px solid var(--line)
}

.turnover-stock:last-child{
  border-bottom:0
}

.turnover-stock.turnover-stock-top2{
  background:
    linear-gradient(
      135deg,
      rgba(254,243,199,.88),
      rgba(253,230,138,.46)
    )
}

.turnover-stock-name{
  min-width:0;
  font-size:13px;
  font-weight:900;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap
}

.turnover-stock-name small{
  margin-left:5px;
  color:var(--muted);
  font-size:10px
}

.turnover-flow-rank{
  display:inline-flex;
  margin-left:6px;
  padding:3px 6px;
  border-radius:999px;
  background:rgba(255,251,235,.96);
  color:#92400e;
  font-size:9px;
  font-weight:950
}

.turnover-stock-flow{
  margin-top:2px;
  color:var(--muted);
  font-size:10px;
  font-weight:850
}

.turnover-stock-right{
  text-align:right;
  white-space:nowrap
}

.turnover-stock-value{
  font-size:12px;
  font-weight:900
}

.turnover-stock-change{
  margin-top:2px;
  font-size:11px;
  font-weight:900
}

.turnover-stock-change.up{
  color:var(--up,#dc2626)
}

.turnover-stock-change.down{
  color:var(--down,#15803d)
}

.turnover-stock-change.flat{
  color:var(--muted)
}


/* =========================================================
   MOBILE
   ========================================================= */

@media(max-width:720px){

  .turnover-head{
    align-items:flex-start;
    flex-direction:column;
    gap:2px
  }

  .turnover-map{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    height:auto!important;
    gap:5px;
    overflow:visible
  }
  .turnover-map .turnover-box{
    position:static!important;
    width:auto!important;
    height:auto!important;
    min-width:0
  }
  .turnover-map .turnover-inner{
    min-height:150px;
    justify-content:flex-start;
    overflow:visible
  }
  .turnover-map .turnover-name{
    display:block;
    overflow:visible;
    overflow-wrap:anywhere;
    flex-shrink:0
  }

  .turnover-inner{
    padding:8px
  }

  .turnover-name{
    font-size:14px
  }

  .turnover-value{
    font-size:12px
  }

  .turnover-progress{
    font-size:11px
  }

  .turnover-avg,
  .turnover-market{
    font-size:10.5px
  }

  .turnover-group-switch{
    grid-template-columns:repeat(2,minmax(0,1fr))!important
  }

  .turnover-group-switch button{
    font-size:10px!important;
    min-height:42px!important
  }

}

`;

document.head.appendChild(s)

}


/* =========================================================
   PRICE / VOLUME SWITCH
   ========================================================= */

function ensureSwitch(){

const g=grid();

if(!g)return;

let w=$("#heatPvSwitch");

if(!w){

  w=document.createElement("div");

  w.id="heatPvSwitch";

  w.innerHTML=`
    <button data-heat-pv="price">價</button>
    <button data-heat-pv="volume">量</button>
  `;

  const p=$("#heatPeriodWrap");

  if(p&&p.parentNode===g.parentNode){
    g.parentNode.insertBefore(w,p)
  }else{
    g.parentNode.insertBefore(w,g)
  }

  w.addEventListener("click",e=>{

    const b=e.target.closest("[data-heat-pv]");

    if(b)setMode(b.dataset.heatPv)

  })

}

$$("[data-heat-pv]",w).forEach(b=>{
  b.classList.toggle(
    "active",
    b.dataset.heatPv===state.mode
  )
})

}


function setPriceControlsVisible(show){

const p=$("#heatPeriodWrap");

if(p)p.style.display=show?"":"none";

const note=$("#heatStrengthNote");

if(note&&!show)note.style.display="none"

}


function ensureStrengthNote(){

const g=grid();

if(!g)return;

let note=$("#heatStrengthNote");

if(!note){

  note=document.createElement("div");

  note.id="heatStrengthNote";

  note.innerHTML=`
    <i></i>
    <span>金色＝各族群近5日累積漲幅前2強</span>
  `;

  g.parentNode.insertBefore(note,g)

}

note.style.display=
  state.mode==="price"&&activePeriod()==="1"
    ?""
    :"none"

}


function clearGold(){

$$("#heatGrid .heat-stock-top2")
  .forEach(x=>x.classList.remove("heat-stock-top2"));

$$("#heatGrid .heat-strength-rank")
  .forEach(x=>x.remove())

}


function latest(a){

if(!Array.isArray(a))return null;

for(let i=a.length-1;i>=0;i--){

  const v=n(a[i]);

  if(v!==null)return v

}

return null

}


async function applyGold(force=false){

if(
  state.mode!=="price" ||
  activePeriod()!=="1"
){

  clearGold();
  ensureStrengthNote();
  return

}

const details=$$("#heatGrid .heat-detail");

if(!details.length)return;

let data;

try{

  data=await loadDetail(force)

}catch(e){

  return

}

clearGold();

details.forEach(d=>{

  $$(".heat-stock",d)
    .map(row=>{

      const t=
        row.dataset.ticker ||
        row.querySelector(".t")?.textContent?.trim() ||
        "";

      const s=data?.stocks?.[t];

      return{
        row,
        value:latest(
          s?.returns_by_period?.["5"] ||
          s?.returns
        )
      }

    })
    .filter(x=>x.value!==null)
    .sort((a,b)=>b.value-a.value)
    .slice(0,2)
    .forEach((x,i)=>{

      x.row.classList.add("heat-stock-top2");

      const el=x.row.querySelector(".t");

      if(el){

        const tag=document.createElement("span");

        tag.className="heat-strength-rank";

        tag.textContent=`近5日漲幅第${i+1}`;

        el.insertAdjacentElement(
          "afterend",
          tag
        )

      }

    })

});

ensureStrengthNote()

}


/* =========================================================
   FORMAT / METRIC
   ========================================================= */

function fmtYi(v){

v=n(v);

if(v===null)return"—";

const y=v/1e8;

return y>=100
  ?`${Math.round(y).toLocaleString("zh-TW")}億`
  :y>=10
    ?`${y.toFixed(0)}億`
    :`${y.toFixed(1)}億`

}


function fmtPct(v,d=1){

v=n(v);

return v===null
  ?"—"
  :`${v>0?"+":""}${v.toFixed(d)}%`

}


function flowRatio(t,a){

t=n(t);
a=n(a);

return t===null||a===null||a<=0
  ?null
  :t/a

}


function isIntraday(d){

if(typeof d?.intraday==="boolean"){
  return d.intraday
}

return !!d?.estimated

}


function metric(row,intra){
// Recalculate from raw amounts, including old cached JSON with linear estimates.
const r=flowRatio(row?.turnover,row?.avg5_turnover);
return {ratio:r,pct:r===null?null:(intra?r*100:(r-1)*100)}
}

function label(intra){
  return intra?"達全天均額":"較5日均"
}

function fmtMetric(v,intra){
  const x=n(v);
  return x===null?"—":intra?`${x.toFixed(1)}%`:fmtPct(x)
}

// Pages are ranked slices, not fixed classification thresholds.
function buildVolumeGroups(heatItems,outflowItems){
  const groups=[];
  const size=11;
  for(let offset=0;offset<heatItems.length;offset+=size){
    const page=offset/size+1;
    groups.push({key:`heat-${page}`,label:`資金熱度 Tier ${page}`,
      shortLabel:`Tier ${page}`,items:heatItems.slice(offset,offset+size)})
  }
  const pages=Math.ceil(outflowItems.length/size);
  for(let offset=0;offset<outflowItems.length;offset+=size){
    const page=offset/size+1;
    const title=pages>1?`資金流出 ${page}/${pages}`:"資金流出";
    groups.push({key:`outflow-${page}`,label:title,shortLabel:title,
      items:outflowItems.slice(offset,offset+size)})
  }
  return groups
}

/* =========================================================
   資金流出定義
   ========================================================= */

/*
   資金流出：
   1. 族群今日漲跌 < 0%
   2. 成交動能 ratio >= 1.10

   盤中：
   使用累積成交額 / 五日全天均額 ratio（不作時間推估）

   盤後：
   使用今日成交額 / 近5日平均成交額
*/

function isCapitalOutflow(metricRatio,change){

const r=n(metricRatio);
const c=n(change);

return(
  r!==null &&
  c!==null &&
  r>=1.10 &&
  c<0
)

}


/* =========================================================
   COLOR
   ========================================================= */

function heatColor(v){

v=n(v);

if(v===null)return"gray";

const a=Math.abs(v);

const l=
  a>=3?4:
  a>=2?3:
  a>=1?2:
  1;

return`${v>=0?"r":"g"}${l}`

}


/* =========================================================
   TREEMAP
   ========================================================= */

function sectorMap(h){

const m=new Map;

(h?.sectors||[]).forEach(s=>{
  m.set(s.name,s)
});

return m

}


function sumArea(r){
  return r.reduce(
    (s,x)=>s+x._area,
    0
  )
}


function worst(r,side){

if(!r.length||side<=0){
  return Infinity
}

const sum=sumArea(r);

const max=Math.max(
  ...r.map(x=>x._area)
);

const p=r
  .map(x=>x._area)
  .filter(x=>x>0);

const min=p.length
  ?Math.min(...p)
  :0;

if(!sum||!min){
  return Infinity
}

return Math.max(
  side*side*max/(sum*sum),
  (sum*sum)/(side*side*min)
)

}


function layoutRow(row,rect,out){

const area=sumArea(row);

if(!row.length||area<=0){
  return rect
}

if(rect.w>=rect.h){

  const sw=area/rect.h;

  let y=rect.y;

  row.forEach((it,i)=>{

    const h=
      i===row.length-1
        ?rect.y+rect.h-y
        :it._area/sw;

    out.push({
      ...it,
      xPx:rect.x,
      yPx:y,
      wPx:sw,
      hPx:h
    });

    y+=h

  });

  return{
    x:rect.x+sw,
    y:rect.y,
    w:Math.max(0,rect.w-sw),
    h:rect.h
  }

}

const sh=area/rect.w;

let x=rect.x;

row.forEach((it,i)=>{

  const w=
    i===row.length-1
      ?rect.x+rect.w-x
      :it._area/sh;

  out.push({
    ...it,
    xPx:x,
    yPx:rect.y,
    wPx:w,
    hPx:sh
  });

  x+=w

});

return{
  x:rect.x,
  y:rect.y+sh,
  w:rect.w,
  h:Math.max(0,rect.h-sh)
}

}


function squarify(items,w,h){

const a=[...items]
  .filter(x=>x.value>0)
  .sort((a,b)=>b.value-a.value);

const total=a.reduce(
  (s,x)=>s+x.value,
  0
);

if(!total)return[];

const work=a.map(x=>({
  ...x,
  _area:x.value/total*w*h
}));

let rect={
  x:0,
  y:0,
  w,
  h
};

let row=[];
let i=0;
let out=[];

while(i<work.length){

  const it=work[i];

  const side=Math.min(
    rect.w,
    rect.h
  );

  if(!row.length){

    row.push(it);
    i++;
    continue

  }

  if(
    worst([...row,it],side) <=
    worst(row,side)
  ){

    row.push(it);
    i++

  }else{

    rect=layoutRow(
      row,
      rect,
      out
    );

    row=[]

  }

}

if(row.length){
  layoutRow(
    row,
    rect,
    out
  )
}

return out.map(x=>({
  ...x,
  x:x.xPx/w*100,
  y:x.yPx/h*100,
  width:x.wPx/w*100,
  height:x.hPx/h*100
}))

}


function mapHeight(w){

return window.innerWidth<=720
  ?Math.round(
      Math.max(
        500,
        Math.min(650,w*1.34)
      )
    )
  :window.innerWidth<=1100
    ?Math.round(
        Math.max(
          560,
          Math.min(720,w*.76)
        )
      )
    :Math.round(
        Math.max(
          600,
          Math.min(760,w*.58)
        )
      )

}


/* =========================================================
   BOX
   ========================================================= */

function boxContent(x,intra){

return`
  <div class="turnover-name">
    ${esc(x.name)}
  </div>

  <div class="turnover-value">
    成交 ${fmtYi(x.turnover)}
  </div>

  <div class="turnover-progress">
    ${label(intra)} ${fmtMetric(x.metricPct,intra)}
  </div>

  <div class="turnover-avg">
    5日均 ${fmtYi(x.avg5_turnover)}
  </div>

  <div class="turnover-market">
    今日 ${fmtPct(x.change,2)}
  </div>
`

}


/* =========================================================
   SECTOR DETAIL
   ========================================================= */

function renderSectorDetail(name,t,h){

const d=$("#turnoverDetail");

if(!d)return;

const sec=(h?.sectors||[])
  .find(x=>x.name===name);

const ts=(t?.sectors||[])
  .find(x=>x.name===name);

if(!sec||!ts){

  d.hidden=true;
  return

}

const intra=isIntraday(t);

const sm=new Map;

(t?.stocks||[]).forEach(x=>{
  sm.set(
    String(x.ticker),
    x
  )
});

const smetric=metric(
  ts,
  intra
);

const outflow=isCapitalOutflow(
  smetric.ratio,
  n(sec.change_pct)
);

const rows=(sec.stocks||[])
  .map(s=>{

    const tr=sm.get(
      String(s.ticker)
    );

    const m=metric(
      tr,
      intra
    );

    return{
      ticker:s.ticker,
      name:s.name||s.ticker,
      turnover:n(tr?.turnover),
      avg:n(tr?.avg5_turnover),
      mr:m.ratio,
      mp:m.pct,
      change:n(s.change_pct)
    }

  })
  .sort(
    (a,b)=>
      (b.mr??-Infinity)-
      (a.mr??-Infinity) ||
      (b.turnover||0)-
      (a.turnover||0)
  );

rows.forEach((r,i)=>{
  r.rank=
    i<2 &&
    r.mr!==null
      ?i+1
      :null
});

d.hidden=false;

d.innerHTML=`

<div class="turnover-detail-head">

  <div>

    <div class="turnover-detail-title">
      ${esc(name)}
    </div>

    <div class="turnover-detail-meta">
      成交 ${fmtYi(ts.turnover)}
      ｜${label(intra)} ${fmtMetric(smetric.pct,intra)}
      ｜5日均 ${fmtYi(ts.avg5_turnover)}
      ｜今日 ${fmtPct(sec.change_pct,2)}
      ${outflow?"｜資金流出":""}
    </div>

  </div>

  <button class="turnover-detail-close">
    ×
  </button>

</div>

<div>

${rows.map(r=>`

<div class="
  turnover-stock
  ${r.rank?"turnover-stock-top2":""}
">

  <div>

    <div class="turnover-stock-name">

      ${esc(r.name)}

      <small>
        ${esc(r.ticker)}
      </small>

      ${
        r.rank
          ?`
            <span class="turnover-flow-rank">
              ${label(intra)}第${r.rank}
            </span>
          `
          :""
      }

    </div>

    <div class="turnover-stock-flow">
      ${label(intra)} ${fmtMetric(r.mp,intra)}
      ｜5日均 ${fmtYi(r.avg)}
    </div>

  </div>

  <div class="turnover-stock-right">

    <div class="turnover-stock-value">
      成交 ${fmtYi(r.turnover)}
    </div>

    <div class="
      turnover-stock-change
      ${
        r.change>0
          ?"up"
          :r.change<0
            ?"down"
            :"flat"
      }
    ">
      今日 ${fmtPct(r.change,2)}
    </div>

  </div>

</div>

`).join("")}

</div>

`;

$(".turnover-detail-close",d)
  ?.addEventListener(
    "click",
    ()=>{

      state.selectedSector=null;

      d.hidden=true;
      d.innerHTML=""

    }
  );

requestAnimationFrame(()=>{
  d.scrollIntoView({
    behavior:"smooth",
    block:"nearest"
  })
})

}


/* =========================================================
   VOLUME MODE
   ========================================================= */

async function renderVolume(force=false){

if(state.mode!=="volume"){
  return
}

const g=grid();

if(!g)return;

g.classList.add(
  "heat-volume-mode"
);

const token=
  ++state.volumeRenderToken;

state.renderingVolume=true;

setPriceControlsVisible(false);

clearGold();

g.innerHTML=`
  <div class="turnover-status">
    成交金額資料載入中…
  </div>
`;

try{

  const[t,h]=await Promise.all([
    loadTurnover(force),
    fetchJson(
      "./data/heatmap.json",
      force
    )
  ]);

  if(
    state.mode!=="volume" ||
    token!==state.volumeRenderToken
  )return;

  const intra=isIntraday(t);

  const hm=sectorMap(h);


  /* =======================================================
     建立所有族群資料
     ======================================================= */

  const items=(t?.sectors||[])
    .map(s=>{

      const m=metric(
        s,
        intra
      );

      const change=n(
        hm.get(s.name)?.change_pct
      );

      const outflow=
        isCapitalOutflow(
          m.ratio,
          change
        );

      return{
        ...s,

        metricRatio:m.ratio,
        metricPct:m.pct,

        value:
          m.ratio===null
            ?0
            :Math.max(
                .05,
                Math.min(
                  m.ratio,
                  3
                )
              ),

        change,
        outflow

      }

    })
    .filter(x=>x.value>0);


  if(!items.length){

    g.innerHTML=`
      <div class="turnover-status">
        目前沒有成交金額資料
      </div>
    `;

    return

  }


  /*
     所有排序都以成交動能為主：

     盤中：
     累積成交額 / 五日全天均額

     盤後：
     今日成交 / 5日均
  */

  items.sort(
    (a,b)=>
      (b.metricRatio??-Infinity)-
      (a.metricRatio??-Infinity)
  );


  /* =======================================================
     先抽出資金流出
     ======================================================= */

  const outflowItems=items
    .filter(x=>x.outflow)
    .sort(
      (a,b)=>
        (b.metricRatio??-Infinity)-
        (a.metricRatio??-Infinity)
    );


  /*
     資金流出族群不再重複出現在 Tier
  */

  const heatItems=items
    .filter(x=>!x.outflow)
    .sort(
      (a,b)=>
        (b.metricRatio??-Infinity)-
        (a.metricRatio??-Infinity)
    );


  /* =======================================================
     每 Tier 最多 11 個
     ======================================================= */

  const groups=buildVolumeGroups(heatItems,outflowItems);
  // Preserve category/page through refreshes, not its shifting array index.
  let active=groups.findIndex(x=>x.key===state.volumeGroupKey);
  if(active<0 && state.volumeGroupKey){
    const category=state.volumeGroupKey.split("-")[0];
    const candidates=groups.map((x,i)=>({x,i})).filter(({x})=>x.key.startsWith(category+"-"));
    if(candidates.length)active=candidates[candidates.length-1].i;
  }
  state.volumeGroup=active>=0?active:0;
  state.volumeGroupKey=groups[state.volumeGroup]?.key||null;


  const sub=intra
    ?"依目前成交額占五日全天均額排序（不預估全天）"
    :"依成交相對5日均排序族群資金熱度";


  /* =======================================================
     判讀邏輯
     預設收合
     ======================================================= */

  const exp=`

    <details class="turnover-explain">

      <summary>
        <span>判讀邏輯</span>
      </summary>

      <div class="turnover-explain-body">

        <p>
          <b>資金流出</b>：
          族群今日下跌，且成交動能較近 5 日平均
          <b>放大 10% 以上</b>
        </p>

        <p>
          ${
            intra
              ?`
                盤中以「目前累積成交額 ÷ 近 5 日全天平均成交額」判斷，
                不依開盤分鐘放大、不預估全天成交額。實際累積達均額的
                <b>110% 以上</b>
              `
              :`
                盤後以「今日成交額 ÷ 近 5 日平均成交額」
                判斷，達
                <b>110% 以上</b>
              `
          }
        </p>

        <p>
          符合條件的資金流出族群依<b>成交倍率由高至低</b>排序；
          Tier 與資金流出各自每 11 個族群自動分頁，空分類不顯示。
          盤中缺少歷史同時間資料，達全天均額不代表同時間放量；
          判斷較保守。盤中成交額仍為價格乘累積成交量的估值，非實際成交淨流向
        </p>

      </div>

    </details>

  `;


  g.innerHTML=`

    <div class="turnover-head">

      <div>

        <div class="turnover-head-main">
          族群資金熱度
        </div>

        <div class="turnover-head-sub">
          ${sub}
        </div>

      </div>

      <div class="turnover-date">
        ${esc(t.updated_at||t.date||"")}
      </div>

    </div>


    ${exp}


    <div
      class="turnover-group-switch"
      id="turnoverGroupSwitch"
    ></div>


    <div
      class="turnover-map"
      id="turnoverMap"
    ></div>


    <div
      class="turnover-detail"
      id="turnoverDetail"
      hidden
    ></div>

  `;


  const map=$(
    "#turnoverMap",
    g
  );

  const sw=$(
    "#turnoverGroupSwitch",
    g
  );

  const width=Math.max(
    280,
    Math.floor(
      map.getBoundingClientRect().width ||
      g.clientWidth ||
      360
    )
  );


  /* =======================================================
     TIER 按鈕
     ======================================================= */

  function renderSwitch(){

    sw.innerHTML=
      groups
        .map((grp,i)=>`

          <button
            data-turnover-group="${i}"
            class="${
              i===state.volumeGroup
                ?"active"
                :""
            }"
          >
            ${esc(grp.shortLabel)}

            <small>
              ${grp.items.length} 個族群
            </small>

          </button>

        `)
        .join("")

  }


  /* =======================================================
     每組重新使用完整畫布計算 Treemap
     ======================================================= */

  function renderMap(){

    const grp=
      groups[state.volumeGroup] ||
      groups[0];

    const list=
      grp?.items ||
      [];

    const height=
      mapHeight(width);

    map.style.height=
      `${height}px`;


    if(!list.length){

      map.innerHTML=`

        <div class="turnover-status">

          ${
            state.volumeGroup===3
              ?"今日目前沒有符合條件的資金流出族群"
              :"目前沒有族群資料"
          }

        </div>

      `;

      return

    }


    map.innerHTML=
      squarify(
        list,
        width,
        height
      )
      .map(x=>`

        <div
          class="turnover-box"
          style="
            left:${x.x}%;
            top:${x.y}%;
            width:${x.width}%;
            height:${x.height}%
          "
        >

          <button
            class="
              turnover-inner
              ${heatColor(x.change)}
            "
            data-turnover-sector="${esc(x.name)}"
          >

            ${boxContent(x,intra)}

          </button>

        </div>

      `)
      .join("")

  }


  renderSwitch();
  renderMap();


  /* =======================================================
     TIER / 資金流出切換
     ======================================================= */

  sw.addEventListener(
    "click",
    e=>{

      const b=
        e.target.closest(
          "[data-turnover-group]"
        );

      if(!b)return;

      state.volumeGroup=
        Number(
          b.dataset.turnoverGroup
        );

      state.volumeGroupKey=groups[state.volumeGroup]?.key||null;
      state.selectedSector=null;

      const d=$(
        "#turnoverDetail",
        g
      );

      if(d){

        d.hidden=true;
        d.innerHTML=""

      }

      renderSwitch();
      renderMap()

    }
  );


  /* =======================================================
     點族群
     ======================================================= */

  map.addEventListener(
    "click",
    e=>{

      const b=
        e.target.closest(
          "[data-turnover-sector]"
        );

      if(!b)return;

      state.selectedSector=
        b.dataset.turnoverSector;

      renderSectorDetail(
        state.selectedSector,
        t,
        h
      )

    }
  );


  if(state.selectedSector){

    renderSectorDetail(
      state.selectedSector,
      t,
      h
    )

  }


}catch(e){

  console.error(
    "[turnover heatmap]",
    e
  );

  if(
    state.mode==="volume" &&
    token===state.volumeRenderToken
  ){

    g.innerHTML=`
      <div class="turnover-status">
        成交金額資料讀取失敗
      </div>
    `

  }

}finally{

  state.renderingVolume=false

}

}


/* =========================================================
   PRICE MODE
   ========================================================= */

function restorePrice(){

state.volumeRenderToken++;

state.selectedSector=null;

const g=grid();

if(g){
  g.classList.remove(
    "heat-volume-mode"
  )
}

setPriceControlsVisible(true);

if(
  typeof window.renderHeatCurrentPeriod===
  "function"
){
  window.renderHeatCurrentPeriod()
}

requestAnimationFrame(()=>{

  ensureSwitch();

  ensureStrengthNote();

  setTimeout(
    ()=>applyGold(false),
    80
  )

})

}


function setMode(m){

if(
  !["price","volume"].includes(m)
)return;

state.mode=m;

ensureSwitch();

if(m==="volume"){

  renderVolume(true)

}else{

  restorePrice()

}

}


/* =========================================================
   OBSERVER
   ========================================================= */

function observeGrid(){

const g=grid();

if(!g)return;

state.observer?.disconnect();

state.observer=
  new MutationObserver(()=>{

    if(state.renderingVolume){
      return
    }

    if(state.mode==="volume"){

      if(
        !g.querySelector(
          ".turnover-map"
        )
      ){
        renderVolume(false)
      }

      return

    }

    clearTimeout(
      state.goldTimer
    );

    state.goldTimer=
      setTimeout(
        ()=>applyGold(false),
        80
      )

  });

state.observer.observe(
  g,
  {
    childList:true,
    subtree:true
  }
)

}


/* =========================================================
   BIND
   ========================================================= */

function bind(){

injectStyle();

ensureSwitch();

ensureStrengthNote();

observeGrid();


window.addEventListener(
  "heatmap:period-changed",
  ()=>{

    if(state.mode==="price"){

      setTimeout(
        ()=>applyGold(false),
        60
      )

    }

  }
);


window.addEventListener(
  "heatmap:data-updated",
  ()=>{

    state.detail=null;
    state.turnover=null;

    if(state.mode==="volume"){

      renderVolume(true)

    }else{

      setTimeout(
        ()=>applyGold(true),
        80
      )

    }

  }
);


window.addEventListener(
  "resize",
  ()=>{

    if(state.mode==="volume"){

      clearTimeout(
        state.resizeTimer
      );

      state.resizeTimer=
        setTimeout(
          ()=>renderVolume(false),
          180
        )

    }

  },
  {
    passive:true
  }
);


/*
   量模式每分鐘更新
*/

setInterval(
  ()=>{

    if(state.mode==="volume"){

      state.turnover=null;

      renderVolume(true)

    }

  },
  60000
);


setTimeout(
  ()=>applyGold(false),
  200
)

}


if(
  document.readyState==="loading"
){

document.addEventListener(
  "DOMContentLoaded",
  bind,
  {
    once:true
  }
)

}else{

bind()

}


/* =========================================================
   EXPOSE
   ========================================================= */

window.getHeatmapDisplayMode=
  ()=>state.mode;

window.setHeatmapDisplayMode=
  setMode;

window.refreshTurnoverHeatmap=
  f=>renderVolume(!!f);

window.refreshHeatStrength=
  f=>applyGold(!!f);

})();

