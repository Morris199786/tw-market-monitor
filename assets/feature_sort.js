/* =========================================================
   首頁功能卡片自訂排序
   - 使用者自行排序，不影響其他人
   - 儲存在 localStorage
   - 手機 / 平板 / 電腦皆可拖曳
   - 可恢復預設排序
   ========================================================= */

(function () {
  const STORAGE_KEY =
    "tw-feature-order-v1";

  let editing = false;
  let draggingCard = null;
  let dragPointerId = null;

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
    const rail = getRail();

    if (!rail) {
      return [];
    }

    return $$(
      ".feature-card[data-feature]",
      rail
    );
  }

  function currentOrder() {
    return getCards()
      .map(
        card =>
          card.dataset.feature
      )
      .filter(Boolean);
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

      if (
        !Array.isArray(parsed)
      ) {
        return null;
      }

      return parsed;
    } catch (e) {
      return null;
    }
  }

  function saveOrder() {
    const order =
      currentOrder();

    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(
        order
      )
    );
  }

  function updateIndexes() {
    getCards()
      .forEach(
        (card, i) => {
          const index =
            card.querySelector(
              ".feature-index"
            );

          if (index) {
            index.textContent =
              String(
                i + 1
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

        if (card) {
          rail.appendChild(
            card
          );

          cards.delete(
            id
          );
        }
      }
    );

    /*
      未來若新增功能，
      舊使用者 localStorage 沒有它，
      自動接在最後，不會消失
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
        margin:0 2px 10px;
      }

      .feature-sort-label{
        display:flex;
        align-items:center;
        gap:8px;
        min-width:0;
      }

      .feature-sort-label strong{
        font-size:14px;
        color:var(--ink);
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
        border:1px solid var(--line);
        background:var(--card);
        color:var(--ink);
        border-radius:999px;
        padding:8px 12px;
        font-size:11px;
        line-height:1;
        font-weight:800;
        cursor:pointer;
        box-shadow:0 4px 12px rgba(15,23,42,.04);
      }

      .feature-sort-btn:hover{
        border-color:rgba(59,130,246,.28);
      }

      .feature-sort-btn.is-primary{
        color:#fff;
        background:#111827;
        border-color:#111827;
      }

      .feature-sort-btn.is-reset{
        display:none;
        color:var(--muted);
      }

      .feature-sort-bar.is-editing
      .feature-sort-btn.is-reset{
        display:inline-flex;
      }

      #featureRail.feature-sort-editing{
        touch-action:pan-x;
      }

      #featureRail.feature-sort-editing
      .feature-card{
        cursor:grab;
        user-select:none;
        -webkit-user-select:none;
        -webkit-touch-callout:none;
        overflow:visible;
        border-style:dashed;
        box-shadow:
          0 10px 26px
          rgba(15,23,42,.08);
      }

      #featureRail.feature-sort-editing
      .feature-card:hover{
        transform:none;
      }

      #featureRail.feature-sort-editing
      .feature-card:active{
        transform:none;
      }

      #featureRail.feature-sort-editing
      .feature-card::before{
        content:"⋮⋮";
        position:absolute;
        right:12px;
        bottom:11px;
        z-index:5;
        min-width:28px;
        height:28px;
        display:grid;
        place-items:center;
        border-radius:9px;
        background:rgba(127,127,127,.10);
        color:var(--muted);
        font-size:15px;
        font-weight:900;
        letter-spacing:-3px;
        padding-right:3px;
      }

      #featureRail.feature-sort-editing
      .feature-arrow{
        display:none;
      }

      #featureRail.feature-sort-editing
      .feature-card.is-dragging{
        opacity:.70;
        cursor:grabbing;
        border-style:solid;
        transform:scale(.97);
        box-shadow:
          0 16px 38px
          rgba(15,23,42,.16);
      }

      #featureRail.feature-sort-editing
      .feature-card.is-drop-before{
        box-shadow:
          -5px 0 0
          rgba(59,130,246,.65),
          0 10px 26px
          rgba(15,23,42,.08);
      }

      #featureRail.feature-sort-editing
      .feature-card.is-drop-after{
        box-shadow:
          5px 0 0
          rgba(59,130,246,.65),
          0 10px 26px
          rgba(15,23,42,.08);
      }

      .feature-sort-tip{
        display:none;
        color:var(--muted);
        font-size:10px;
        margin:-3px 2px 10px;
      }

      .feature-sort-tip.show{
        display:block;
      }

      [data-theme="dark"]
      .feature-sort-btn.is-primary{
        background:#e5e7eb;
        border-color:#e5e7eb;
        color:#111827;
      }

      [data-theme="dark"]
      #featureRail.feature-sort-editing
      .feature-card::before{
        background:rgba(255,255,255,.10);
      }

      @media (max-width:700px){
        .feature-sort-bar{
          margin-top:0;
        }

        .feature-sort-label small{
          display:none;
        }

        .feature-sort-btn{
          padding:8px 11px;
          font-size:10px;
        }

        .feature-sort-tip{
          font-size:9px;
        }
      }
    `;

    document.head.appendChild(
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
        class="feature-sort-label"
      >
        <strong>
          功能列表
        </strong>

        <small>
          可依個人習慣調整順序
        </small>
      </div>

      <div
        class="feature-sort-actions"
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
          class="feature-sort-btn"
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
      "按住卡片拖曳到想要的位置，完成後會自動記住";

    rail.parentNode.insertBefore(
      bar,
      rail
    );

    rail.parentNode.insertBefore(
      tip,
      rail
    );

    $("#featureSortToggle")
      .addEventListener(
        "click",
        () => {
          setEditing(
            !editing
          );
        }
      );

    $("#featureSortReset")
      .addEventListener(
        "click",
        () => {
          localStorage.removeItem(
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
      ) || null;
  }

  function moveDraggingCard(
    x,
    y
  ) {
    if (!draggingCard) {
      return;
    }

    const target =
      cardAtPoint(
        x,
        y
      );

    clearDropMarks();

    if (
      !target ||
      target ===
        draggingCard
    ) {
      return;
    }

    const rect =
      target.getBoundingClientRect();

    const before =
      x <
      rect.left +
        rect.width / 2;

    target.classList.add(
      before
        ? "is-drop-before"
        : "is-drop-after"
    );

    const rail =
      getRail();

    if (!rail) {
      return;
    }

    if (before) {
      rail.insertBefore(
        draggingCard,
        target
      );
    } else {
      rail.insertBefore(
        draggingCard,
        target.nextSibling
      );
    }

    updateIndexes();
  }

  function endDrag(
    event
  ) {
    if (!draggingCard) {
      return;
    }

    if (
      event &&
      dragPointerId !== null &&
      event.pointerId !==
        dragPointerId
    ) {
      return;
    }

    try {
      draggingCard.releasePointerCapture(
        dragPointerId
      );
    } catch (e) {
      /* ignore */
    }

    draggingCard.classList.remove(
      "is-dragging"
    );

    clearDropMarks();

    draggingCard =
      null;

    dragPointerId =
      null;

    saveOrder();
  }

  function startDrag(
    event,
    card
  ) {
    if (!editing) {
      return;
    }

    if (
      event.pointerType ===
      "mouse" &&
      event.button !== 0
    ) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    draggingCard =
      card;

    dragPointerId =
      event.pointerId;

    card.classList.add(
      "is-dragging"
    );

    try {
      card.setPointerCapture(
        event.pointerId
      );
    } catch (e) {
      /* ignore */
    }
  }

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

    card.addEventListener(
      "click",
      event => {
        if (editing) {
          event.preventDefault();
          event.stopPropagation();
        }
      },
      true
    );

    card.addEventListener(
      "pointerdown",
      event =>
        startDrag(
          event,
          card
        )
    );

    card.addEventListener(
      "pointermove",
      event => {
        if (
          draggingCard !==
          card
        ) {
          return;
        }

        event.preventDefault();

        moveDraggingCard(
          event.clientX,
          event.clientY
        );
      }
    );

    card.addEventListener(
      "pointerup",
      endDrag
    );

    card.addEventListener(
      "pointercancel",
      endDrag
    );
  }

  function bindCards() {
    getCards()
      .forEach(
        bindCard
      );
  }

  function setEditing(
    next
  ) {
    editing =
      Boolean(next);

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

    if (rail) {
      rail.classList.toggle(
        "feature-sort-editing",
        editing
      );
    }

    if (bar) {
      bar.classList.toggle(
        "is-editing",
        editing
      );
    }

    if (tip) {
      tip.classList.toggle(
        "show",
        editing
      );
    }

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
      endDrag();
      saveOrder();
    }
  }

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
      若其他 JS 重新產生功能卡，
      重新套用使用者排序
    */
    const observer =
      new MutationObserver(
        mutations => {
          const addedCard =
            mutations.some(
              m =>
                [...m.addedNodes]
                  .some(
                    node =>
                      node.nodeType === 1 &&
                      (
                        node.matches?.(
                          ".feature-card"
                        ) ||
                        node.querySelector?.(
                          ".feature-card"
                        )
                      )
                  )
            );

          if (!addedCard) {
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
        childList: true
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
