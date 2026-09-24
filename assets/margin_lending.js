const mlState = {
  kind: "margin",
  market: "twse"
};

function mlNum(v, digits = 0) {
  if (
    v === null ||
    v === undefined ||
    Number.isNaN(Number(v))
  ) {
    return "—";
  }

  return Number(v).toLocaleString(
    "zh-TW",
    {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits
    }
  );
}

function mlSigned(v, suffix = "張", digits = 0) {
  if (
    v === null ||
    v === undefined ||
    Number.isNaN(Number(v))
  ) {
    return "—";
  }

  const n = Number(v);

  return (
    (n > 0 ? "+" : "") +
    mlNum(n, digits) +
    suffix
  );
}

function mlPriorityLabel(x) {
  if (x.priority === "sudden") {
    return "單日突發";
  }

  if (x.priority === "trend") {
    return "持續累積";
  }

  return "一般增加";
}

function renderMlLogic(d) {
  const box = $("#mlLogic");

  if (!box) {
    return;
  }

  const logic = d.logic || {};

  const details =
    logic.details || [];

  box.innerHTML = `
    <details class="criteria" style="margin-bottom:14px">
      <summary style="
        cursor:pointer;
        list-style:none;
        display:flex;
        justify-content:space-between;
        align-items:center;
        gap:12px
      ">
        <span style="font-weight:800">
          判讀邏輯
        </span>

        <span style="
          color:var(--muted);
          font-size:10px
        ">
          點擊展開 ▾
        </span>
      </summary>

      <div style="
        margin-top:10px;
        padding-top:10px;
        border-top:1px solid var(--line)
      ">
        <p>
          股票池：${logic.universe || "全台股普通股"}
        </p>

        ${(logic.ranking || [])
          .map(
            x => `
              <p>
                ${x}
              </p>
            `
          )
          .join("")}

        <div class="criteria-grid" style="margin:9px 0">
          <span class="criterion">
            20日異常基準
          </span>

          <span class="criterion">
            5日成交均量
          </span>

          <span class="criterion">
            5日／10日趨勢
          </span>

          <span class="criterion">
            上市上櫃分開排行
          </span>
        </div>

        ${details
          .map(
            x => `
              <p>
                ${x}
              </p>
            `
          )
          .join("")}
      </div>
    </details>
  `;

  const detail =
    box.querySelector(
      "details"
    );

  const hint =
    box.querySelector(
      "summary span:last-child"
    );

  if (
    detail &&
    hint
  ) {
    detail.addEventListener(
      "toggle",
      () => {
        hint.textContent =
          detail.open
            ? "收起 ▴"
            : "點擊展開 ▾";
      }
    );
  }
}

function mlRawDetail(x) {
  const r = x.raw || {};

  return `
    <div style="
      margin-top:12px;
      padding-top:10px;
      border-top:1px solid var(--line);
      font-size:10px;
      line-height:1.8;
      color:var(--muted)
    ">
      <div>
        目前餘額：
        ${mlNum(
          r.balance_lots,
          0
        )} 張
      </div>

      <div>
        1日增減：
        ${mlSigned(
          r.change_1d_lots
        )}
        ${
          r.change_1d_pct !==
          undefined
            ? `（${
                Number(
                  r.change_1d_pct ||
                  0
                ) > 0
                  ? "+"
                  : ""
              }${Number(
                r.change_1d_pct ||
                0
              ).toFixed(1)}%）`
            : ""
        }
      </div>

      <div>
        5日增減：
        ${mlSigned(
          r.change_5d_lots
        )}
        ${
          r.change_5d_pct !==
          undefined
            ? `（${
                Number(
                  r.change_5d_pct ||
                  0
                ) > 0
                  ? "+"
                  : ""
              }${Number(
                r.change_5d_pct ||
                0
              ).toFixed(1)}%）`
            : ""
        }
      </div>

      <div>
        最近5日：
        ${r.up_days_5d ?? "—"} 日增加
        ｜最近10日：
        ${r.up_days_10d ?? "—"} 日增加
      </div>

      <div>
        20日異常倍數：
        ${Number(
          r.anomaly_20d ||
          0
        ).toFixed(2)}x
      </div>

      <div>
        過去20日正常每日變化：
        ${mlNum(
          r.normal_daily_change_20d_lots,
          0
        )} 張
      </div>

      <div>
        1日增加占5日均量：
        ${Number(
          r.change_1d_vs_avg5_volume_pct ||
          0
        ).toFixed(1)}%
      </div>

      <div>
        5日增加占5日均量：
        ${Number(
          r.change_5d_vs_avg5_volume_pct ||
          0
        ).toFixed(1)}%
      </div>

      ${
        mlState.kind === "borrow" &&
        r.short_sell_change_1d_lots !==
        null &&
        r.short_sell_change_1d_lots !==
        undefined
          ? `
            <div>
              借券賣出1日增減：
              ${mlSigned(
                r.short_sell_change_1d_lots
              )}
            </div>
          `
          : ""
      }

      ${
        mlState.kind === "borrow" &&
        r.short_sell_change_5d_lots !==
        null &&
        r.short_sell_change_5d_lots !==
        undefined
          ? `
            <div>
              借券賣出5日增減：
              ${mlSigned(
                r.short_sell_change_5d_lots
              )}
            </div>
          `
          : ""
      }
    </div>
  `;
}

