const $=s=>document.querySelector(s), $$=s=>document.querySelectorAll(s);
const st={period:"1d",inst:"foreign",market:"twse",turn:"twse",hm:"twse",hk:"400",aim:"twse",advanced:false};
const cache={};

async function J(p){
  try{
    let u=p;
    if(p.startsWith("./data/")){
      u="https://raw.githubusercontent.com/Morris199786/tw-market-monitor/main/"+p.slice(2);
    }
    let r=await fetch(
      u+(u.includes("?")?"&":"?")+"v="+Date.now(),
      {cache:"no-store"}
    );
    if(!r.ok) throw 0;
    return await r.json();
  }catch(e){
    return {};
  }
}

function pct(v){
  if(v===null||v===undefined)return"—";
  v=Number(v);
  return(v>0?"+":"")+v.toFixed(2)+"%";
}

function cl(v){
  return Number(v)>=0?"up":"down";
}

function money(v){
  return(v>0?"+":"")+Number(v||0).toFixed(2)+"億";
}

function stock(x,rank){
  return`${rank?`<span class="rank">${rank}</span>`:""}
  <span class="stock">
    <b>${x.name||""}</b>
    <span>${x.ticker||""}</span>
  </span>`;
}

function page(id){
  $$(".page").forEach(x=>x.classList.toggle("active",x.id===id));
  $$(".nav").forEach(x=>x.classList.toggle("active",x.dataset.p===id));

  const mobile=$("#mobileNav");
  if(mobile) mobile.value=id;

  scrollTo(0,0);
}

$$(".nav").forEach(b=>b.onclick=()=>page(b.dataset.p));

const mobileNav=$("#mobileNav");
if(mobileNav){
  mobileNav.onchange=e=>page(e.target.value);
}

function clock(){
  const c=$("#clock");
  if(!c)return;

  c.textContent=new Intl.DateTimeFormat(
    "zh-TW",
    {
      timeZone:"Asia/Taipei",
      year:"numeric",
      month:"2-digit",
      day:"2-digit",
      hour:"2-digit",
      minute:"2-digit"
    }
  ).format(new Date());
}

clock();
setInterval(clock,30000);

function heatClass(v){
  if(v===null||v===undefined)return"gray";

  let a=Math.abs(v);

  if(v>=0){
    return a>=3?"r4":a>=2?"r3":a>=1?"r2":"r1";
  }

  return a>=3?"g4":a>=2?"g3":a>=1?"g2":"g1";
}

async function home(){
  let h=await J("./data/heatmap.json");
  let a=await J("./data/ai_picks.json");
  let ho=await J("./data/holders.json");

  let s=[...(h.sectors||[])]
    .filter(x=>x.change_pct!==null&&x.change_pct!==undefined)
    .sort((x,y)=>y.change_pct-x.change_pct);

  let top=s.slice(0,3);

  const homeCards=$("#homeCards");
  if(homeCards){
    homeCards.innerHTML=`
      <div class="card metric">
        <small>市場熱力圖</small>
        <strong>19 族群</strong>
        <small>每 5 分鐘</small>
      </div>

      <div class="card metric">
        <small>AI 選股</small>
        <strong>18:00</strong>
        <small>每日更新</small>
      </div>

      <div class="card metric">
        <small>大戶籌碼</small>
        <strong>週六 15:00</strong>
        <small>${ho.complete?"資料完整":"等待兩期資料"}</small>
      </div>

      <div class="card metric">
        <small>最強族群</small>
        <strong>${top[0]?.name||"—"}</strong>
        <small class="${cl(top[0]?.change_pct)}">
          ${top[0]?pct(top[0].change_pct):"—"}
        </small>
      </div>
    `;
  }

  const topSectors=$("#topSectors");
  if(topSectors){
    topSectors.innerHTML=top.map((x,i)=>`
      <div class="card metric">
        <small>0${i+1} ${x.name}</small>
        <strong class="${cl(x.change_pct)}">
          ${pct(x.change_pct)}
        </strong>
        <small>
          ${x.complete?"完整市值加權":"部分成分股缺資料"}
        </small>
      </div>
    `).join("");
  }
}

async function flows(){
  let d=await J("./data/institutional.json");

  const flowDate=$("#flowDate");
  if(flowDate){
    flowDate.textContent=d.date?`截至 ${d.date}`:"尚無資料";
  }

  let g=d.periods?.[st.period]?.[st.market]?.[st.inst]||{
    buy:[],
    sell:[],
    complete:false,
    days_used:0
  };

  const flowStatus=$("#flowStatus");

  if(flowStatus){
    flowStatus.className="status"+(g.complete?"":" warn");

    flowStatus.textContent=g.complete
      ?`資料完整 · ${g.days_used} 個交易日`
      :`資料尚未累積完整：目前 ${g.days_used||0} / ${
        st.period==="1d"?1:st.period==="3d"?3:5
      } 個交易日`;
  }

  function rows(a){
    return(a||[]).map((x,i)=>`
      <tr class="${x.change_pct<0?"negative-row":""}">
        <td>${stock(x,i+1)}</td>
        <td class="${x.amount_100m>=0?"up":"down"}">
          ${money(x.amount_100m)}
        </td>
        <td>
          ${Math.round((x.shares||0)/1000).toLocaleString()}
        </td>
        <td class="${cl(x.change_pct)}">
          ${pct(x.change_pct)}
        </td>
      </tr>
    `).join("");
  }

  const buy=$("#buyRows");
  const sell=$("#sellRows");

  if(buy) buy.innerHTML=rows(g.buy);
  if(sell) sell.innerHTML=rows(g.sell);
}

