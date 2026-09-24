const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

const st = {
  period: "1d",
  inst: "foreign",
  market: "twse",
  turn: "twse",
  hm: "twse",
  hk: "400",
  aim: "twse",
  advanced: false,
  openSector: null
};

const cache = {};
const shortNames = {};

async function J(p) {
  try {
    const r = await fetch(
      p + (p.includes("?") ? "&" : "?") + "v=" + Date.now(),
      { cache: "no-store" }
    );

    if (!r.ok) throw new Error("HTTP " + r.status);

    return await r.json();
  } catch (e) {
    console.error("JSON load failed:", p, e);
    return {};
  }
}

function pct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  v = Number(v);
  return (v > 0 ? "+" : "") + v.toFixed(2) + "%";
}

function cl(v) {
  return Number(v) >= 0 ? "up" : "down";
}

function money(v) {
  if (v === null || v === undefined) return "—";
  return (Number(v) > 0 ? "+" : "") + Number(v).toFixed(2) + "億";
}

function cleanLegalName(name = "") {
  return String(name)
    .replace(/&#\d+;/g, "")
    .replace(/股份有限公司/g, "")
    .replace(/有限公司/g, "")
    .trim();
}

function displayName(x = {}) {
  const t = String(x.ticker || "");
  if (shortNames[t]) return shortNames[t];

  const raw = cleanLegalName(x.name || "");

  return raw || t || "—";
}

function stock(x, rank) {
  const name = displayName(x);

  return `
    <span style="display:inline-flex;align-items:center;min-width:0">
      ${rank ? `<span class="rank">${rank}</span>` : ""}
      <span class="stock">
        <b>${name}</b>
        <span>${x.ticker || ""}</span>
      </span>
    </span>
  `;
}

function emptyRow(text = "目前沒有符合條件的資料") {
  return `<tr><td colspan="8"><div class="empty">${text}</div></td></tr>`;
}

/* -----------------------------
   股票簡稱
----------------------------- */

async function loadShortNames() {
  const sectors = await J("./data/sectors.json");

  (sectors.sectors || []).forEach(sec => {
    (sec.stocks || []).forEach(x => {
      if (x.ticker && x.name) {
        shortNames[String(x.ticker)] = x.name;
      }
    });
  });
}

/* -----------------------------
   導覽
----------------------------- */

function page(id) {
  $$(".page").forEach(x => {
    x.classList.toggle("active", x.id === id);
  });

  $$(".nav").forEach(x => {
    x.classList.toggle("active", x.dataset.p === id);
  });

  const nav = $("#mobileNav");
  if (nav) nav.value = id;

  window.scrollTo({
    top: 0,
    behavior: "smooth"
  });
}

$$(".nav").forEach(b => {
  b.onclick = () => page(b.dataset.p);
});

if ($("#mobileNav")) {
  $("#mobileNav").onchange = e => page(e.target.value);
}

/* -----------------------------
   時鐘
----------------------------- */

function clock() {
  const el = $("#clock");
  if (!el) return;

  el.textContent = new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date());
}

clock();
setInterval(clock, 30000);

/* -----------------------------
   深色模式
----------------------------- */

function setupTheme() {
  let theme = localStorage.getItem("tw-market-theme") || "light";

  document.documentElement.dataset.theme = theme;

  let actions = $(".header-actions");

  if (!actions) {
    actions = document.createElement("div");
    actions.className = "header-actions";

    const clockEl = $("#clock");

    if (clockEl && clockEl.parentNode) {
      clockEl.parentNode.insertBefore(actions, clockEl.nextSibling);
    }
  }

  const btn = document.createElement("button");
  btn.className = "icon-btn";
  btn.id = "themeToggle";
  btn.title = "切換深色模式";

  function icon() {
    btn.textContent =
      document.documentElement.dataset.theme === "dark"
        ? "☀︎"
        : "◐";
  }

  icon();

  btn.onclick = () => {
    const next =
      document.documentElement.dataset.theme === "dark"
        ? "light"
        : "dark";

    document.documentElement.dataset.theme = next;
    localStorage.setItem("tw-market-theme", next);

    icon();
  };

  actions.appendChild(btn);
}