async function marginLending() {
  const d = await J(
    "./data/margin_lending.json"
  );

  if ($("#mlDate")) {
    $("#mlDate").textContent =
      d.date
        ? `截至 ${d.date}`
        : "尚無資料";
  }

  const status =
    $("#mlStatus");

  if (status) {
    status.className =
      "status" +
      (
        d.complete
          ? ""
          : " warn"
      );

    if (!d.date) {
      status.textContent =
        "尚未產生融資／借券資料，先手動執行 Margin lending update";
    } else {
      status.textContent =
        `${
          d.complete
            ? "資料完整"
            : "歷史資料建立中"
        } · ${
          d.history_days ||
          0
        } 個交易日 · ${
          d.logic?.version ||
          ""
        }`;
    }
  }

  renderMlLogic(d);

  const arr =
    d[mlState.kind]?.[
      mlState.market
    ] || [];

  const box =
    $("#mlCards");

  if (!box) {
    return;
  }

  if (!arr.length) {
    box.innerHTML = `
      <div class="card empty">
        目前沒有符合條件的資料
      </div>
    `;

    return;
  }

  box.innerHTML = arr
    .map(
      (x, i) => `
        <div class="card aicard mlcard">
          <div class="aitop">
            <div>
              <div style="
                font-size:10px;
                color:var(--muted);
                margin-bottom:5px
              ">
                #${i + 1}
                ·
                ${mlPriorityLabel(
                  x
                )}
              </div>

              ${stock(x)}

              <div
                style="
                  font-size:10px;
                  margin-top:6px
                "
                class="${cl(
                  x.change_pct
                )}"
              >
                今日
                ${pct(
                  x.change_pct
                )}
              </div>
            </div>

            <div style="
              text-align:right
            ">
              <div class="score">
                ${Number(
                  x.score || 0
                ).toFixed(1)}
              </div>

              <div style="
                font-size:9px;
                color:var(--muted);
                margin-top:2px
              ">
                異動分數
              </div>
            </div>
          </div>

          <div class="tags">
            ${(x.tags || [])
              .map(
                t => `
                  <span class="tag">
                    ${t}
                  </span>
                `
              )
              .join("")}
          </div>

          <div style="
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:8px;
            margin-top:10px;
            font-size:10px
          ">
            <div>
              <span style="color:var(--muted)">
                今日
              </span>
              <b style="display:block;margin-top:2px">
                ${mlSigned(
                  x.raw
                    ?.change_1d_lots
                )}
              </b>
            </div>

            <div>
              <span style="color:var(--muted)">
                近5日
              </span>
              <b style="display:block;margin-top:2px">
                ${mlSigned(
                  x.raw
                    ?.change_5d_lots
                )}
              </b>
            </div>
          </div>

          <div class="reason">
            <div style="
              font-weight:800;
              color:var(--ink);
              margin-bottom:5px
            ">
              判讀原因
            </div>

            <div>
              ${x.reason || "—"}
            </div>

            ${mlRawDetail(x)}

            <div style="
              margin-top:10px;
              font-size:10px;
              line-height:1.6;
              color:var(--muted)
            ">
              異動分數只用於同類型排名，
              不代表股價未來方向
            </div>
          </div>
        </div>
      `
    )
    .join("");

  $$(".mlcard").forEach(
    card => {
      card.onclick = () => {
        card.classList.toggle(
          "open"
        );
      };
    }
  );
}

$$("[data-ml-kind]").forEach(
  b => {
    b.onclick = () => {
      $$("[data-ml-kind]").forEach(
        x =>
          x.classList.remove(
            "active"
          )
      );

      b.classList.add(
        "active"
      );

      mlState.kind =
        b.dataset.mlKind;

      marginLending();
    };
  }
);

$$("[data-ml-market]").forEach(
  b => {
    b.onclick = () => {
      $$("[data-ml-market]").forEach(
        x =>
          x.classList.remove(
            "active"
          )
      );

      b.classList.add(
        "active"
      );

      mlState.market =
        b.dataset.mlMarket;

      marginLending();
    };
  }
);

marginLending();
