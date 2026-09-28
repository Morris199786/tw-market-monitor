/* =========================================================
   首頁功能卡片自訂排序 V3
   - 點「自訂排序」後開啟排序面板
   - 手機 / 平板 / 電腦：上下拖曳排序
   - 完成後套用首頁卡片順序
   - localStorage 保存
   - 可恢復預設排序
   ========================================================= */

(function () {
  const STORAGE_KEY = "tw-feature-order-v3";

  const DEFAULT_ORDER = [
    "heat",
    "selfReports",
    "flows",
    "volume",
    "turnover",
    "marginLending",
    "ai",
    "reports",
    "holders",
    "monthlyRevenue"
  ];

  let workingOrder = [];
  let dragId = null;
  let dragEl = null;

  function $(selector, root = document) {
    return root.querySelector(selector);
  }

  function $$(selector, root = document) {
    return [
      ...root.querySelectorAll(selector)
    ];
  }

  function rail() {
    return document.getElementById(
      "featureRail"
    );
  }

  function cards() {
    const box = rail();

    if (!box) {
      return [];
    }

    return $$(
      ".feature-card[data-feature]",
      box
    );
  }

  function featureMeta() {
    const map = new Map();

    cards().forEach(card => {
      const id =
        card.dataset.feature;

      const name =
        card.querySelector(
          ".feature-copy b"
        )?.textContent?.trim() ||
        id;

      const subtitle =
        card.querySelector(
          ".feature-copy small"
        )?.textContent?.trim() ||
        "";

      map.set(
        id,
        {
          id,
          name,
          subtitle
        }
      );
    });

    return map;
  }

  function currentOrder() {
    return cards()
      .map(
        card =>
          card.dataset.feature
      )
      .filter(Boolean);
  }

  function readSavedOrder() {
    try {
      const raw =
        localStorage.getItem(
          STORAGE_KEY
        );

      if (!raw) {
        return null;
      }

      const parsed =
        JSON.parse(raw);

      return Array.isArray(parsed)
        ? parsed
        : null;
    } catch (e) {
      return null;
    }
  }

  function saveOrder(order) {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(order)
      );
    } catch (e) {
      console.warn(
        "feature order save failed",
        e
      );
    }
  }

  function normalizedOrder(order) {
    const actual =
      currentOrder();

    const valid =
      (order || [])
        .filter(
          id =>
            actual.includes(id)
        );

    actual.forEach(id => {
      if (
        !valid.includes(id)
      ) {
        valid.push(id);
      }
    });

    return valid;
  }

  function updateIndexes() {
    cards().forEach(
      (card, index) => {
        const badge =
          card.querySelector(
            ".feature-index"
          );

        if (badge) {
          badge.textContent =
            String(
              index + 1
            ).padStart(
              2,
              "0"
            );
        }
      }
    );
  }

  function applyOrder(order) {
    const box = rail();

    if (!box) {
      return;
    }

    const byId =
      new Map(
        cards().map(
          card => [
            card.dataset.feature,
            card
          ]
        )
      );

    normalizedOrder(order)
      .forEach(id => {
        const card =
          byId.get(id);

        if (card) {
          box.appendChild(
            card
          );
        }
      });

    updateIndexes();
  }

  function restoreOrder() {
    const saved =
      readSavedOrder();

    if (saved) {
      applyOrder(saved);
    } else {
      updateIndexes();
    }
  }

  function injectStyles() {
    if (
      document.getElementById(
        "featureSortV3Styles"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "featureSortV3Styles";

    style.textContent = `
      .feature-sort-bar-v3{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        margin:0 2px 10px;
      }

      .feature-sort-title-v3{
        display:flex;
        align-items:center;
        gap:8px;
        min-width:0;
      }

      .feature-sort-title-v3 strong{
        color:var(--ink);
        font-size:14px;
        font-weight:900;
      }

      .feature-sort-title-v3 small{
        color:var(--muted);
        font-size:10px;
      }

      .feature-sort-open-v3{
        appearance:none;
        -webkit-appearance:none;
        border:1px solid var(--line);
        background:var(--card);
        color:var(--ink);
        border-radius:999px;
        padding:8px 12px;
        font-size:11px;
        line-height:1;
        font-weight:800;
        cursor:pointer;
        box-shadow:
          0 4px 12px
          rgba(15,23,42,.05);
      }

      .feature-sort-backdrop-v3{
        position:fixed;
        inset:0;
        z-index:9998;
        background:
          rgba(15,23,42,.38);
        backdrop-filter:
          blur(6px);
        -webkit-backdrop-filter:
          blur(6px);
        opacity:0;
        pointer-events:none;
        transition:
          opacity .18s ease;
      }

      .feature-sort-backdrop-v3.show{
        opacity:1;
        pointer-events:auto;
      }

      .feature-sort-sheet-v3{
        position:fixed;
        left:50%;
        bottom:0;
        z-index:9999;

        width:
          min(
            560px,
            100%
          );

        max-height:
          min(
            82vh,
            760px
          );

        transform:
          translate(
            -50%,
            105%
          );

        background:
          var(--card);

        border:
          1px solid
          var(--line);

        border-bottom:0;

        border-radius:
          24px
          24px
          0
          0;

        box-shadow:
          0
          -18px
          60px
          rgba(
            15,
            23,
            42,
            .18
          );

        overflow:hidden;

        transition:
          transform
          .24s
          cubic-bezier(
            .2,
            .8,
            .2,
            1
          );
      }

      .feature-sort-sheet-v3.show{
        transform:
          translate(
            -50%,
            0
          );
      }

      .feature-sort-handle-v3{
        width:44px;
        height:5px;

        border-radius:
          999px;

        background:
          rgba(
            127,
            127,
            127,
            .28
          );

        margin:
          10px
          auto
          4px;
      }

      .feature-sort-sheet-head-v3{
        display:flex;
        align-items:flex-start;
        justify-content:space-between;

        gap:12px;

        padding:
          12px
          18px
          14px;

        border-bottom:
          1px
          solid
          var(--line);
      }

      .feature-sort-sheet-head-v3 h3{
        margin:0;

        color:
          var(--ink);

        font-size:
          18px;

        line-height:
          1.2;
      }

      .feature-sort-sheet-head-v3 p{
        margin:
          5px
          0
          0;

        color:
          var(--muted);

        font-size:
          11px;

        line-height:
          1.5;
      }

      .feature-sort-close-v3{
        flex:
          0 0 auto;

        width:34px;
        height:34px;

        border:
          1px
          solid
          var(--line);

        border-radius:
          50%;

        background:
          var(--soft);

        color:
          var(--ink);

        font-size:
          18px;

        display:grid;
        place-items:center;

        cursor:pointer;
      }

      .feature-sort-list-v3{
        position:relative;

        overflow-y:auto;

        overscroll-behavior:
          contain;

        max-height:
          calc(
            min(
              82vh,
              760px
            )
            - 185px
          );

        padding:
          12px
          14px
          16px;

        -webkit-overflow-scrolling:
          touch;
      }

      .feature-sort-row-v3{
        display:flex;
        align-items:center;

        gap:12px;

        min-height:
          58px;

        padding:
          9px
          10px;

        margin-bottom:
          8px;

        border:
          1px
          solid
          var(--line);

        border-radius:
          15px;

        background:
          var(--card);

        color:
          var(--ink);

        box-shadow:
          0
          5px
          14px
          rgba(
            15,
            23,
            42,
            .04
          );

        user-select:none;
        -webkit-user-select:none;
        -webkit-touch-callout:none;

        touch-action:none;

        transition:
          transform
          .12s
          ease,
          box-shadow
          .12s
          ease,
          opacity
          .12s
          ease,
          border-color
          .12s
          ease;
      }

      .feature-sort-row-v3:last-child{
        margin-bottom:0;
      }

      .feature-sort-row-v3.dragging{
        opacity:.72;

        transform:
          scale(.985);

        border-color:
          rgba(
            59,
            130,
            246,
            .45
          );

        box-shadow:
          0
          10px
          28px
          rgba(
            15,
            23,
            42,
            .14
          );
      }

      .feature-sort-grip-v3{
        flex:
          0 0 auto;

        width:34px;
        height:34px;

        border-radius:
          10px;

        background:
          var(--soft);

        color:
          var(--muted);

        display:grid;
        place-items:center;

        font-size:
          18px;

        line-height:
          1;

        cursor:
          grab;
      }

      .feature-sort-row-v3.dragging
      .feature-sort-grip-v3{
        cursor:
          grabbing;
      }

      .feature-sort-row-copy-v3{
        flex:1;
        min-width:0;
      }

      .feature-sort-row-copy-v3 strong{
        display:block;

        font-size:
          14px;

        line-height:
          1.25;
      }

      .feature-sort-row-copy-v3 small{
        display:block;

        margin-top:
          3px;

        color:
          var(--muted);

        font-size:
          10px;
      }

      .feature-sort-number-v3{
        flex:
          0 0 auto;

        width:
          28px;

        color:
          var(--muted);

        text-align:
          right;

        font-size:
          10px;

        font-weight:
          900;

        letter-spacing:
          .05em;
      }

      .feature-sort-sheet-foot-v3{
        display:grid;

        grid-template-columns:
          1fr
          1.35fr;

        gap:
          10px;

        padding:
          12px
          14px
          calc(
            12px
            + env(
                safe-area-inset-bottom
              )
          );

        border-top:
          1px
          solid
          var(--line);

        background:
          var(--card);
      }

      .feature-sort-action-v3{
        appearance:none;
        -webkit-appearance:none;

        border:
          1px
          solid
          var(--line);

        border-radius:
          14px;

        min-height:
          44px;

        font-size:
          12px;

        font-weight:
          900;

        cursor:
          pointer;
      }

      .feature-sort-reset-v3{
        background:
          var(--soft);

        color:
          var(--muted);
      }

      .feature-sort-save-v3{
        background:
          #111827;

        border-color:
          #111827;

        color:
          #fff;
      }

      [data-theme="dark"]
      .feature-sort-save-v3{
        background:
          #e5e7eb;

        border-color:
          #e5e7eb;

        color:
          #111827;
      }

      .feature-sort-toast-v3{
        position:fixed;

        left:50%;

        bottom:
          calc(
            28px
            + env(
                safe-area-inset-bottom
              )
          );

        z-index:
          10020;

        transform:
          translate(
            -50%,
            20px
          );

        background:
          #111827;

        color:
          #fff;

        border-radius:
          999px;

        padding:
          10px
          14px;

        font-size:
          11px;

        font-weight:
          800;

        opacity:
          0;

        pointer-events:
          none;

        transition:
          opacity
          .18s
          ease,
          transform
          .18s
          ease;

        box-shadow:
          0
          12px
          34px
          rgba(
            15,
            23,
            42,
            .22
          );
      }

      .feature-sort-toast-v3.show{
        opacity:1;

        transform:
          translate(
            -50%,
            0
          );
      }

      body.feature-sort-lock-v3{
        overflow:
          hidden
          !important;

        touch-action:
          none;
      }

      @media (
        min-width:
          720px
      ){
        .feature-sort-sheet-v3{
          bottom:50%;

          border-bottom:
            1px
            solid
            var(--line);

          border-radius:
            24px;

          transform:
            translate(
              -50%,
              60%
            );

          opacity:
            0;

          pointer-events:
            none;
        }

        .feature-sort-sheet-v3.show{
          transform:
            translate(
              -50%,
              50%
            );

          opacity:
            1;

          pointer-events:
            auto;
        }

        .feature-sort-handle-v3{
          display:none;
        }
      }

      @media (
        max-width:
          700px
      ){
        .feature-sort-title-v3 small{
          display:none;
        }

        .feature-sort-open-v3{
          padding:
            8px
            11px;

          font-size:
            10px;
        }
      }
    `;

    document.head.appendChild(
      style
    );
  }

  function ensureToolbar() {
    const box = rail();

    if (!box) {
      return;
    }

    if (
      document.getElementById(
        "featureSortBarV3"
      )
    ) {
      return;
    }

    const bar =
      document.createElement(
        "div"
      );

    bar.id =
      "featureSortBarV3";

    bar.className =
      "feature-sort-bar-v3";

    bar.innerHTML = `
      <div
        class="
          feature-sort-title-v3
        "
      >
        <strong>
          功能列表
        </strong>

        <small>
          可依個人習慣調整順序
        </small>
      </div>

      <button
        type="button"
        id="featureSortOpenV3"
        class="
          feature-sort-open-v3
        "
      >
        自訂排序
      </button>
    `;

    box.parentNode.insertBefore(
      bar,
      box
    );

    $("#featureSortOpenV3")
      ?.addEventListener(
        "click",
        openSheet
      );
  }

  function ensureSheet() {
    if (
      document.getElementById(
        "featureSortSheetV3"
      )
    ) {
      return;
    }

    const backdrop =
      document.createElement(
        "div"
      );

    backdrop.id =
      "featureSortBackdropV3";

    backdrop.className =
      "feature-sort-backdrop-v3";

    const sheet =
      document.createElement(
        "section"
      );

    sheet.id =
      "featureSortSheetV3";

    sheet.className =
      "feature-sort-sheet-v3";

    sheet.setAttribute(
      "role",
      "dialog"
    );

    sheet.setAttribute(
      "aria-modal",
      "true"
    );

    sheet.innerHTML = `
      <div
        class="
          feature-sort-handle-v3
        "
      ></div>

      <div
        class="
          feature-sort-sheet-head-v3
        "
      >
        <div>
          <h3>
            自訂功能順序
          </h3>

          <p>
            按住左側 ☰ 上下拖曳，完成後首頁會立即套用
          </p>
        </div>

        <button
          type="button"
          id="featureSortCloseV3"
          class="
            feature-sort-close-v3
          "
          aria-label="關閉"
        >
          ×
        </button>
      </div>

      <div
        id="featureSortListV3"
        class="
          feature-sort-list-v3
        "
      ></div>

      <div
        class="
          feature-sort-sheet-foot-v3
        "
      >
        <button
          type="button"
          id="featureSortResetV3"
          class="
            feature-sort-action-v3
            feature-sort-reset-v3
          "
        >
          恢復預設
        </button>

        <button
          type="button"
          id="featureSortSaveV3"
          class="
            feature-sort-action-v3
            feature-sort-save-v3
          "
        >
          完成並儲存
        </button>
      </div>
    `;

    const toast =
      document.createElement(
        "div"
      );

    toast.id =
      "featureSortToastV3";

    toast.className =
      "feature-sort-toast-v3";

    toast.textContent =
      "排序已儲存";

    document.body.appendChild(
      backdrop
    );

    document.body.appendChild(
      sheet
    );

    document.body.appendChild(
      toast
    );

    backdrop.addEventListener(
      "click",
      closeSheet
    );

    $("#featureSortCloseV3")
      ?.addEventListener(
        "click",
        closeSheet
      );

    $("#featureSortResetV3")
      ?.addEventListener(
        "click",
        () => {
          workingOrder =
            normalizedOrder(
              DEFAULT_ORDER
            );

          renderList();
        }
      );

    $("#featureSortSaveV3")
      ?.addEventListener(
        "click",
        () => {
          const next =
            normalizedOrder(
              workingOrder
            );

          applyOrder(next);

          saveOrder(next);

          closeSheet();

          showToast();
        }
      );
  }

  function renderList() {
    const list =
      document.getElementById(
        "featureSortListV3"
      );

    if (!list) {
      return;
    }

    const meta =
      featureMeta();

    list.innerHTML =
      workingOrder
        .map(
          (id, index) => {
            const item =
              meta.get(id);

            if (!item) {
              return "";
            }

            return `
              <div
                class="
                  feature-sort-row-v3
                "
                data-sort-id="${id}"
              >
                <div
                  class="
                    feature-sort-grip-v3
                  "
                  aria-hidden="true"
                >
                  ☰
                </div>

                <div
                  class="
                    feature-sort-row-copy-v3
                  "
                >
                  <strong>
                    ${item.name}
                  </strong>

                  ${
                    item.subtitle
                      ? `
                        <small>
                          ${item.subtitle}
                        </small>
                      `
                      : ""
                  }
                </div>

                <span
                  class="
                    feature-sort-number-v3
                  "
                >
                  ${
                    String(
                      index + 1
                    ).padStart(
                      2,
                      "0"
                    )
                  }
                </span>
              </div>
            `;
          }
        )
        .join("");

    bindRows();
  }

  function openSheet() {
    ensureSheet();

    workingOrder =
      normalizedOrder(
        readSavedOrder() ||
        currentOrder()
      );

    renderList();

    document.body
      .classList.add(
        "feature-sort-lock-v3"
      );

    requestAnimationFrame(
      () => {
        $("#featureSortBackdropV3")
          ?.classList.add(
            "show"
          );

        $("#featureSortSheetV3")
          ?.classList.add(
            "show"
          );
      }
    );
  }

  function closeSheet() {
    finishDrag();

    $("#featureSortBackdropV3")
      ?.classList.remove(
        "show"
      );

    $("#featureSortSheetV3")
      ?.classList.remove(
        "show"
      );

    document.body
      .classList.remove(
        "feature-sort-lock-v3"
      );
  }

  function showToast() {
    const toast =
      $("#featureSortToastV3");

    if (!toast) {
      return;
    }

    toast.classList.add(
      "show"
    );

    clearTimeout(
      toast._timer
    );

    toast._timer =
      setTimeout(
        () => {
          toast.classList.remove(
            "show"
          );
        },
        1500
      );
  }

  function rowAtY(y) {
    const list =
      $("#featureSortListV3");

    if (!list) {
      return null;
    }

    const rows =
      $$(
        ".feature-sort-row-v3",
        list
      );

    for (
      const row of rows
    ) {
      const rect =
        row.getBoundingClientRect();

      if (
        y >= rect.top &&
        y <= rect.bottom
      ) {
        return row;
      }
    }

    return null;
  }

  function updateWorkingOrderFromDom() {
    const list =
      $("#featureSortListV3");

    if (!list) {
      return;
    }

    workingOrder =
      $$(
        ".feature-sort-row-v3",
        list
      )
        .map(
          row =>
            row.dataset.sortId
        )
        .filter(Boolean);

    $$(
      ".feature-sort-row-v3",
      list
    )
      .forEach(
        (row, index) => {
          const num =
            row.querySelector(
              ".feature-sort-number-v3"
            );

          if (num) {
            num.textContent =
              String(
                index + 1
              ).padStart(
                2,
                "0"
              );
          }
        }
      );
  }

  function autoScrollList(y) {
    const list =
      $("#featureSortListV3");

    if (!list) {
      return;
    }

    const rect =
      list.getBoundingClientRect();

    const edge =
      54;

    if (
      y <
      rect.top +
      edge
    ) {
      list.scrollTop -=
        12;
    } else if (
      y >
      rect.bottom -
      edge
    ) {
      list.scrollTop +=
        12;
    }
  }

  function moveDrag(y) {
    if (!dragEl) {
      return;
    }

    autoScrollList(y);

    const target =
      rowAtY(y);

    if (
      !target ||
      target === dragEl
    ) {
      return;
    }

    const list =
      $("#featureSortListV3");

    if (!list) {
      return;
    }

    const rect =
      target.getBoundingClientRect();

    const before =
      y <
      rect.top +
      rect.height / 2;

    if (before) {
      list.insertBefore(
        dragEl,
        target
      );
    } else {
      list.insertBefore(
        dragEl,
        target.nextSibling
      );
    }

    updateWorkingOrderFromDom();
  }

  function startDrag(
    id,
    row
  ) {
    dragId =
      id;

    dragEl =
      row;

    row.classList.add(
      "dragging"
    );

    if (
      navigator.vibrate
    ) {
      try {
        navigator.vibrate(
          20
        );
      } catch (e) {}
    }
  }

  function finishDrag() {
    if (dragEl) {
      dragEl.classList.remove(
        "dragging"
      );
    }

    dragId =
      null;

    dragEl =
      null;

    updateWorkingOrderFromDom();
  }

  function bindRows() {
    const list =
      $("#featureSortListV3");

    if (!list) {
      return;
    }

    $$(
      ".feature-sort-row-v3",
      list
    )
      .forEach(row => {
        const grip =
          row.querySelector(
            ".feature-sort-grip-v3"
          );

        if (!grip) {
          return;
        }

        grip.addEventListener(
          "touchstart",
          event => {
            if (
              event.touches.length !==
              1
            ) {
              return;
            }

            event.preventDefault();

            startDrag(
              row.dataset.sortId,
              row
            );
          },
          {
            passive:false
          }
        );

        grip.addEventListener(
          "mousedown",
          event => {
            if (
              event.button !== 0
            ) {
              return;
            }

            event.preventDefault();

            startDrag(
              row.dataset.sortId,
              row
            );
          }
        );
      });

    list.addEventListener(
      "touchmove",
      event => {
        if (
          !dragEl ||
          !event.touches.length
        ) {
          return;
        }

        event.preventDefault();

        moveDrag(
          event.touches[0]
            .clientY
        );
      },
      {
        passive:false
      }
    );

    list.addEventListener(
      "touchend",
      event => {
        if (!dragEl) {
          return;
        }

        event.preventDefault();

        finishDrag();
      },
      {
        passive:false
      }
    );

    list.addEventListener(
      "touchcancel",
      () => {
        finishDrag();
      },
      {
        passive:false
      }
    );

    document.addEventListener(
      "mousemove",
      event => {
        if (!dragEl) {
          return;
        }

        event.preventDefault();

        moveDrag(
          event.clientY
        );
      }
    );

    document.addEventListener(
      "mouseup",
      () => {
        if (!dragEl) {
          return;
        }

        finishDrag();
      }
    );
  }

  function boot() {
    const box =
      rail();

    if (!box) {
      return;
    }

    injectStyles();

    ensureToolbar();

    restoreOrder();

    const observer =
      new MutationObserver(
        mutations => {
          const changed =
            mutations.some(
              mutation =>
                mutation.addedNodes
                  .length
            );

          if (!changed) {
            return;
          }

          setTimeout(
            () => {
              restoreOrder();
            },
            0
          );
        }
      );

    observer.observe(
      box,
      {
        childList:true
      }
    );
  }

  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      () => {
        setTimeout(
          boot,
          0
        );
      }
    );
  } else {
    setTimeout(
      boot,
      0
    );
  }
})();