/* -----------------------------
   回到最上方
----------------------------- */

function setupToTop() {
  const btn = document.createElement("button");

  btn.id = "toTop";
  btn.innerHTML = "↑";
  btn.setAttribute("aria-label", "回到最上方");

  document.body.appendChild(btn);

  window.addEventListener("scroll", () => {
    btn.classList.toggle("show", window.scrollY > 500);
  });

  btn.onclick = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth"
    });
  };
}

/* -----------------------------
   熱力圖顏色
----------------------------- */

function heatClass(v) {
  if (v === null || v === undefined) return "gray";

  const a = Math.abs(Number(v));

  if (Number(v) >= 0) {
    return a >= 3 ? "r4" :
           a >= 2 ? "r3" :
           a >= 1 ? "r2" : "r1";
  }

  return a >= 3 ? "g4" :
         a >= 2 ? "g3" :
         a >= 1 ? "g2" : "g1";
}

/* -----------------------------
   總覽
----------------------------- */

async function home() {
  const h = await J("./data/heatmap.json");
  const a = await J("./data/ai_picks.json");
  const ho = await J("./data/holders.json");

  const sectors = [...(h.sectors || [])]
    .filter(x => x.change_pct !== null && x.change_pct !== undefined)
    .sort((x, y) => y.change_pct - x.change_pct);

  const top = sectors.slice(0, 3);

  const cards = $("#homeCards");

  if (cards) {
    cards.innerHTML = `
      <div class="card metric">
        <small>市場熱力圖</small>
        <strong>${h.sectors?.length || 0} 族群</strong>
        <small>盤中每 5 分鐘更新</small>
      </div>

      <div class="card metric">
        <small>AI 選股</small>
        <strong>${(a.twse?.length || 0) + (a.tpex?.length || 0)} 檔</strong>
        <small>每天 18:00 更新</small>
      </div>

      <div class="card metric">
        <small>大戶籌碼</small>
        <strong>${ho.complete ? "完整" : "待補"}</strong>
        <small>每週六 15:00</small>
      </div>

      <div class="card metric">
        <small>目前最強族群</small>
        <strong>${top[0]?.name || "—"}</strong>
        <small class="${cl(top[0]?.change_pct)}">
          ${top[0] ? pct(top[0].change_pct) : "—"}
        </small>
      </div>
    `;
  }

  const box = $("#topSectors");

  if (box) {
    box.innerHTML = top.map((x, i) => `
      <div class="card metric">
        <small>0${i + 1} ${x.name}</small>
        <strong class="${cl(x.change_pct)}">
          ${pct(x.change_pct)}
        </strong>
        <small>
          ${x.complete ? "完整市值加權" : "部分市值資料待補"}
        </small>
      </div>
    `).join("");
  }
}

/* -----------------------------
   籌碼日報
----------------------------- */

async function flows() {
  const d = await J("./data/institutional.json");

  if ($("#flowDate")) {
    $("#flowDate").textContent =
      d.date ? `截至 ${d.date}` : "尚無資料";
  }

  const g =
    d.periods?.[st.period]?.[st.market]?.[st.inst] || {
      buy: [],
      sell: [],
      complete: false,
      days_used: 0
    };

  const need =
    st.period === "1d" ? 1 :
    st.period === "3d" ? 3 : 5;

  const status = $("#flowStatus");

  if (status) {
    status.className =
      "status" + (g.complete ? "" : " warn");

    status.textContent = g.complete
      ? `資料完整 · ${g.days_used} 個交易日`
      : `目前 ${g.days_used || 0} / ${need} 個交易日`;
  }

  function rows(arr) {
    if (!(arr || []).length) {
      return emptyRow();
    }

    return arr.map((x, i) => `
      <tr class="${x.change_pct < 0 ? "negative-row" : ""}">
        <td>
          ${stock(x, i + 1)}
          <div class="mobile-meta">
            ${Math.round((x.shares || 0) / 1000).toLocaleString()} 張
          </div>
        </td>

        <td
          data-label="估算金額"
          class="${x.amount_100m >= 0 ? "up" : "down"}"
        >
          ${money(x.amount_100m)}
        </td>

        <td data-label="張數">
          ${Math.round((x.shares || 0) / 1000).toLocaleString()}
        </td>

        <td
          data-label="漲跌"
          class="${cl(x.change_pct)}"
        >
          ${pct(x.change_pct)}
        </td>
      </tr>
    `).join("");
  }

  if ($("#buyRows")) $("#buyRows").innerHTML = rows(g.buy);
  if ($("#sellRows")) $("#sellRows").innerHTML = rows(g.sell);
}

