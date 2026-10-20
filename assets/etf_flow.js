(()=>{'use strict';

const css=`
.etf-switch{display:flex;gap:9px;margin:14px 0}
.etf-switch button,.etf-controls button{background:#243349;color:#e7efff;border:1px solid #50617a;border-radius:10px;padding:10px 16px;font-weight:700;cursor:pointer}
.etf-switch button.on,.etf-controls button.on{background:#2563eb;color:white}
.etf-flow{color:inherit}
.etf-flow[hidden],.etf-old[hidden]{display:none!important}
.etf-controls{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}
.etf-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
.etf-card,.etf-box{border:1px solid #46536a;border-radius:12px;padding:15px;background:rgba(96,115,146,.08)}
.etf-card strong{display:block;font-size:23px;margin-top:7px}
.etf-lists{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}
.etf-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
.etf-table th,.etf-table td{padding:9px 6px;border-bottom:1px solid #6c789044;text-align:right}
.etf-table th:first-child,.etf-table td:first-child{text-align:left}
.etf-table tr[data-code]{cursor:pointer}
.etf-table tr[data-code]:hover{background:#627aa02b}
.etf-pos{color:#ef6464}
.etf-neg{color:#32b985}
.etf-detail{margin-top:14px}
.etf-chart{width:100%;height:250px;display:block}
.etf-note{opacity:.75;font-size:13px;line-height:1.6}

@media(max-width:760px){
  .etf-lists{grid-template-columns:1fr}
  .etf-cards{grid-template-columns:repeat(3,minmax(0,1fr))}
  .etf-card{padding:10px}
  .etf-card strong{font-size:18px}
}`;

const st=document.createElement('style');
st.textContent=css;
document.head.append(st);

const container=
  document.querySelector('#institutional')||
  Array.from(document.querySelectorAll('section.page'))
    .find(s=>s.textContent.includes('籌碼日報'));

if(!container){
  console.warn('ETF 00981A: cannot locate institutional page');
  return;
}

const switcher=document.createElement('div');
switcher.className='etf-switch';
switcher.innerHTML=`
  <button class="on" type="button" data-etf-tab="original">三大法人</button>
  <button type="button" data-etf-tab="etf">主動式 ETF</button>
`;

const anchor=container.querySelector('.hero');
(anchor?anchor.after.bind(anchor):container.prepend.bind(container))(switcher);

const old=document.createElement('div');
old.className='etf-old';

while(switcher.nextSibling){
  old.appendChild(switcher.nextSibling);
}

container.appendChild(old);

const root=document.createElement('div');
root.className='etf-flow';
root.hidden=true;
container.appendChild(root);

let dataset=null;
let period=1;
let selected=null;

const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({
  '&':'&amp;',
  '<':'&lt;',
  '>':'&gt;',
  '"':'&quot;',
  "'":'&#39;'
}[c]));

const fmt=n=>Math.round(n).toLocaleString('zh-TW');

function calc(){

  const dates=Object.keys(dataset.snapshots||{}).sort();
  const end=dates.at(-1);

  if(!end)return null;

  const begin=dates[Math.max(0,dates.length-1-period)];

  const current=dataset.snapshots[end];

  const previous=dates.length>1
    ?dataset.snapshots[begin]||{}
    :current;

  const rows=[
    ...new Set([
      ...Object.keys(current),
      ...Object.keys(previous)
    ])
  ].map(code=>{

    const a=current[code];
    const b=previous[code];

    const delta=(a?.shares||0)-(b?.shares||0);

    return{
      code,
      name:a?.name||b?.name||code,
      shares:a?.shares||0,
      weight:a?.weight||0,
      delta,
      ratio:b?.shares?delta/b.shares*100:null
    };
  });

  return{
    dates,
    end,
    begin,
    rows,
    valid:dates.length>period
  };
}

function render(){

  if(!dataset){
    root.innerHTML=`
      <div class="etf-box">
        正在載入 00981A 持股資料…
      </div>
    `;
    return;
  }

  const z=calc();

  if(!z){
    root.innerHTML=`
      <div class="etf-box">
        目前沒有可用的持股快照，請先執行 ETF 更新排程
      </div>
    `;
    return;
  }

  const adds=z.rows
    .filter(x=>x.delta>0)
    .sort((a,b)=>b.delta-a.delta);

  const sells=z.rows
    .filter(x=>x.delta<0)
    .sort((a,b)=>a.delta-b.delta);

  const table=(rows,kind)=>`
    <div class="etf-box">
      <h3>${kind}持股排行</h3>

      <table class="etf-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>增減張</th>
            <th>增減幅</th>
          </tr>
        </thead>

        <tbody>
          ${
            rows.slice(0,20).map(x=>`
              <tr data-code="${esc(x.code)}">
                <td>
                  ${esc(x.name)} ${esc(x.code)}
                </td>

                <td class="${x.delta>=0?'etf-pos':'etf-neg'}">
                  ${x.delta>0?'+':''}${fmt(x.delta/1000)}
                </td>

                <td>
                  ${
                    x.ratio==null
                      ?'新增／出清'
                      :(x.ratio>0?'+':'')+x.ratio.toFixed(1)+'%'
                  }
                </td>
              </tr>
            `).join('')
            ||
            '<tr><td colspan="3">無增減資料</td></tr>'
          }
        </tbody>
      </table>
    </div>
  `;

  root.innerHTML=`
    <div class="etf-box">

      <h2>00981A｜主動統一台股增長</h2>

      <div class="etf-note">
        資料日 ${esc(z.end)}
        · 比較基準 ${esc(z.begin)}
        · 資料來源：公開持股快照
      </div>

      <div class="etf-controls">
        ${
          [1,5,10,20].map(n=>`
            <button
              type="button"
              data-period="${n}"
              class="${n===period?'on':''}"
            >
              ${n===1?'當日':n+'日'}
            </button>
          `).join('')
        }
      </div>

      ${
        !z.valid
          ?'<p class="etf-note">歷史快照不足，無法完整計算此期間；目前僅顯示已收錄資料差額</p>'
          :''
      }

      <div class="etf-cards">

        <div class="etf-card">
          增加持股
          <strong>${adds.length} 檔</strong>
        </div>

        <div class="etf-card">
          減少持股
          <strong>${sells.length} 檔</strong>
        </div>

        <div class="etf-card">
          持股檔數
          <strong>
            ${Object.keys(dataset.snapshots[z.end]).length}
          </strong>
        </div>

      </div>
    </div>

    <div class="etf-lists">
      ${table(adds,'增加')}
      ${table(sells,'減少')}
    </div>

    <div id="etfDetail" class="etf-detail"></div>

    <p class="etf-note">
      數字是持股快照差額，非已驗證的逐筆交易量；
      新增／出清也可能受到申購買回影響。
      跨期間若缺快照，不可當作逐日交易資料
    </p>
  `;

  root.querySelectorAll('[data-period]').forEach(b=>{
    b.onclick=()=>{
      period=+b.dataset.period;
      render();
    };
  });

  root.querySelectorAll('[data-code]').forEach(r=>{
    r.onclick=()=>{
      selected=r.dataset.code;
      detail(z.dates);
    };
  });

  if(selected){
    detail(z.dates);
  }
}

function detail(dates){

  const holder=root.querySelector('#etfDetail');

  if(!holder)return;

  const pts=dates.map((d,i)=>{

    const h=dataset.snapshots[d]?.[selected];

    const p=i
      ?dataset.snapshots[dates[i-1]]?.[selected]
      :null;

    return{
      d,
      h,
      delta:i
        ?(h?.shares||0)-(p?.shares||0)
        :null
    };

  }).filter(x=>x.h||x.delta!==null);

  const latest=pts.at(-1);

  if(!latest)return;

  const bars=pts.slice(-60);

  const max=Math.max(
    1,
    ...bars.map(x=>Math.abs(x.delta||0))
  );

  const w=760;
  const h=210;

  const barw=w/Math.max(1,bars.length);

  const rects=bars.map((x,i)=>{

    const v=x.delta||0;
    const height=Math.abs(v)/max*88;

    return`
      <rect
        x="${i*barw+1}"
        y="${v>=0?105-height:105}"
        width="${Math.max(1,barw-2)}"
        height="${height}"
        fill="${v>=0?'#ed6767':'#36bb91'}"
      >
        <title>
          ${esc(x.d)}
          ${v>=0?'+':''}${fmt(v/1000)}張
        </title>
      </rect>
    `;

  }).join('');

  holder.innerHTML=`
    <div class="etf-box">

      <h3>
        ${esc(latest.h?.name||selected)}
        （${esc(selected)}）
        ｜持股歷史
      </h3>

      <div class="etf-note">
        最新持股
        ${fmt((latest.h?.shares||0)/1000)} 張

        ｜權重
        ${(latest.h?.weight||0).toFixed(2)}%

        ｜已收錄
        ${pts.length} 個觀測日
      </div>

      <svg
        class="etf-chart"
        viewBox="0 0 760 210"
        role="img"
        aria-label="ETF 持股每日增減柱狀圖"
      >
        <line
          x1="0"
          x2="760"
          y1="105"
          y2="105"
          stroke="#9aa7b9"
        />

        ${rects}
      </svg>

      <p class="etf-note">
        紅柱：增加持股；
        綠柱：減少持股。
        第一版僅繪持股變化；
        股價疊圖待核對歷史股價日期後加入
      </p>

      <div style="max-height:300px;overflow:auto">

        <table class="etf-table">

          <thead>
            <tr>
              <th>日期</th>
              <th>持股張數</th>
              <th>增減張數</th>
            </tr>
          </thead>

          <tbody>
            ${
              pts.slice(-30).reverse().map(x=>`
                <tr>
                  <td>${esc(x.d)}</td>

                  <td>
                    ${fmt((x.h?.shares||0)/1000)}
                  </td>

                  <td>
                    ${
                      x.delta===null
                        ?'—'
                        :(x.delta>0?'+':'')+fmt(x.delta/1000)
                    }
                  </td>
                </tr>
              `).join('')
            }
          </tbody>

        </table>

      </div>
    </div>
  `;

  holder.scrollIntoView({
    behavior:'smooth',
    block:'nearest'
  });
}

let loaded=false;

switcher.querySelectorAll('[data-etf-tab]').forEach(b=>{

  b.addEventListener('click',async()=>{

    const active=b.dataset.etfTab==='etf';

    old.hidden=active;
    root.hidden=!active;

    switcher.querySelectorAll('button').forEach(x=>{
      x.classList.toggle('on',x===b);
    });

    if(active&&!loaded){

      loaded=true;
      render();

      try{

        const res=await fetch(
          './data/etf_00981a.json?t='+Date.now(),
          {cache:'no-store'}
        );

        if(!res.ok){
          throw Error('HTTP '+res.status);
        }

        dataset=await res.json();

        render();

      }catch(e){

        root.innerHTML=`
          <div class="etf-box">
            00981A 尚無可用資料：
            ${esc(e.message)}
          </div>
        `;
      }
    }
  });
});

})();