$$("[data-period]").forEach(b=>b.onclick=()=>{
  $$("[data-period]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  st.period=b.dataset.period;
  flows();
});

$$("[data-inst]").forEach(b=>b.onclick=()=>{
  $$("[data-inst]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  st.inst=b.dataset.inst;
  flows();
});

$$("[data-market]").forEach(b=>b.onclick=()=>{
  $$("[data-market]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  st.market=b.dataset.market;
  flows();
});

async function volume(){
  let v=await J("./data/volume.json");
  let s=await J("./data/screener.json");

  const volDate=$("#volDate");
  if(volDate){
    volDate.textContent=v.date||"尚無資料";
  }

  let d=st.advanced?s.items:v.items;

  const volStatus=$("#volStatus");

  if(volStatus){
    volStatus.className="status"+(
      (st.advanced?!s.complete:!v.complete)
      ?" warn":""
    );

    volStatus.textContent=st.advanced
      ?(
        s.complete
        ?"進階篩選：20D歷史完整"
        :`進階篩選需要21個交易日，目前 ${s.history_days||0}`
      )
      :(
        v.complete
        ?"前五日量比資料完整"
        :`突然放量需要6個交易日，目前 ${v.history_days||0}`
      );
  }

  const volRows=$("#volRows");

  if(volRows){
    volRows.innerHTML=(d||[]).map((x,i)=>`
      <tr class="${x.change_pct<0?"negative-row":""}">
        <td>${stock(x,i+1)}</td>
        <td class="${cl(x.change_pct)}">
          ${pct(x.change_pct)}
        </td>
        <td>
          ${Math.round((x.volume||0)/1000).toLocaleString()}張
        </td>
        <td>
          ${Number(x.volume_ratio_5d||0).toFixed(2)}x
        </td>
        <td>
          ${
            st.advanced
            ?`${Number(x.volume_ratio_20d||0).toFixed(2)}x / ${x.avg3}>${x.avg5}>${x.avg10}`
            :(x.low_base?"低基期":"—")
          }
        </td>
      </tr>
    `).join("");
  }
}

const advanced=$("#advanced");

if(advanced){
  advanced.onclick=()=>{
    st.advanced=!st.advanced;

    advanced.classList.toggle("active",st.advanced);

    advanced.textContent=st.advanced
      ?"進階篩選 ✓"
      :"進階篩選 ＋";

    volume();
  };
}

async function turnover(){
  let d=await J("./data/turnover.json");

  const turnDate=$("#turnDate");

  if(turnDate){
    turnDate.textContent=d.date||"尚無資料";
  }

  const turnRows=$("#turnRows");

  if(turnRows){
    turnRows.innerHTML=(d[st.turn]||[]).map((x,i)=>`
      <tr class="${x.change_pct<0?"negative-row":""}">
        <td>${stock(x,i+1)}</td>
        <td>
          ${(Number(x.turnover||0)/1e8).toFixed(2)}億
        </td>
        <td>
          ${Math.round(Number(x.volume||0)/1000).toLocaleString()}
        </td>
        <td>${x.price||"—"}</td>
        <td class="${cl(x.change_pct)}">
          ${pct(x.change_pct)}
        </td>
      </tr>
    `).join("");
  }
}

$$("[data-turn]").forEach(b=>b.onclick=()=>{
  $$("[data-turn]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  st.turn=b.dataset.turn;
  turnover();
});

async function holders(){
  let d=await J("./data/holders.json");

  const holderDate=$("#holderDate");

  if(holderDate){
    holderDate.textContent=d.date
      ?`${d.date}｜週六 15:00`
      :"週六 15:00";
  }

  const holderStatus=$("#holderStatus");

  if(holderStatus){
    holderStatus.className="status"+(d.complete?"":" warn");

    holderStatus.textContent=d.complete
      ?`比較 ${d.previous_date} → ${d.date}`
      :"首次部署需累積兩期集保快照；有第二期後自動開始排名";
  }

  const holderRows=$("#holderRows");

  if(holderRows){
    holderRows.innerHTML=(d[st.hm]?.[st.hk]||[]).map((x,i)=>`
      <tr class="${x.week_change_pct<0?"negative-row":""}">
        <td>${stock(x,i+1)}</td>
        <td class="${cl(x.week_change_pct)}">
          ${pct(x.week_change_pct)}
        </td>
        <td>
          ${Number(x.ratio).toFixed(2)}%
        </td>
        <td class="up">
          +${Number(x.delta).toFixed(2)}ppt
        </td>
      </tr>
    `).join("");
  }
}

$$("[data-hm]").forEach(b=>b.onclick=()=>{
  $$("[data-hm]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  st.hm=b.dataset.hm;
  holders();
});

$$("[data-hk]").forEach(b=>b.onclick=()=>{
  $$("[data-hk]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  st.hk=b.dataset.hk;
  holders();
});

async function ai(){
  let d=await J("./data/ai_picks.json");

  const aiStatus=$("#aiStatus");

  if(aiStatus){
    aiStatus.className="status"+(d.complete?"":" warn");

    aiStatus.textContent=d.complete
      ?`${d.mode==="sunday"?"週日版":"交易日版"} · 資料完整`
      :"資料尚未累積完整；排行只會使用目前已取得的來源";
  }

  const aiCards=$("#aiCards");

  if(aiCards){
    aiCards.innerHTML=(d[st.aim]||[]).map((x,i)=>`
      <div class="card aicard">
        <div class="aitop">
          <div>${stock(x,null)}</div>
          <div class="score">${x.score}</div>
        </div>

        <div class="tags">
          ${(x.tags||[]).map(t=>`
            <span class="tag">${t}</span>
          `).join("")}
        </div>

        <div class="reason">
          ${x.reason}
        </div>
      </div>
    `).join("");

    $$(".aicard").forEach(x=>{
      x.onclick=()=>x.classList.toggle("open");
    });
  }
}

$$("[data-aim]").forEach(b=>b.onclick=()=>{
  $$("[data-aim]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active");
  st.aim=b.dataset.aim;
  ai();
});

async function heat(){
  let d=await J("./data/heatmap.json");

  cache.heat=d;

  const heatTime=$("#heatTime");

  if(heatTime){
    heatTime.textContent=d.updated_at||"尚無資料";
  }

  const heatGrid=$("#heatGrid");

  if(heatGrid){
    heatGrid.innerHTML=(d.sectors||[]).map((x,i)=>`
      <button
        class="heat ${
          i===1
          ?"s5 tall"
          :i===11
          ?"s6 tall"
          :i%3===0
          ?"s4"
          :"s3"
        } ${heatClass(x.change_pct)}"
        data-sec="${x.name}"
      >
        <b>${x.name}</b>
        <strong>${pct(x.change_pct)}</strong>
        <small>
          ${
            x.complete
            ?`${x.stocks.length}檔`
            :`缺${x.missing?.length||0}檔`
          }
        </small>
      </button>
    `).join("");

    $$("[data-sec]").forEach(b=>{
      b.onclick=()=>showSec(b.dataset.sec);
    });
  }

  if(d.sectors?.length){
    showSec(d.sectors[0].name);
  }
}

function showSec(n){
  let s=cache.heat?.sectors?.find(x=>x.name===n);

  if(!s)return;

  const heatTitle=$("#heatTitle");

  if(heatTitle){
    heatTitle.textContent=`${s.name} ${pct(s.change_pct)}`;
  }

  let a=[...(s.stocks||[])].sort(
    (x,y)=>(y.change_pct??-999)-(x.change_pct??-999)
  );

  const heatRows=$("#heatRows");

  if(heatRows){
    heatRows.innerHTML=a.map(x=>`
      <tr class="${x.change_pct<0?"negative-row":""}">
        <td>${stock(x)}</td>
        <td>${x.price??"—"}</td>
        <td class="${
          x.change_pct===null||x.change_pct===undefined
          ?""
          :cl(x.change_pct)
        }">
          ${pct(x.change_pct)}
        </td>
        <td>
          ${
            x.weight===null||x.weight===undefined
            ?"缺資料"
            :(x.weight*100).toFixed(1)+"%"
          }
        </td>
      </tr>
    `).join("");
  }
}

async function reports(){
  let d=await J("./data/reports.json");

  let map={
    upgrade:"上調",
    downgrade:"下調",
    initiate:"初評",
    maintain:"維持"
  };

  const reportList=$("#reportList");

  if(!reportList)return;

  if((d.items||[]).length){
    reportList.innerHTML=(d.items||[]).map(r=>`
      <div class="report">
        <div class="broker">
          ${r.broker||""}
        </div>

        <div class="rmain">
          <div class="rtitle">
            ${r.broker||""}
            ${map[r.action]||r.action||""}
            ${r.name||""}
            ${r.ticker||""}
          </div>

          <div class="rmeta">
            ${r.summary||""}
            ${r.date?` · ${r.date}`:""}
          </div>
        </div>

        <div class="tp">
          ${
            r.target_price
            ?`目標價 ${r.target_price}`
            :""
          }
        </div>
      </div>
    `).join("");
  }else{
    reportList.innerHTML=`
      <div class="report">
        <div class="rmain">
          <div class="rtitle">
            尚無券商報告
          </div>
          <div class="rmeta">
            收到 PDF 或連結後，把整理結果寫入 data/reports.json 即會顯示
          </div>
        </div>
      </div>
    `;
  }
}

async function init(){
  await Promise.all([
    home(),
    flows(),
    volume(),
    turnover(),
    holders(),
    ai(),
    heat(),
    reports()
  ]);
}

init();