$$("[data-period]").forEach(b => {
  b.onclick = () => {
    $$("[data-period]").forEach(x => x.classList.remove("active"));
    b.classList.add("active");

    st.period = b.dataset.period;

    flows();
  };
});

$$("[data-inst]").forEach(b => {
  b.onclick = () => {
    $$("[data-inst]").forEach(x => x.classList.remove("active"));
    b.classList.add("active");

    st.inst = b.dataset.inst;

    flows();
  };
});

$$("[data-market]").forEach(b => {
  b.onclick = () => {
    $$("[data-market]").forEach(x => x.classList.remove("active"));
    b.classList.add("active");

    st.market = b.dataset.market;

    flows();
  };
});

/* -----------------------------
   突然放量
----------------------------- */

function ensureVolumeCriteria() {
  if ($("#volumeCriteria")) return;

  const status = $("#volStatus");

  if (!status) return;

  const box = document.createElement("div");

  box.id = "volumeCriteria";
  box.className = "criteria";

  status.insertAdjacentElement("afterend", box);
}

function renderVolumeCriteria() {
  ensureVolumeCriteria();

  const box = $("#volumeCriteria");

  if (!box) return;

  if (!st.advanced) {
    box.innerHTML = `
      <b>篩選依據</b>
      <p>依「今日成交量 ÷ 前 5 個交易日平均成交量」排序</p>

      <div class="criteria-grid">
        <span class="criterion">
          僅追蹤自訂科技股
        </span>

        <span class="criterion">
          量比越高排名越前
        </span>
      </div>
    `;

    return;
  }

  box.innerHTML = `
    <b>進階篩選條件</b>

    <div class="criteria-grid">
      <span class="criterion">
        今日量 ≥ 20日均量 1.3倍
      </span>

      <span class="criterion">
        今日量 ≤ 20日均量 2倍
      </span>

      <span class="criterion">
        3日均量 ＞ 5日均量 ＞ 10日均量
      </span>

      <span class="criterion">
        今日成交量 ≥ 1,000張
      </span>
    </div>

    <p>
      「短期均量多頭排列」代表近期成交熱度持續升高，而不是單日突然爆量
    </p>
  `;
}

async function volume() {
  const v = await J("./data/volume.json");
  const s = await J("./data/screener.json");

  if ($("#volDate")) {
    $("#volDate").textContent = v.date || "尚無資料";
  }

  const d = st.advanced
    ? (s.items || [])
    : (v.items || []);

  const status = $("#volStatus");

  if (status) {
    status.className =
      "status" +
      ((st.advanced ? !s.complete : !v.complete) ? " warn" : "");

    status.textContent = st.advanced
      ? (
          s.complete
            ? "20日歷史完整"
            : `進階篩選需要 21 個交易日，目前 ${s.history_days || 0}`
        )
      : (
          v.complete
            ? "前 5 日歷史完整"
            : `突然放量需要 6 個交易日，目前 ${v.history_days || 0}`
        );
  }

  renderVolumeCriteria();

  const rows = $("#volRows");

  if (!rows) return;

  if (!d.length) {
    rows.innerHTML = emptyRow("目前沒有符合篩選條件的股票");
    return;
  }

  rows.innerHTML = d.map((x, i) => {

    const advText = st.advanced
      ? `20日量比 ${Number(x.volume_ratio_20d || 0).toFixed(2)}x`
      : "";

    const trendText = st.advanced
      ? `3日 ${Number(x.avg3 || 0).toLocaleString()} ＞ 5日 ${Number(x.avg5 || 0).toLocaleString()} ＞ 10日 ${Number(x.avg10 || 0).toLocaleString()}`
      : "";

    return `
      <tr class="${x.change_pct < 0 ? "negative-row" : ""}">

        <td>
          ${stock(x, i + 1)}

          <div class="mobile-meta">
            今日量 ${Math.round((x.volume || 0) / 1000).toLocaleString()}張
          </div>
        </td>

        <td
          data-label="漲跌"
          class="${cl(x.change_pct)}"
        >
          ${pct(x.change_pct)}
        </td>

        <td data-label="今日量">
          ${Math.round((x.volume || 0) / 1000).toLocaleString()}張
        </td>

        <td data-label="5日量比">
          ${Number(x.volume_ratio_5d || 0).toFixed(2)}x
        </td>

        <td data-label="${st.advanced ? "進階條件" : "訊號"}">
          ${
            st.advanced
              ? `
                <div>${advText}</div>
                <div style="font-size:10px;color:var(--muted);margin-top:3px">
                  ${trendText}
                </div>
              `
              : (x.low_base ? "低基期" : "—")
          }
        </td>

      </tr>
    `;
  }).join("");
}

