/* =========================================================
   首頁功能卡片自訂排序 V2
   - iPhone / iPad Safari 拖曳修正版
   - Android / Desktop 支援
   - localStorage 保存
   - 左右邊緣自動捲動
   ========================================================= */

(function () {
  const STORAGE_KEY =
    "tw-feature-order-v2";

  let editing = false;

  let draggingCard = null;

  let touchDragging = false;

  let mouseDragging = false;

  let lastX = 0;
  let lastY = 0;

  let autoScrollFrame = null;

  let autoScrollDirection = 0;

  const AUTO_SCROLL_EDGE = 70;

  const AUTO_SCROLL_SPEED = 8;


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


  function defaultOrder() {
    return [
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
  }


  function currentOrder() {
    return getCards()
      .map(
        card =>
          card.dataset.feature
      )
      .filter(Boolean);
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


  function saveOrder() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify(
          currentOrder()
        )
      );
    } catch (e) {
      console.warn(
        "feature order save failed",
        e
      );
    }
  }


  function updateIndexes() {
    getCards()
      .forEach(
        (card, index) => {
          const badge =
            card.querySelector(
              ".feature-index"
            );

          if (!badge) {
            return;
          }

          badge.textContent =
            String(
              index + 1
            ).padStart(
              2,
              "0"
            );
        }
      );
  }


  function applyOrder(
    order
  ) {
    const rail =
      getRail();

    if (
      !rail ||
      !Array.isArray(
        order
      )
    ) {
      return;
    }

    const cards =
      new Map(
        getCards()
          .map(
            card => [
              card.dataset.feature,
              card
            ]
          )
      );

    order.forEach(
      id => {
        const card =
          cards.get(id);

        if (!card) {
          return;
        }

        rail.appendChild(
          card
        );

        cards.delete(id);
      }
    );

    /*
      新功能如果沒有存在舊排序中
      自動接到最後面
    */
    cards.forEach(
      card => {
        rail.appendChild(
          card
        );
      }
    );

    updateIndexes();
  }


  function restoreSavedOrder() {
    const saved =
      readOrder();

    if (saved) {
      applyOrder(
        saved
      );
    } else {
      updateIndexes();
    }
  }


  function injectStyles() {
    if (
      document.getElementById(
        "featureSortStyles"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "featureSortStyles";

    style.textContent = `

      .feature-sort-bar{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        margin:
          0
          2px
          10px;
      }

      .feature-sort-label{
        display:flex;
        align-items:center;
        gap:8px;
        min-width:0;
      }

      .feature-sort-label strong{
        color:var(--ink);
        font-size:14px;
        font-weight:900;
      }

      .feature-sort-label small{
        color:var(--muted);
        font-size:10px;
      }

      .feature-sort-actions{
        display:flex;
        align-items:center;
        gap:7px;
        flex:0 0 auto;
      }

      .feature-sort-btn{
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
          800;
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
            .04
          );
      }

      .feature-sort-btn.is-primary{
        background:
          #111827;
        border-color:
          #111827;
        color:
          #fff;
      }

      .feature-sort-btn.is-reset{
        display:none;
        color:
          var(--muted);
      }

      .feature-sort-bar.is-editing
      .feature-sort-btn.is-reset{
        display:inline-flex;
      }

      .feature-sort-tip{
        display:none;
        margin:
          -2px
          2px
          10px;
        color:
          var(--muted);
        font-size:
          10px;
      }

      .feature-sort-tip.show{
        display:block;
      }

      /*
        編輯模式
      */

      #featureRail.feature-sort-editing{
        scroll-snap-type:none;
        touch-action:none;
        overscroll-behavior-x:contain;
      }

      #featureRail.feature-sort-editing
      .feature-card{
        cursor:grab;
        user-select:none;
        -webkit-user-select:none;
        -webkit-touch-callout:none;
        border-style:dashed;

        transition:
          transform
          .12s
          ease,
          box-shadow
          .12s
          ease,
          opacity
          .12s
          ease;
      }

      #featureRail.feature-sort-editing
      .feature-card:hover{
        transform:none;
      }

      #featureRail.feature-sort-editing
      .feature-card:active{
        transform:none;
      }

      /*
        拖曳把手
      */

      #featureRail.feature-sort-editing
      .feature-card::before{
        content:"☰";

        position:absolute;

        right:12px;

        bottom:10px;

        z-index:8;

        width:30px;

        height:30px;

        display:grid;

        place-items:center;

        border-radius:
          9px;

        background:
          rgba(
            127,
            127,
            127,
            .10
          );

        color:
          var(--muted);

        font-size:
          14px;

        font-weight:
          900;
      }

      #featureRail.feature-sort-editing
      .feature-arrow{
        display:none;
      }

      /*
        正在拖
      */

      #featureRail
      .feature-card.is-dragging{
        opacity:.66;

        cursor:grabbing;

        border-style:solid;

        transform:
          scale(.96);

        box-shadow:
          0
          18px
          42px
          rgba(
            15,
            23,
            42,
            .18
          );
      }

      /*
        插入位置
      */

      #featureRail
      .feature-card.is-drop-before{
        box-shadow:
          -5px
          0
          0
          rgba(
            59,
            130,
            246,
            .72
          ),
          0
          10px
          26px
          rgba(
            15,
            23,
            42,
            .08
          );
      }

      #featureRail
      .feature-card.is-drop-after{
        box-shadow:
          5px
          0
          0
          rgba(
            59,
            130,
            246,
            .72
          ),
          0
          10px
          26px
          rgba(
            15,
            23,
            42,
            .08
          );
      }

      /*
        深色模式
      */

      [data-theme="dark"]
      .feature-sort-btn.is-primary{
        background:
          #e5e7eb;

        border-color:
          #e5e7eb;

        color:
          #111827;
      }

      [data-theme="dark"]
      #featureRail.feature-sort-editing
      .feature-card::before{
        background:
          rgba(
            255,
            255,
            255,
            .10
          );
      }

      @media(
        max-width:700px
      ){

        .feature-sort-label small{
          display:none;
        }

        .feature-sort-btn{
          padding:
            8px
            11px;

          font-size:
            10px;
        }

        .feature-sort-tip{
          font-size:
            9px;
        }

      }

    `;

    document.head
      .appendChild(
        style
      );
  }


  function ensureToolbar() {
    const rail =
      getRail();

    if (!rail) {
      return;
    }

    if (
      document.getElementById(
        "featureSortBar"
      )
    ) {
      return;
    }

    const bar =
      document.createElement(
        "div"
      );

    bar.id =
      "featureSortBar";

    bar.className =
      "feature-sort-bar";

    bar.innerHTML = `

      <div
        class="
          feature-sort-label
        "
      >

        <strong>
          功能列表
        </strong>

        <small>
          可依個人習慣調整順序
        </small>

      </div>

      <div
        class="
          feature-sort-actions
        "
      >

        <button
          type="button"
          id="featureSortReset"
          class="
            feature-sort-btn
            is-reset
          "
        >
          恢復預設
        </button>

        <button
          type="button"
          id="featureSortToggle"
          class="
            feature-sort-btn
          "
        >
          自訂排序
        </button>

      </div>

    `;


    const tip =
      document.createElement(
        "div"
      );

    tip.id =
      "featureSortTip";

    tip.className =
      "feature-sort-tip";

    tip.textContent =
      "按住卡片後左右拖曳，放開即可調整順序";


    rail.parentNode
      .insertBefore(
        bar,
        rail
      );


    rail.parentNode
      .insertBefore(
        tip,
        rail
      );


    $("#featureSortToggle")
      ?.addEventListener(
        "click",
        () => {
          setEditing(
            !editing
          );
        }
      );


    $("#featureSortReset")
      ?.addEventListener(
        "click",
        () => {
          localStorage
            .removeItem(
              STORAGE_KEY
            );

          applyOrder(
            defaultOrder()
          );

          saveOrder();
        }
      );
  }


  function clearDropMarks() {
    getCards()
      .forEach(
        card => {
          card.classList.remove(
            "is-drop-before",
            "is-drop-after"
          );
        }
      );
  }


  function cardAtPoint(
    x,
    y
  ) {
    const el =
      document.elementFromPoint(
        x,
        y
      );

    return el
      ?.closest(
        ".feature-card[data-feature]"
      )
      || null;
  }


  function moveCardAtPoint(
    x,
    y
  ) {
    if (!draggingCard) {
      return;
    }

    clearDropMarks();

    const target =
      cardAtPoint(
        x,
        y
      );

    if (
      !target ||
      target ===
        draggingCard
    ) {
      return;
    }

    const rail =
      getRail();

    if (!rail) {
      return;
    }

    const rect =
      target.getBoundingClientRect();

    const midpoint =
      rect.left +
      rect.width / 2;

    const before =
      x <
      midpoint;


    if (before) {

      target.classList.add(
        "is-drop-before"
      );

      rail.insertBefore(
        draggingCard,
        target
      );

    } else {

      target.classList.add(
        "is-drop-after"
      );

      rail.insertBefore(
        draggingCard,
        target.nextSibling
      );

    }

    updateIndexes();
  }


  /* ======================================================
     自動左右捲動
     ====================================================== */

  function stopAutoScroll() {
    autoScrollDirection =
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


  function autoScrollLoop() {
    const rail =
      getRail();

    if (
      !rail ||
      !autoScrollDirection
    ) {
      stopAutoScroll();

      return;
    }

    rail.scrollLeft +=
      autoScrollDirection *
      AUTO_SCROLL_SPEED;

    moveCardAtPoint(
      lastX,
      lastY
    );

    autoScrollFrame =
      requestAnimationFrame(
        autoScrollLoop
      );
  }


  function updateAutoScroll(
    x
  ) {
    const rail =
      getRail();

    if (!rail) {
      return;
    }

    const rect =
      rail.getBoundingClientRect();

    let nextDirection =
      0;

    if (
      x <
      rect.left +
      AUTO_SCROLL_EDGE
    ) {
      nextDirection = -1;
    }

    else if (
      x >
      rect.right -
      AUTO_SCROLL_EDGE
    ) {
      nextDirection = 1;
    }


    if (
      nextDirection ===
      autoScrollDirection
    ) {
      return;
    }


    stopAutoScroll();

    autoScrollDirection =
      nextDirection;


    if (
      autoScrollDirection
    ) {
      autoScrollFrame =
        requestAnimationFrame(
          autoScrollLoop
        );
    }
  }


  /* ======================================================
     Touch
     ====================================================== */

  function touchStart(
    event,
    card
  ) {
    if (!editing) {
      return;
    }

    if (
      !event.touches ||
      event.touches.length !== 1
    ) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    const touch =
      event.touches[0];

    draggingCard =
      card;

    touchDragging =
      true;

    lastX =
      touch.clientX;

    lastY =
      touch.clientY;

    card.classList.add(
      "is-dragging"
    );

    document.body.style
      .overscrollBehavior =
      "none";
  }


  function touchMove(
    event
  ) {
    if (
      !editing ||
      !touchDragging ||
      !draggingCard
    ) {
      return;
    }

    if (
      !event.touches ||
      !event.touches.length
    ) {
      return;
    }

    event.preventDefault();

    const touch =
      event.touches[0];

    lastX =
      touch.clientX;

    lastY =
      touch.clientY;

    moveCardAtPoint(
      lastX,
      lastY
    );

    updateAutoScroll(
      lastX
    );
  }


  function touchEnd(
    event
  ) {
    if (
      !touchDragging
    ) {
      return;
    }

    event?.preventDefault?.();

    finishDrag();
  }


  /* ======================================================
     Mouse / Desktop
     ====================================================== */

  function mouseDown(
    event,
    card
  ) {
    if (!editing) {
      return;
    }

    if (
      event.button !== 0
    ) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    draggingCard =
      card;

    mouseDragging =
      true;

    lastX =
      event.clientX;

    lastY =
      event.clientY;

    card.classList.add(
      "is-dragging"
    );
  }


  function mouseMove(
    event
  ) {
    if (
      !editing ||
      !mouseDragging ||
      !draggingCard
    ) {
      return;
    }

    event.preventDefault();

    lastX =
      event.clientX;

    lastY =
      event.clientY;

    moveCardAtPoint(
      lastX,
      lastY
    );

    updateAutoScroll(
      lastX
    );
  }


  function mouseUp() {
    if (
      !mouseDragging
    ) {
      return;
    }

    finishDrag();
  }


  /* ======================================================
     結束拖曳
     ====================================================== */

  function finishDrag() {
    stopAutoScroll();

    if (
      draggingCard
    ) {
      draggingCard
        .classList.remove(
          "is-dragging"
        );
    }

    clearDropMarks();

    draggingCard =
      null;

    touchDragging =
      false;

    mouseDragging =
      false;

    document.body.style
      .overscrollBehavior =
      "";

    updateIndexes();

    saveOrder();
  }


  /* ======================================================
     卡片綁定
     ====================================================== */

  function bindCard(
    card
  ) {
    if (
      card.dataset.sortBound ===
      "1"
    ) {
      return;
    }

    card.dataset.sortBound =
      "1";


    /*
      編輯模式時
      不要進入功能頁
    */
    card.addEventListener(
      "click",
      event => {

        if (!editing) {
          return;
        }

        event.preventDefault();
        event.stopImmediatePropagation();

      },
      true
    );


    /*
      iPhone / iPad
    */
    card.addEventListener(
      "touchstart",
      event =>
        touchStart(
          event,
          card
        ),
      {
        passive:false
      }
    );


    /*
      Desktop
    */
    card.addEventListener(
      "mousedown",
      event =>
        mouseDown(
          event,
          card
        )
    );
  }


  function bindCards() {
    getCards()
      .forEach(
        bindCard
      );
  }


  /* ======================================================
     編輯模式
     ====================================================== */

  function setEditing(
    next
  ) {
    editing =
      Boolean(
        next
      );

    const rail =
      getRail();

    const bar =
      document.getElementById(
        "featureSortBar"
      );

    const tip =
      document.getElementById(
        "featureSortTip"
      );

    const toggle =
      document.getElementById(
        "featureSortToggle"
      );


    rail?.classList.toggle(
      "feature-sort-editing",
      editing
    );


    bar?.classList.toggle(
      "is-editing",
      editing
    );


    tip?.classList.toggle(
      "show",
      editing
    );


    if (toggle) {

      toggle.classList.toggle(
        "is-primary",
        editing
      );

      toggle.textContent =
        editing
          ? "完成"
          : "自訂排序";

    }


    if (!editing) {

      finishDrag();

      saveOrder();

    }
  }


  /* ======================================================
     啟動
     ====================================================== */

  function boot() {
    const rail =
      getRail();

    if (!rail) {
      return;
    }


    injectStyles();

    ensureToolbar();

    restoreSavedOrder();

    bindCards();


    /*
      全域 touchmove
      iOS Safari 上比綁在單一卡片穩
    */

    document.addEventListener(
      "touchmove",
      touchMove,
      {
        passive:false
      }
    );


    document.addEventListener(
      "touchend",
      touchEnd,
      {
        passive:false
      }
    );


    document.addEventListener(
      "touchcancel",
      touchEnd,
      {
        passive:false
      }
    );


    document.addEventListener(
      "mousemove",
      mouseMove
    );


    document.addEventListener(
      "mouseup",
      mouseUp
    );


    /*
      如果 ui_v2.js 重新產生卡片
      自動重新綁定
    */

    const observer =
      new MutationObserver(
        mutations => {

          const changed =
            mutations.some(
              mutation =>
                mutation
                  .addedNodes
                  .length
            );

          if (!changed) {
            return;
          }

          setTimeout(
            () => {

              restoreSavedOrder();

              bindCards();

              if (editing) {

                rail.classList.add(
                  "feature-sort-editing"
                );

              }

            },
            0
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
