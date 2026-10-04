/* =========================================================
   首頁功能排序 V4 FIX
   - 保留 V4 檔名與 index 引用
   - 修正 iPhone 拖曳卡住
   - 拿掉會互相打架的 MutationObserver
   - 全域 pointerup / pointercancel 保證解除拖曳
   - 拖曳時清單與下方功能卡同步更新
   ========================================================= */

(function () {
  const STORAGE_KEY =
    "tw-feature-order-v4";

  const DEFAULT_ORDER = [
    "heat",
    "reports",
    "selfReports",
    "flows",
    "volume",
    "turnover",
    "marginLending",
    "ai",
    "holders",
    "monthlyRevenue"
  ];

  let editing = false;

  let dragRow = null;
  let dragGhost = null;

  let activePointerId = null;

  let pointerOffsetY = 0;
  let currentY = 0;

  let autoScrollFrame = null;
  let autoScrollSpeed = 0;

  let orderBeforeEdit = [];


  /* -------------------------------------------------------
     Helpers
  ------------------------------------------------------- */

  function $(
    selector,
    root = document
  ) {
    return root.querySelector(
      selector
    );
  }


  function $$(
    selector,
    root = document
  ) {
    return [
      ...root.querySelectorAll(
        selector
      )
    ];
  }


  function getRail() {
    return document.getElementById(
      "featureRail"
    );
  }


  function getCards() {
    const rail =
      getRail();

    if (!rail) {
      return [];
    }

    return $$(
      ".feature-card[data-feature]",
      rail
    );
  }


  function getFeatureInfo() {
    const map =
      new Map();

    getCards()
      .forEach(
        card => {

          const id =
            card.dataset.feature;

          const name =
            card.querySelector(
              ".feature-copy b"
            )
              ?.textContent
              ?.trim()
            ||
            id;

          const sub =
            card.querySelector(
              ".feature-copy small"
            )
              ?.textContent
              ?.trim()
            ||
            "";

          map.set(
            id,
            {
              id,
              name,
              sub
            }
          );
        }
      );

    return map;
  }


  function getCurrentOrder() {
    return getCards()
      .map(
        card =>
          card.dataset.feature
      )
      .filter(Boolean);
  }


  function normalizeOrder(
    order
  ) {
    const actual =
      getCurrentOrder();

    const result =
      [];

    (order || [])
      .forEach(
        id => {

          if (
            actual.includes(id) &&
            !result.includes(id)
          ) {
            result.push(id);
          }

        }
      );

    actual.forEach(
      id => {

        if (
          !result.includes(id)
        ) {
          result.push(id);
        }

      }
    );

    return result;
  }


  function readOrder() {
    try {

      const raw =
        localStorage.getItem(
          STORAGE_KEY
        );

      if (!raw) {
        return null;
      }

      const parsed =
        JSON.parse(
          raw
        );

      return Array.isArray(
        parsed
      )
        ? parsed
        : null;

    } catch (e) {

      return null;

    }
  }


  function saveOrder(
    order
  ) {
    try {

      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(
          order
        )
      );

    } catch (e) {

      console.warn(
        "Unable to save feature order",
        e
      );

    }
  }


  /* -------------------------------------------------------
     首頁卡片排序
  ------------------------------------------------------- */

  function updateCardNumbers() {
    getCards()
      .forEach(
        (
          card,
          index
        ) => {

          const num =
            card.querySelector(
              ".feature-index"
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


  function applyOrder(
    order
  ) {
    const rail =
      getRail();

    if (!rail) {
      return;
    }

    const normalized =
      normalizeOrder(
        order
      );

    const map =
      new Map(
        getCards()
          .map(
            card => [
              card.dataset.feature,
              card
            ]
          )
      );

    normalized
      .forEach(
        id => {

          const card =
            map.get(id);

          if (card) {
            rail.appendChild(
              card
            );
          }

        }
      );

    updateCardNumbers();
  }


  function restoreSavedOrder() {
    const saved =
      readOrder();

    if (saved) {

      applyOrder(
        saved
      );

    } else {

      updateCardNumbers();

    }
  }


  /* -------------------------------------------------------
     Styles
  ------------------------------------------------------- */

  function injectStyles() {
    if (
      document.getElementById(
        "featureSortV4Styles"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "featureSortV4Styles";

    style.textContent = `

      .feature-sort-head-v4{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        margin:0 2px 10px;
      }

      .feature-sort-head-copy-v4{
        display:flex;
        align-items:center;
        gap:8px;
        min-width:0;
      }

      .feature-sort-head-copy-v4 strong{
        color:var(--ink);
        font-size:14px;
        font-weight:900;
      }

      .feature-sort-head-copy-v4 small{
        color:var(--muted);
        font-size:10px;
      }

      .feature-sort-toggle-v4{
        appearance:none;
        -webkit-appearance:none;

        border:
          1px
          solid
          var(--line);

        background:
          var(--card);

        color:
          var(--ink);

        border-radius:
          999px;

        padding:
          8px
          12px;

        font-size:
          11px;

        line-height:
          1;

        font-weight:
          850;

        cursor:
          pointer;

        box-shadow:
          0
          4px
          12px
          rgba(
            15,
            23,
            42,
            .05
          );
      }

      .feature-sort-toggle-v4.active{
        background:#111827;
        border-color:#111827;
        color:#fff;
      }


      .feature-sort-panel-v4{
        display:none;

        margin:
          0
          0
          16px;

        padding:
          12px;

        border:
          1px
          solid
          var(--line);

        border-radius:
          18px;

        background:
          var(--card);

        box-shadow:
          0
          8px
          24px
          rgba(
            15,
            23,
            42,
            .06
          );
      }

      .feature-sort-panel-v4.show{
        display:block;
      }


      .feature-sort-tip-v4{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:10px;
        margin-bottom:10px;
      }

      .feature-sort-tip-v4 span{
        color:var(--muted);
        font-size:10px;
        line-height:1.4;
      }


      .feature-sort-reset-v4{
        appearance:none;
        -webkit-appearance:none;

        flex:0 0 auto;

        border:0;

        background:transparent;

        color:var(--muted);

        font-size:10px;
        font-weight:800;

        padding:
          6px
          4px;

        cursor:pointer;
      }


      .feature-sort-list-v4{
        display:flex;
        flex-direction:column;
        gap:7px;
      }


      .feature-sort-row-v4{
        position:relative;

        display:flex;
        align-items:center;

        min-height:52px;

        gap:11px;

        padding:
          7px
          10px
          7px
          7px;

        border:
          1px
          solid
          var(--line);

        border-radius:
          14px;

        background:
          var(--card);

        color:
          var(--ink);

        box-shadow:
          0
          3px
          10px
          rgba(
            15,
            23,
            42,
            .035
          );

        transition:
          box-shadow
          .10s
          ease,
          border-color
          .10s
          ease,
          opacity
          .10s
          ease;
      }


      .feature-sort-handle-v4{
        flex:
          0
          0
          auto;

        width:
          38px;

        height:
          38px;

        border:
          0;

        border-radius:
          11px;

        background:
          var(--soft);

        color:
          var(--muted);

        display:grid;
        place-items:center;

        font-size:
          19px;

        font-weight:
          900;

        line-height:
          1;

        cursor:
          grab;

        touch-action:
          none;

        user-select:
          none;

        -webkit-user-select:
          none;

        -webkit-touch-callout:
          none;
      }


      .feature-sort-handle-v4:active{
        cursor:grabbing;
      }


      .feature-sort-row-copy-v4{
        flex:1;
        min-width:0;
      }

      .feature-sort-row-copy-v4 strong{
        display:block;

        color:
          var(--ink);

        font-size:
          13px;

        font-weight:
          900;

        line-height:
          1.25;
      }

      .feature-sort-row-copy-v4 small{
        display:block;

        margin-top:
          3px;

        color:
          var(--muted);

        font-size:
          9px;
      }


      .feature-sort-number-v4{
        flex:
          0
          0
          auto;

        min-width:
          25px;

        color:
          var(--muted);

        font-size:
          9px;

        font-weight:
          900;

        letter-spacing:
          .05em;

        text-align:
          right;
      }


      .feature-sort-row-v4.drag-source{
        opacity:.30;
        border-style:dashed;
      }


      .feature-sort-ghost-v4{
        position:fixed;

        z-index:10000;

        pointer-events:none;

        display:flex;
        align-items:center;

        min-height:
          52px;

        gap:
          11px;

        padding:
          7px
          10px
          7px
          7px;

        border:
          1px
          solid
          rgba(
            59,
            130,
            246,
            .45
          );

        border-radius:
          14px;

        background:
          var(--card);

        color:
          var(--ink);

        box-shadow:
          0
          16px
          38px
          rgba(
            15,
            23,
            42,
            .22
          );

        opacity:
          .98;

        transform:
          scale(
            1.015
          );
      }


      .feature-sort-row-v4.drop-before{
        box-shadow:
          0
          -3px
          0
          #3b82f6,
          0
          3px
          10px
          rgba(
            15,
            23,
            42,
            .035
          );
      }


      .feature-sort-row-v4.drop-after{
        box-shadow:
          0
          3px
          0
          #3b82f6,
          0
          3px
          10px
          rgba(
            15,
            23,
            42,
            .035
          );
      }


      .feature-sort-footer-v4{
        display:none;
        margin-top:11px;
      }

      .feature-sort-panel-v4.show
      .feature-sort-footer-v4{
        display:block;
      }


      .feature-sort-done-v4{
        appearance:none;
        -webkit-appearance:none;

        width:100%;

        min-height:43px;

        border:
          1px
          solid
          #111827;

        border-radius:
          13px;

        background:
          #111827;

        color:
          #fff;

        font-size:
          12px;

        font-weight:
          900;

        cursor:pointer;
      }


      .feature-sort-toast-v4{
        position:fixed;

        left:50%;

        bottom:
          calc(
            26px
            +
            env(
              safe-area-inset-bottom
            )
          );

        z-index:
          12000;

        transform:
          translate(
            -50%,
            18px
          );

        padding:
          9px
          14px;

        border-radius:
          999px;

        background:
          #111827;

        color:
          #fff;

        font-size:
          10px;

        font-weight:
          850;

        opacity:
          0;

        pointer-events:
          none;

        transition:
          opacity
          .16s
          ease,
          transform
          .16s
          ease;

        box-shadow:
          0
          12px
          30px
          rgba(
            15,
            23,
            42,
            .20
          );
      }

      .feature-sort-toast-v4.show{
        opacity:1;

        transform:
          translate(
            -50%,
            0
          );
      }


      body.feature-sort-dragging-v4{
        user-select:none;
        -webkit-user-select:none;
        -webkit-touch-callout:none;
      }


      [data-theme="dark"]
      .feature-sort-toggle-v4.active,
      [data-theme="dark"]
      .feature-sort-done-v4{
        background:#e5e7eb;
        border-color:#e5e7eb;
        color:#111827;
      }


      @media(
        max-width:
          700px
      ){

        .feature-sort-head-copy-v4 small{
          display:none;
        }

        .feature-sort-toggle-v4{
          padding:
            8px
            11px;

          font-size:
            10px;
        }

        .feature-sort-panel-v4{
          padding:
            10px;

          border-radius:
            16px;
        }

        .feature-sort-row-v4{
          min-height:
            50px;
        }

      }

    `;

    document.head.appendChild(
      style
    );
  }


  /* -------------------------------------------------------
     UI
  ------------------------------------------------------- */

  function ensureUI() {
    const rail =
      getRail();

    if (!rail) {
      return;
    }


    if (
      document.getElementById(
        "featureSortHeadV4"
      )
    ) {
      return;
    }


    const head =
      document.createElement(
        "div"
      );

    head.id =
      "featureSortHeadV4";

    head.className =
      "feature-sort-head-v4";


    head.innerHTML = `
      <div
        class="
          feature-sort-head-copy-v4
        "
      >

        <strong>
          功能列表
        </strong>

        <small>
          可自訂常用功能順序
        </small>

      </div>

      <button
        type="button"
        id="featureSortToggleV4"
        class="
          feature-sort-toggle-v4
        "
      >
        自訂排序
      </button>
    `;


    const panel =
      document.createElement(
        "div"
      );

    panel.id =
      "featureSortPanelV4";

    panel.className =
      "feature-sort-panel-v4";


    panel.innerHTML = `
      <div
        class="
          feature-sort-tip-v4
        "
      >

        <span>
          抓住左側 ☰ 上下拖曳
        </span>

        <button
          type="button"
          id="featureSortResetV4"
          class="
            feature-sort-reset-v4
          "
        >
          恢復預設
        </button>

      </div>

      <div
        id="featureSortListV4"
        class="
          feature-sort-list-v4
        "
      ></div>

      <div
        class="
          feature-sort-footer-v4
        "
      >

        <button
          type="button"
          id="featureSortDoneV4"
          class="
            feature-sort-done-v4
          "
        >
          完成
        </button>

      </div>
    `;


    const toast =
      document.createElement(
        "div"
      );

    toast.id =
      "featureSortToastV4";

    toast.className =
      "feature-sort-toast-v4";

    toast.textContent =
      "功能順序已儲存";


    rail.parentNode.insertBefore(
      head,
      rail
    );


    rail.parentNode.insertBefore(
      panel,
      rail
    );


    document.body.appendChild(
      toast
    );


    $("#featureSortToggleV4")
      ?.addEventListener(
        "click",
        toggleEditing
      );


    $("#featureSortDoneV4")
      ?.addEventListener(
        "click",
        finishEditing
      );


    $("#featureSortResetV4")
      ?.addEventListener(
        "click",
        () => {

          stopDrag();

          const order =
            normalizeOrder(
              DEFAULT_ORDER
            );

          applyOrder(
            order
          );

          renderSortList(
            order
          );

        }
      );
  }


  /* -------------------------------------------------------
     Render list
  ------------------------------------------------------- */

  function renderSortList(
    order
  ) {
    const list =
      $("#featureSortListV4");

    if (!list) {
      return;
    }


    const meta =
      getFeatureInfo();


    const normalized =
      normalizeOrder(
        order
      );


    list.innerHTML =
      normalized
        .map(
          (
            id,
            index
          ) => {

            const info =
              meta.get(id);

            if (!info) {
              return "";
            }


            return `
              <div
                class="
                  feature-sort-row-v4
                "
                data-sort-id="${id}"
              >

                <button
                  type="button"
                  class="
                    feature-sort-handle-v4
                  "
                  aria-label="
                    拖曳
                    ${info.name}
                  "
                >
                  ☰
                </button>

                <div
                  class="
                    feature-sort-row-copy-v4
                  "
                >

                  <strong>
                    ${info.name}
                  </strong>

                  ${
                    info.sub
                      ? `
                        <small>
                          ${info.sub}
                        </small>
                      `
                      : ""
                  }

                </div>

                <span
                  class="
                    feature-sort-number-v4
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


    bindHandles();
  }


  function listOrder() {
    const list =
      $("#featureSortListV4");

    if (!list) {
      return [];
    }


    return $$(
      ".feature-sort-row-v4",
      list
    )
      .map(
        row =>
          row.dataset.sortId
      )
      .filter(Boolean);
  }


  function syncNumbers() {
    const list =
      $("#featureSortListV4");

    if (!list) {
      return;
    }


    $$(
      ".feature-sort-row-v4",
      list
    )
      .forEach(
        (
          row,
          index
        ) => {

          const n =
            row.querySelector(
              ".feature-sort-number-v4"
            );

          if (n) {
            n.textContent =
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


  function syncCardsLive() {
    const order =
      listOrder();

    if (!order.length) {
      return;
    }

    applyOrder(
      order
    );

    syncNumbers();
  }


  /* -------------------------------------------------------
     Edit
  ------------------------------------------------------- */

  function toggleEditing() {
    if (editing) {
      finishEditing();
      return;
    }

    editing = true;

    orderBeforeEdit =
      normalizeOrder(
        getCurrentOrder()
      );

    const order =
      normalizeOrder(
        readOrder() ||
        getCurrentOrder()
      );

    renderSortList(
      order
    );

    $("#featureSortPanelV4")
      ?.classList.add(
        "show"
      );

    const toggle =
      $("#featureSortToggleV4");

    toggle?.classList.add(
      "active"
    );

    if (toggle) {
      toggle.textContent =
        "編輯中";
    }
  }


  function finishEditing() {
    if (!editing) {
      return;
    }

    stopDrag();

    const order =
      listOrder();

    if (order.length) {

      applyOrder(
        order
      );

      saveOrder(
        order
      );

    }

    editing =
      false;

    $("#featureSortPanelV4")
      ?.classList.remove(
        "show"
      );

    const toggle =
      $("#featureSortToggleV4");

    toggle?.classList.remove(
      "active"
    );

    if (toggle) {
      toggle.textContent =
        "自訂排序";
    }

    showToast();
  }


  function showToast() {
    const toast =
      $("#featureSortToastV4");

    if (!toast) {
      return;
    }

    toast.classList.add(
      "show"
    );

    clearTimeout(
      toast._hideTimer
    );

    toast._hideTimer =
      setTimeout(
        () => {

          toast.classList.remove(
            "show"
          );

        },
        1400
      );
  }


  /* -------------------------------------------------------
     Drag helpers
  ------------------------------------------------------- */

  function clearDropMarks() {
    const list =
      $("#featureSortListV4");

    if (!list) {
      return;
    }

    $$(
      ".feature-sort-row-v4",
      list
    )
      .forEach(
        row => {

          row.classList.remove(
            "drop-before",
            "drop-after"
          );

        }
      );
  }


  function createGhost(
    row
  ) {
    const rect =
      row.getBoundingClientRect();

    const ghost =
      row.cloneNode(
        true
      );

    ghost.classList.remove(
      "drag-source",
      "drop-before",
      "drop-after"
    );

    ghost.classList.add(
      "feature-sort-ghost-v4"
    );

    ghost.style.left =
      `${rect.left}px`;

    ghost.style.top =
      `${rect.top}px`;

    ghost.style.width =
      `${rect.width}px`;

    document.body.appendChild(
      ghost
    );

    return ghost;
  }


  function moveGhost(
    clientY
  ) {
    if (!dragGhost) {
      return;
    }

    dragGhost.style.top =
      `${
        clientY -
        pointerOffsetY
      }px`;
  }


  function getTargetRow(
    clientY
  ) {
    const list =
      $("#featureSortListV4");

    if (!list) {
      return null;
    }

    const rows =
      $$(
        ".feature-sort-row-v4",
        list
      )
        .filter(
          row =>
            row !==
            dragRow
        );

    for (
      const row
      of rows
    ) {

      const rect =
        row.getBoundingClientRect();

      if (
        clientY >=
          rect.top &&
        clientY <=
          rect.bottom
      ) {
        return row;
      }

    }

    return null;
  }


  function reorderAt(
    clientY
  ) {
    if (!dragRow) {
      return;
    }

    const list =
      $("#featureSortListV4");

    if (!list) {
      return;
    }

    clearDropMarks();

    const target =
      getTargetRow(
        clientY
      );

    if (!target) {

      const rows =
        $$(
          ".feature-sort-row-v4",
          list
        )
          .filter(
            row =>
              row !==
              dragRow
          );

      if (!rows.length) {
        return;
      }

      const first =
        rows[0]
          .getBoundingClientRect();

      const last =
        rows[
          rows.length - 1
        ]
          .getBoundingClientRect();

      if (
        clientY <
        first.top
      ) {

        list.insertBefore(
          dragRow,
          rows[0]
        );

        syncCardsLive();

      }

      else if (
        clientY >
        last.bottom
      ) {

        list.appendChild(
          dragRow
        );

        syncCardsLive();

      }

      return;
    }

    const rect =
      target
        .getBoundingClientRect();

    const before =
      clientY <
      rect.top +
      rect.height / 2;

    target.classList.add(
      before
        ? "drop-before"
        : "drop-after"
    );

    const beforeNode =
      dragRow.previousElementSibling;

    const afterNode =
      dragRow.nextElementSibling;

    if (before) {

      if (
        target !==
        afterNode
      ) {

        list.insertBefore(
          dragRow,
          target
        );

        syncCardsLive();

      }

    } else {

      if (
        target !==
        beforeNode
      ) {

        list.insertBefore(
          dragRow,
          target.nextSibling
        );

        syncCardsLive();

      }

    }
  }


  /* -------------------------------------------------------
     Auto scroll
  ------------------------------------------------------- */

  function stopAutoScroll() {
    autoScrollSpeed =
      0;

    if (
      autoScrollFrame
    ) {

      cancelAnimationFrame(
        autoScrollFrame
      );

      autoScrollFrame =
        null;

    }
  }


  function runAutoScroll() {
    if (
      !dragRow ||
      !autoScrollSpeed
    ) {

      stopAutoScroll();

      return;
    }

    window.scrollBy(
      0,
      autoScrollSpeed
    );

    reorderAt(
      currentY
    );

    autoScrollFrame =
      requestAnimationFrame(
        runAutoScroll
      );
  }


  function updateAutoScroll(
    clientY
  ) {
    const edge =
      85;

    let speed =
      0;

    if (
      clientY <
      edge
    ) {

      speed =
        -9;

    }

    else if (
      clientY >
      window.innerHeight -
      edge
    ) {

      speed =
        9;

    }

    if (
      speed ===
      autoScrollSpeed
    ) {
      return;
    }

    stopAutoScroll();

    autoScrollSpeed =
      speed;

    if (
      speed
    ) {

      autoScrollFrame =
        requestAnimationFrame(
          runAutoScroll
        );

    }
  }


  /* -------------------------------------------------------
     Drag lifecycle
  ------------------------------------------------------- */

  function startDrag(
    row,
    clientY,
    pointerId
  ) {
    if (!editing) {
      return;
    }

    stopDrag();

    dragRow =
      row;

    activePointerId =
      pointerId;

    const rect =
      row.getBoundingClientRect();

    pointerOffsetY =
      clientY -
      rect.top;

    currentY =
      clientY;

    dragGhost =
      createGhost(
        row
      );

    row.classList.add(
      "drag-source"
    );

    document.body
      .classList.add(
        "feature-sort-dragging-v4"
      );

    document.documentElement
      .style
      .overscrollBehavior =
      "none";

    document.body
      .style
      .overscrollBehavior =
      "none";
  }


  function dragMove(
    clientY
  ) {
    if (!dragRow) {
      return;
    }

    currentY =
      clientY;

    moveGhost(
      clientY
    );

    reorderAt(
      clientY
    );

    updateAutoScroll(
      clientY
    );
  }


  function stopDrag() {
    clearDropMarks();

    if (
      dragRow
    ) {

      dragRow.classList.remove(
        "drag-source"
      );

    }

    if (
      dragGhost
    ) {

      dragGhost.remove();

    }

    dragRow =
      null;

    dragGhost =
      null;

    activePointerId =
      null;

    stopAutoScroll();

    document.body
      .classList.remove(
        "feature-sort-dragging-v4"
      );

    document.documentElement
      .style
      .overscrollBehavior =
      "";

    document.body
      .style
      .overscrollBehavior =
      "";

    syncNumbers();
  }


  /* -------------------------------------------------------
     Handle binding
  ------------------------------------------------------- */

  function bindHandles() {
    const list =
      $("#featureSortListV4");

    if (!list) {
      return;
    }

    $$(
      ".feature-sort-handle-v4",
      list
    )
      .forEach(
        handle => {

          if (
            handle.dataset.dragBound ===
            "1"
          ) {
            return;
          }

          handle.dataset.dragBound =
            "1";

          handle.addEventListener(
            "pointerdown",
            event => {

              if (
                event.pointerType ===
                  "mouse" &&
                event.button !== 0
              ) {
                return;
              }

              event.preventDefault();
              event.stopPropagation();

              const row =
                handle.closest(
                  ".feature-sort-row-v4"
                );

              if (!row) {
                return;
              }

              try {

                handle.setPointerCapture(
                  event.pointerId
                );

              } catch (e) {}

              startDrag(
                row,
                event.clientY,
                event.pointerId
              );

            }
          );

        }
      );
  }


  /* -------------------------------------------------------
     Global pointer events
     關鍵修正：
     不再只監聽 handle 本身
  ------------------------------------------------------- */

  function bindGlobalPointerEvents() {
    if (
      window.__featureSortV4GlobalBound
    ) {
      return;
    }

    window.__featureSortV4GlobalBound =
      true;


    window.addEventListener(
      "pointermove",
      event => {

        if (!dragRow) {
          return;
        }

        if (
          activePointerId !==
            null &&
          event.pointerId !==
            activePointerId
        ) {
          return;
        }

        event.preventDefault();

        dragMove(
          event.clientY
        );

      },
      {
        passive:false
      }
    );


    window.addEventListener(
      "pointerup",
      event => {

        if (!dragRow) {
          return;
        }

        if (
          activePointerId !==
            null &&
          event.pointerId !==
            activePointerId
        ) {
          return;
        }

        stopDrag();

      },
      {
        passive:true
      }
    );


    window.addEventListener(
      "pointercancel",
      () => {

        if (!dragRow) {
          return;
        }

        stopDrag();

      },
      {
        passive:true
      }
    );


    window.addEventListener(
      "blur",
      () => {

        if (!dragRow) {
          return;
        }

        stopDrag();

      }
    );


    document.addEventListener(
      "visibilitychange",
      () => {

        if (
          document.hidden &&
          dragRow
        ) {

          stopDrag();

        }

      }
    );
  }


  /* -------------------------------------------------------
     Boot
  ------------------------------------------------------- */

  function boot() {
    const rail =
      getRail();

    if (!rail) {
      return;
    }

    injectStyles();

    ensureUI();

    restoreSavedOrder();

    bindGlobalPointerEvents();

    /*
      注意：
      這裡刻意不再監聽 featureRail MutationObserver
      因為拖曳時 applyOrder() 本身會搬動 DOM
      舊版 Observer 會一直把舊排序套回去
    */
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