if ($("#advanced")) {
  $("#advanced").onclick = () => {

    st.advanced = !st.advanced;

    $("#advanced").classList.toggle(
      "active",
      st.advanced
    );

    $("#advanced").textContent =
      st.advanced
        ? "進階篩選 ✓"
        : "進階篩選 ＋";

    volume();
  };
}

/* -----------------------------
   成交排行
----------------------------- */

async function turnover() {
  const d = await J("./data/turnover.json");

  if ($("#turnDate")) {
    $("#turnDate").textContent =
      d.date || "尚無資料";
  }

  const arr = d[st.turn] || [];
  const rows = $("#turnRows");

  if (!rows) return;

  if (!arr.length) {
    rows.innerHTML = emptyRow();
    return;
  }

  rows.innerHTML = arr.map((x, i) => `
    <tr class="${x.change_pct < 0 ? "negative-row" : ""}">

      <td>
        ${stock(x, i + 1)}

        <div class="mobile-meta">
          ${x.price || "—"} · ${pct(x.change_pct)}
        </div>
      </td>

      <td data-label="成交金額">
        ${(Number(x.turnover || 0) / 1e8).toFixed(2)}億
      </td>

      <td data-label="成交張數">
        ${Math.round(Number(x.volume || 0) / 1000).toLocaleString()}
      </td>

      <td data-label="收盤">
        ${x.price || "—"}
      </td>

      <td
        data-label="漲跌"
        class="${cl(x.change_pct)}"
      >
        ${pct(x.change_pct)}
      </td>

    </tr>
  `).join("");
}

$$("[data-turn]").forEach(b => {
  b.onclick = () => {

    $$("[data-turn]")
      .forEach(x => x.classList.remove("active"));

    b.classList.add("active");

    st.turn = b.dataset.turn;

    turnover();
  };
});

/* -----------------------------
   大戶籌碼
----------------------------- */

async function holders() {
  const d = await J("./data/holders.json");

  if ($("#holderDate")) {
    $("#holderDate").textContent =
      d.date
        ? `${d.date}｜週六 15:00`
        : "週六 15:00";
  }

  const status = $("#holderStatus");

  if (status) {
    status.className =
      "status" + (d.complete ? "" : " warn");

    status.textContent = d.complete
      ? `比較 ${d.previous_date} → ${d.date}`
      : "需要兩期集保資料才能計算大戶增加";
  }

  const arr =
    d[st.hm]?.[st.hk] || [];

  const rows = $("#holderRows");

  if (!rows) return;

  if (!arr.length) {
    rows.innerHTML = emptyRow();
    return;
  }

  rows.innerHTML = arr.map((x, i) => `
    <tr class="${x.week_change_pct < 0 ? "negative-row" : ""}">

      <td>
        ${stock(x, i + 1)}

        <div class="mobile-meta">
          大戶比 ${Number(x.ratio || 0).toFixed(2)}%
        </div>
      </td>

      <td
        data-label="同期股價"
        class="${cl(x.week_change_pct)}"
      >
        ${pct(x.week_change_pct)}
      </td>

      <td data-label="大戶比率">
        ${Number(x.ratio || 0).toFixed(2)}%
      </td>

      <td data-label="增加" class="up">
        +${Number(x.delta || 0).toFixed(2)} ppt
      </td>

    </tr>
  `).join("");
}

