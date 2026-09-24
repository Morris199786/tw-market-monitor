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

function aiFactorLabel(key) {
  const map = {
    foreign: "外資",
    trust: "投信",
    dealer: "自營商",
    holders: "大戶籌碼",
    volume_price: "量價",
    turnover: "當日成交熱度",
    turnover_5d: "近5日成交熱度"
  };

  return map[key] || key;
}

function renderAiCriteria(d) {
  ensureAiCriteria();

  const box = $("#aiCriteria");
  if (!box) return;

  const logic = d.logic || {};
  const factors = logic.factors || [];

  const dates = (logic.institutional_dates || []).join("、");

  const factorHtml = factors.length
    ? factors.map(x => `
        <span class="criterion">
          ${x.label || aiFactorLabel(x.key)}
          ${Number(x.weight_pct || 0).toFixed(0)}%
        </span>
      `).join("")
    : `
        <span class="criterion">外資 20%</span>
        <span class="criterion">投信 25%</span>
        <span class="criterion">自營商 10%</span>
        <span class="criterion">大戶籌碼 25%</span>
        <span class="criterion">量價 5%</span>
        <span class="criterion">成交熱度 15%</span>
      `;

  const details = logic.details || [];

  box.innerHTML = `
    <b>
      AI 選股邏輯｜
      ${d.mode === "sunday" ? "週日版" : "交易日版"}
    </b>

    <p style="margin-top:7px">
      股票池：
      ${logic.universe || "自訂科技股"}
    </p>

    ${
      dates
        ? `
          <p>
            法人計算期間：
            ${dates}
          </p>
        `
        : ""
    }

    <div class="criteria-grid">
      ${factorHtml}
    </div>

    ${
      details.length
        ? `
          <div style="
            margin-top:10px;
            padding-top:9px;
            border-top:1px solid var(--line);
            font-size:11px;
            line-height:1.7;
            color:var(--muted)
          ">
            ${details.map((x, i) => `
              <div style="margin-bottom:4px">
                ${i + 1}. ${x}
              </div>
            `).join("")}
          </div>
        `
        : ""
    }
  `;
}

function aiFactorBreakdown(x) {
  const scores = x.factor_scores || {};
  const contributions = x.contributions || {};

  const keys = Object.keys(contributions);

  if (!keys.length) {
    return `
      <div class="empty">
        尚無因子拆解資料
      </div>
    `;
  }

  const rows = keys
    .map(key => ({
      key,
      label: aiFactorLabel(key),
      score: Number(scores[key] || 0),
      contribution: Number(contributions[key] || 0)
    }))
    .sort((a, b) => b.contribution - a.contribution);

  return `
    <div style="
      margin-top:12px;
      padding-top:10px;
      border-top:1px solid var(--line)
    ">

      <div style="
        font-size:11px;
        font-weight:800;
        margin-bottom:7px
      ">
        因子分數拆解
      </div>

      ${rows.map(r => `
        <div style="
          display:grid;
          grid-template-columns:minmax(88px,1fr) 64px 72px;
          gap:8px;
          align-items:center;
          padding:6px 0;
          border-bottom:1px solid var(--line);
          font-size:11px
        ">

          <div>
            ${r.label}
          </div>

          <div style="
            text-align:right;
            color:var(--muted)
          ">
            ${r.score.toFixed(1)} 分
          </div>

          <div style="
            text-align:right;
            font-weight:800
          ">
            +${r.contribution.toFixed(1)}
          </div>

        </div>
      `).join("")}

      <div style="
        margin-top:8px;
        font-size:10px;
        line-height:1.6;
        color:var(--muted)
      ">
        因子分數為同市場追蹤股的相對百分位分數，
        「貢獻」為因子分數 × 該因子權重
      </div>

    </div>
  `;
}

async function ai() {
  const d = await J("./data/ai_picks.json");

  const status = $("#aiStatus");

  if (status) {
    status.className =
      "status" + (d.complete ? "" : " warn");

    status.textContent = d.complete
      ? `${
          d.mode === "sunday"
            ? "週日版"
            : "交易日版"
        } · 資料完整 · ${
          d.logic?.version || ""
        }`
      : "部分來源尚未完整";
  }

  renderAiCriteria(d);

  const arr = d[st.aim] || [];
  const box = $("#aiCards");

  if (!box) return;

  if (!arr.length) {
    box.innerHTML = `
      <div class="card empty">
        目前沒有 AI 選股資料
      </div>
    `;
    return;
  }

  box.innerHTML = arr.map((x, i) => `
    <div class="card aicard">

      <div class="aitop">

        <div>

          <div style="
            font-size:10px;
            color:var(--muted);
            margin-bottom:5px
          ">
            #${i + 1}
          </div>

          ${stock(x)}

          <div style="
            font-size:10px;
            margin-top:6px
          "
          class="${cl(x.change_pct)}">
            今日 ${pct(x.change_pct)}
          </div>

        </div>

        <div style="text-align:right">

          <div class="score">
            ${Number(x.score || 0).toFixed(1)}
          </div>

          <div style="
            font-size:9px;
            color:var(--muted);
            margin-top:2px
          ">
            相對分數
          </div>

        </div>

      </div>

      <div class="tags">
        ${(x.tags || []).map(t => `
          <span class="tag">
            ${t}
          </span>
        `).join("")}
      </div>

      <div class="reason">

        <div style="
          font-weight:800;
          color:var(--ink);
          margin-bottom:5px
        ">
          主要入選原因
        </div>

        <div>
          ${x.reason || "—"}
        </div>

        ${aiFactorBreakdown(x)}

        ${
          x.raw
            ? `
              <div style="
                margin-top:10px;
                padding-top:8px;
                border-top:1px solid var(--line);
                font-size:10px;
                line-height:1.7;
                color:var(--muted)
              ">

                ${
                  x.raw.holder_delta_avg_ppt !== undefined
                    ? `
                      <div>
                        大戶週增幅平均：
                        ${Number(
                          x.raw.holder_delta_avg_ppt || 0
                        ).toFixed(2)} ppt
                      </div>
                    `
                    : ""
                }

                ${
                  x.raw.volume_ratio_5d !== undefined
                    ? `
                      <div>
                        5日量比：
                        ${Number(
                          x.raw.volume_ratio_5d || 0
                        ).toFixed(2)}x
                      </div>
                    `
                    : ""
                }

              </div>
            `
            : ""
        }

        <div style="
          margin-top:10px;
          font-size:10px;
          line-height:1.6;
          color:var(--muted)
        ">
          分數僅代表同市場追蹤股的相對強弱，
          不代表未來上漲機率
        </div>

      </div>

    </div>
  `).join("");

  $$(".aicard").forEach(card => {
    card.onclick = () => {
      card.classList.toggle("open");
    };
  });
}

$$("[data-aim]").forEach(b => {
  b.onclick = () => {

    $$("[data-aim]")
      .forEach(x =>
        x.classList.remove("active")
      );

    b.classList.add("active");

    st.aim = b.dataset.aim;

    ai();
  };
});
