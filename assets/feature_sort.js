/* =========================================================
   首頁功能排序 V4
   Handle-only vertical drag
   - 左側 ☰ 拖曳
   - 排序清單與下方功能卡同步
   - iPhone / iPad / Desktop
   - localStorage 儲存
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

  let pointerOffsetY = 0;

  let currentY = 0;

  let autoScrollTimer = null;


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
        JSON.parse(raw);

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
        (card, index) => {

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

      /* =========================
         Toolbar
      ========================= */

      .feature-sort-head-v4{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        margin:
          0
          2px
          10px;
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

        cursor:pointer;

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
        background:
          #111827;

        border-color:
          #111827;

        color:
          #fff;
      }


      /* =========================
         Sort panel
      ========================= */

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

        margin-bottom:
          10px;
      }

      .feature-sort-tip-v4 span{
        color:
          var(--muted);

        font-size:
          10px;

        line-height:
          1.4;
      }


      .feature-sort-reset-v4{
        appearance:none;
        -webkit-appearance:none;

        flex:
          0 0 auto;

        border:
          0;

        background:
          transparent;

        color:
          var(--muted);

        font-size:
          10px;

        font-weight:
          800;

        padding:
          6px
          4px;

        cursor:pointer;
      }


      /* =========================
         List
      ========================= */

      .feature-sort-list-v4{
        display:flex;
        flex-direction:column;
        gap:7px;
      }


      .feature-sort-row-v4{
        position:relative;

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
          transform
          .12s
          ease,
          box-shadow
          .12s
          ease,
          border-color
          .12s
          ease;
      }


      /* =========================
         Handle
      ========================= */

      .feature-sort-handle-v4{
        flex:
          0 0 auto;

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
        cursor:
          grabbing;
      }


      /* =========================
         Row copy
      ========================= */

      .feature-sort-row-copy-v4{
        flex:
          1;

        min-width:
          0;
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


      /* =========================
         Drag state
      ========================= */

      .feature-sort-row-v4.drag-source{
        opacity:
          .22;

        border-style:
          dashed;
      }


      .feature-sort-ghost-v4{
        position:
          fixed;

        left:
          12px;

        right:
          12px;

        z-index:
          10000;

        pointer-events:
          none;

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
            .38
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

        transform:
          scale(
            1.015
          );

        opacity:
          .97;
      }


      .feature-sort-row-v4.drop-before{
        border-top-color:
          #3b82f6;

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
        border-bottom-color:
          #3b82f6;

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


      /* =========================
         Footer
      ========================= */

      .feature-sort-footer-v4{
        display:none;

        margin-top:
          11px;
      }

      .feature-sort-panel-v4.show
      .feature-sort-footer-v4{
        display:block;
      }


      .feature-sort-done-v4{
        appearance:none;
        -webkit-appearance:none;

        width:
          100%;

        min-height:
          43px;

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


      /* =========================
         Toast
      ========================= */

      .feature-sort-toast-v4{
        position:
          fixed;

        left:
          50%;

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
        opacity:
          1;

        transform:
          translate(
            -50%,
            0
          );
      }


      /* =========================
         Dark
      ========================= */

      [data-theme="dark"]
      .feature-sort-toggle-v4.active,
      [data-theme="dark"]
      .feature-sort-done-v4{
        background:
          #e5e7eb;

        border-color:
          #e5e7eb;

        color:
          #111827;
      }


      /* =========================
         Mobile
      ========================= */

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
     Toolbar / panel
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

          saveOrder(
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

    applyOrder(
      order
    );

    syncNumbers();
  }


  /* -------------------------------------------------------
     Edit mode
  ------------------------------------------------------- */

  function toggleEditing() {
    editing =
      !editing;


    const panel =
      $("#featureSortPanelV4");

    const toggle =
      $("#featureSortToggleV4");


    if (editing) {

      const order =
        normalizeOrder(
          readOrder() ||
          getCurrentOrder()
        );

      renderSortList(
        order
      );

      panel?.classList.add(
        "show"
      );

      toggle?.classList.add(
        "active"
      );

      if (toggle) {
        toggle.textContent =
          "編輯中";
      }


    } else {

      finishEditing();

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
     Drag
  ------------------------------------------------------- */

  function clearDropMarks() {
    $$(
      ".feature-sort-row-v4"
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


    ghost.style.width =
      `${rect.width}px`;


    ghost.style.left =
      `${rect.left}px`;


    ghost.style.right =
      "auto";


    ghost.style.top =
      `${rect.top}px`;


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


      const firstRect =
        rows[0]
          .getBoundingClientRect();


      const lastRect =
        rows[
          rows.length - 1
        ]
          .getBoundingClientRect();


      if (
        clientY <
        firstRect.top
      ) {

        list.insertBefore(
          dragRow,
          rows[0]
        );


        syncCardsLive();

      } else if (
        clientY >
        lastRect.bottom
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


    if (before) {

      if (
        dragRow.nextSibling !==
        target
      ) {

        list.insertBefore(
          dragRow,
          target
        );

        syncCardsLive();

      }

    } else {

      if (
        target.nextSibling !==
        dragRow
      ) {

        list.insertBefore(
          dragRow,
          target.nextSibling
        );

        syncCardsLive();

      }

    }
  }


  function autoScroll(
    clientY
  ) {
    const edge =
      90;


    let speed =
      0;


    if (
      clientY <
      edge
    ) {

      speed =
        -10;

    } else if (
      clientY >
      window.innerHeight -
      edge
    ) {

      speed =
        10;

    }


    if (!speed) {

      if (
        autoScrollTimer
      ) {

        cancelAnimationFrame(
          autoScrollTimer
        );

        autoScrollTimer =
          null;

      }

      return;
    }


    if (
      autoScrollTimer
    ) {
      return;
    }


    const loop =
      () => {

        if (
          !dragRow
        ) {

          autoScrollTimer =
            null;

          return;
        }


        window.scrollBy(
          0,
          speed
        );


        reorderAt(
          currentY
        );


        autoScrollTimer =
          requestAnimationFrame(
            loop
          );
      };


    autoScrollTimer =
      requestAnimationFrame(
        loop
      );
  }


  function startDrag(
    row,
    clientY
  ) {
    if (!editing) {
      return;
    }


    stopDrag();


    dragRow =
      row;


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


    document.documentElement
      .style
      .overscrollBehavior =
      "none";


    document.body.style
      .overscrollBehavior =
      "none";


    if (
      navigator.vibrate
    ) {

      try {

        navigator.vibrate(
          12
        );

      } catch (e) {}

    }
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


    autoScroll(
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


    if (
      autoScrollTimer
    ) {

      cancelAnimationFrame(
        autoScrollTimer
      );

      autoScrollTimer =
        null;

    }


    document.documentElement
      .style
      .overscrollBehavior =
      "";


    document.body.style
      .overscrollBehavior =
      "";


    syncCardsLive();
  }


  /* -------------------------------------------------------
     Handles
  ------------------------------------------------------- */

  function bindHandles() {
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

          const handle =
            row.querySelector(
              ".feature-sort-handle-v4"
            );


          if (!handle) {
            return;
          }


          /*
            Pointer Events
            Desktop / newer iOS
          */

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


              try {

                handle.setPointerCapture(
                  event.pointerId
                );

              } catch (e) {}


              startDrag(
                row,
                event.clientY
              );

            }
          );


          handle.addEventListener(
            "pointermove",
            event => {

              if (!dragRow) {
                return;
              }


              event.preventDefault();


              dragMove(
                event.clientY
              );

            }
          );


          handle.addEventListener(
            "pointerup",
            event => {

              if (!dragRow) {
                return;
              }


              event.preventDefault();


              try {

                handle.releasePointerCapture(
                  event.pointerId
                );

              } catch (e) {}


              stopDrag();

            }
          );


          handle.addEventListener(
            "pointercancel",
            () => {

              stopDrag();

            }
          );

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


    /*
      如果其他 JS 未來重新建立
      feature cards，自動重新套用
    */

    const observer =
      new MutationObserver(
        mutations => {

          const changed =
            mutations.some(
              mutation =>
                mutation.addedNodes
                  .length >
                0
            );


          if (!changed) {
            return;
          }


          requestAnimationFrame(
            () => {

              const saved =
                readOrder();

              if (saved) {
                applyOrder(
                  saved
                );
              }

            }
          );

        }
      );


    observer.observe(
      rail,
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