$$("[data-hm]").forEach(b => {
  b.onclick = () => {

    $$("[data-hm]")
      .forEach(x => x.classList.remove("active"));

    b.classList.add("active");

    st.hm = b.dataset.hm;

    holders();
  };
});

$$("[data-hk]").forEach(b => {
  b.onclick = () => {

    $$("[data-hk]")
      .forEach(x => x.classList.remove("active"));

    b.classList.add("active");

    st.hk = b.dataset.hk;

    holders();
  };
});

/* -----------------------------
   AI 選股
----------------------------- */

function ensureAiCriteria() {
  if ($("#aiCriteria")) return;

  const status = $("#aiStatus");

  if (!status) return;

  const box = document.createElement("div");

  box.id = "aiCriteria";
  box.className = "criteria";

  status.insertAdjacentElement("afterend", box);
}

function renderAiCriteria(mode) {
  ensureAiCriteria();

  const box = $("#aiCriteria");

  if (!box) return;

  if (mode === "sunday") {
    box.innerHTML = `
      <b>AI 選股篩選／計分依據｜週日版</b>

      <div class="criteria-grid">
        <span class="criterion">外資 20%</span>
        <span class="criterion">投信 25%</span>
        <span class="criterion">自營商 10%</span>
        <span class="criterion">大戶籌碼 30%</span>
        <span class="criterion">近5日成交熱度 15%</span>
      </div>

      <p>
        分數為同市場股票的相對強弱排名，不代表未來上漲機率
      </p>
    `;

    return;
  }

  box.innerHTML = `
    <b>AI 選股篩選／計分依據｜交易日版</b>

    <div class="criteria-grid">
      <span class="criterion">外資 20%</span>
      <span class="criterion">投信 25%</span>
      <span class="criterion">自營商 10%</span>
      <span class="criterion">大戶籌碼 25%</span>
      <span class="criterion">量價 5%</span>
      <span class="criterion">成交熱度 15%</span>
    </div>

    <p>
      分數為同市場股票的相對強弱排名，不代表未來上漲機率
    </p>
  `;
}

async function ai() {
  const d = await J("./data/ai_picks.json");

  const status = $("#aiStatus");

  if (status) {
    status.className =
      "status" + (d.complete ? "" : " warn");

    status.textContent = d.complete
      ? `${d.mode === "sunday" ? "週日版" : "交易日版"} · 資料完整`
      : "部分來源尚未完整";
  }

  renderAiCriteria(d.mode);

  const arr = d[st.aim] || [];
  const box = $("#aiCards");

  if (!box) return;

  if (!arr.length) {
    box.innerHTML =
      `<div class="card empty">目前沒有 AI 選股資料</div>`;
    return;
  }

  box.innerHTML = arr.map((x, i) => `
    <div class="card aicard">

      <div class="aitop">

        <div>
          <div style="font-size:10px;color:var(--muted);margin-bottom:5px">
            #${i + 1}
          </div>

          ${stock(x)}
        </div>

        <div class="score">
          ${x.score}
        </div>

      </div>

      <div class="tags">
        ${(x.tags || []).map(t =>
          `<span class="tag">${t}</span>`
        ).join("")}
      </div>

      <div class="reason">
        ${x.reason || "—"}
      </div>

    </div>
  `).join("");

  $$(".aicard").forEach(x => {
    x.onclick =
      () => x.classList.toggle("open");
  });
}

$$("[data-aim]").forEach(b => {
  b.onclick = () => {

    $$("[data-aim]")
      .forEach(x => x.classList.remove("active"));

    b.classList.add("active");

    st.aim = b.dataset.aim;

    ai();
  };
});

/* -----------------------------
   市場熱力圖
----------------------------- */

function heatDetail(sec) {
  const stocks = [...(sec.stocks || [])]
    .sort(
      (a, b) =>
        (b.change_pct ?? -999) -
        (a.change_pct ?? -999)
    );

  return `
    <div class="heat-detail">

      <div class="heat-detail-head">

        <b>
          ${sec.name}
          <span class="${cl(sec.change_pct)}">
            ${pct(sec.change_pct)}
          </span>
        </b>

        <span>
          ${stocks.length} 檔｜依漲跌幅排序
        </span>

      </div>

      <div class="heat-stock-list">

        ${stocks.map(x => `
          <div class="heat-stock">

            <div>
              <span class="n">
                ${displayName(x)}
              </span>

              <span class="t">
                ${x.ticker}
              </span>
            </div>

            <span class="v ${cl(x.change_pct)}">
              ${pct(x.change_pct)}
            </span>

          </div>
        `).join("")}

      </div>

    </div>
  `;
}

async function heat() {
  const d = await J("./data/heatmap.json");

  cache.heat = d;

  if ($("#heatTime")) {
    $("#heatTime").textContent =
      d.updated_at || "尚無資料";
  }

  const box = $("#heatGrid");

  if (!box) return;

  const sectors = d.sectors || [];

  if (!sectors.length) {
    box.innerHTML =
      `<div class="empty">目前沒有熱力圖資料</div>`;
    return;
  }

  let html = "";

  sectors.forEach((x, i) => {

    html += `
      <button
        class="heat ${
          i === 1
            ? "s5 tall"
            : i === 11
            ? "s6 tall"
            : i % 3 === 0
            ? "s4"
            : "s3"
        } ${heatClass(x.change_pct)}"
        data-sec="${x.name}"
      >

        <b>${x.name}</b>

        <strong>
          ${pct(x.change_pct)}
        </strong>

        <small>
          ${
            x.complete
              ? `${x.stocks?.length || 0}檔`
              : `${x.stocks?.length || 0}檔 · 市值待補${x.missing?.length || 0}`
          }
        </small>

      </button>
    `;

    if (st.openSector === x.name) {
      html += heatDetail(x);
    }
  });

  box.innerHTML = html;

  $$("[data-sec]").forEach(b => {

    b.onclick = () => {

      st.openSector =
        st.openSector === b.dataset.sec
          ? null
          : b.dataset.sec;

      heat();
    };

  });

  /* 舊版底部明細隱藏 */
  const oldSection = $("#heatTitle")?.closest(".section");

  if (oldSection) {
    oldSection.style.display = "none";
  }

  const oldTable = $("#heatRows")?.closest(".card");

  if (oldTable) {
    oldTable.style.display = "none";
  }
}

/* -----------------------------
   券商報告
----------------------------- */

async function reports() {
  const d = await J("./data/reports.json");

  const map = {
    upgrade: "上調",
    downgrade: "下調",
    initiate: "初評",
    maintain: "維持"
  };

  const box = $("#reportList");

  if (!box) return;

  if (!(d.items || []).length) {

    box.innerHTML = `
      <div class="report">
        <div class="rmain">
          <div class="rtitle">
            尚無券商報告
          </div>

          <div class="rmeta">
            收到 PDF 或連結後即會整理至此
          </div>
        </div>
      </div>
    `;

    return;
  }

  box.innerHTML = d.items.map(r => `
    <div class="report">

      <div class="broker">
        ${r.broker || ""}
      </div>

      <div class="rmain">

        <div class="rtitle">
          ${r.broker || ""}
          ${map[r.action] || r.action || ""}
          ${r.name || ""}
          ${r.ticker || ""}
        </div>

        <div class="rmeta">
          ${r.summary || ""}
          ${r.date ? ` · ${r.date}` : ""}
        </div>

      </div>

      <div class="tp">
        ${
          r.target_price
            ? `目標價 ${r.target_price}`
            : ""
        }
      </div>

    </div>
  `).join("");
}

/* -----------------------------
   啟動
----------------------------- */

async function init() {

  setupTheme();
  setupToTop();

  await loadShortNames();

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
