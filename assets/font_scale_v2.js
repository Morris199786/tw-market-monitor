/* =========================================================
   全站文字縮放 V2
   - 只改文字，不 zoom 整個頁面
   - 90% / 100% / 110% / 120%
   - iPhone / iPad / Desktop 一致
   - 動態新增內容也會自動套用
   ========================================================= */

(function () {
  const LEVELS = [
    0.9,
    1,
    1.1,
    1.2
  ];

  const STORAGE_KEY =
    "tw-font-scale";

  let currentScale =
    1;

  let observer =
    null;

  const SKIP_TAGS =
    new Set([
      "SCRIPT",
      "STYLE",
      "SVG",
      "PATH",
      "RECT",
      "CIRCLE",
      "LINE",
      "POLYLINE",
      "POLYGON",
      "DEFS",
      "USE"
    ]);


  /* -------------------------------------------------
     關閉舊版整頁縮放
  ------------------------------------------------- */

  function injectResetStyle() {
    if (
      document.getElementById(
        "twFontScaleResetV2"
      )
    ) {
      return;
    }

    const style =
      document.createElement(
        "style"
      );

    style.id =
      "twFontScaleResetV2";

    style.textContent = `
      /*
        關掉舊版整頁 zoom / 父層 font-size 縮放
        新版只針對真正的文字節點調整字級
      */

      html{
        font-size:
          16px
          !important;
      }

      body{
        zoom:
          1
          !important;
      }

      #home,
      .page,
      header .head{
        font-size:
          1em
          !important;
      }
    `;

    document.head
      .appendChild(
        style
      );
  }


  /* -------------------------------------------------
     判斷元素本身是否真的有文字
  ------------------------------------------------- */

  function hasDirectText(
    el
  ) {
    if (
      !el ||
      el.nodeType !== 1 ||
      SKIP_TAGS.has(
        el.tagName
      )
    ) {
      return false;
    }

    /*
      表單類元件的文字
      也要一起縮放
    */
    if (
      [
        "INPUT",
        "TEXTAREA",
        "SELECT",
        "OPTION"
      ].includes(
        el.tagName
      )
    ) {
      return true;
    }

    return [
      ...el.childNodes
    ].some(
      node =>
        node.nodeType ===
          Node.TEXT_NODE &&
        node.textContent
          .trim()
    );
  }


  /* -------------------------------------------------
     找出需要縮放的文字元素
  ------------------------------------------------- */

  function getTargets(
    root
  ) {
    const targets =
      [];

    if (
      root?.nodeType === 1 &&
      hasDirectText(
        root
      )
    ) {
      targets.push(
        root
      );
    }

    if (
      root?.querySelectorAll
    ) {
      root
        .querySelectorAll(
          "*"
        )
        .forEach(
          el => {
            if (
              hasDirectText(
                el
              )
            ) {
              targets.push(
                el
              );
            }
          }
        );
    }

    return targets;
  }


  /* -------------------------------------------------
     記住每個元素原始字體大小
  ------------------------------------------------- */

  function rememberBase(
    el
  ) {
    if (
      el.dataset
        .twTextBasePx
    ) {
      return;
    }

    const px =
      parseFloat(
        getComputedStyle(
          el
        ).fontSize
      );

    if (
      !Number.isFinite(
        px
      ) ||
      px <= 0
    ) {
      return;
    }

    el.dataset
      .twTextBasePx =
      String(
        px
      );

    /*
      記錄原本 inline style
      之後切回 100% 時可以恢復
    */
    el.dataset
      .twTextOriginalFont =
      el.style
        .getPropertyValue(
          "font-size"
        ) ||
      "__none__";

    el.dataset
      .twTextOriginalPriority =
      el.style
        .getPropertyPriority(
          "font-size"
        ) ||
      "";
  }


  /* -------------------------------------------------
     恢復原始字體
  ------------------------------------------------- */

  function restoreOriginal(
    el
  ) {
    const value =
      el.dataset
        .twTextOriginalFont;

    const priority =
      el.dataset
        .twTextOriginalPriority ||
      "";

    if (
      !value ||
      value ===
        "__none__"
    ) {
      el.style
        .removeProperty(
          "font-size"
        );
    } else {
      el.style
        .setProperty(
          "font-size",
          value,
          priority
        );
    }
  }


  /* -------------------------------------------------
     動態內容新增時
     避免父層已經 120% 導致子元素再乘一次
  ------------------------------------------------- */

  function temporarilyRestoreAncestorBases(
    root
  ) {
    const changed =
      [];

    let parent =
      root?.parentElement;

    while (
      parent
    ) {
      const base =
        Number(
          parent.dataset
            .twTextBasePx
        );

      if (
        Number.isFinite(
          base
        )
      ) {
        changed.push({
          el:
            parent,

          value:
            parent.style
              .getPropertyValue(
                "font-size"
              ),

          priority:
            parent.style
              .getPropertyPriority(
                "font-size"
              )
        });

        parent.style
          .setProperty(
            "font-size",
            `${base}px`,
            "important"
          );
      }

      parent =
        parent.parentElement;
    }

    return function restore() {
      changed.forEach(
        item => {
          if (
            item.value
          ) {
            item.el.style
              .setProperty(
                "font-size",
                item.value,
                item.priority
              );
          } else {
            item.el.style
              .removeProperty(
                "font-size"
              );
          }
        }
      );
    };
  }


  /* -------------------------------------------------
     註冊文字元素
  ------------------------------------------------- */

  function registerTargets(
    root
  ) {
    if (
      !root
    ) {
      return [];
    }

    const elementRoot =
      root.nodeType === 1
        ? root
        : root.parentElement;

    if (
      !elementRoot
    ) {
      return [];
    }

    /*
      如果目前已經是
      110% / 120%
      先暫時把祖先恢復基準
      避免新內容被重複放大
    */
    const restoreAncestors =
      temporarilyRestoreAncestorBases(
        elementRoot
      );

    const targets =
      getTargets(
        elementRoot
      );

    targets.forEach(
      rememberBase
    );

    restoreAncestors();

    return targets;
  }


  /* -------------------------------------------------
     對單一元素套用縮放
  ------------------------------------------------- */

  function applyToElement(
    el,
    scale
  ) {
    const base =
      Number(
        el.dataset
          .twTextBasePx
      );

    if (
      !Number.isFinite(
        base
      )
    ) {
      return;
    }

    /*
      100% 直接還原 CSS
    */
    if (
      scale === 1
    ) {
      restoreOriginal(
        el
      );

      return;
    }

    el.style
      .setProperty(
        "font-size",
        `${(
          base *
          scale
        ).toFixed(
          2
        )}px`,
        "important"
      );
  }


  /* -------------------------------------------------
     對一整個區域套用縮放
  ------------------------------------------------- */

  function applyToRoot(
    root,
    scale
  ) {
    const targets =
      registerTargets(
        root
      );

    targets.forEach(
      el => {
        applyToElement(
          el,
          scale
        );
      }
    );
  }


  /* -------------------------------------------------
     重新讀取目前 responsive CSS 的真實字級
  ------------------------------------------------- */

  function refreshBasesAt100() {
    if (
      !document.body
    ) {
      return;
    }

    const targets =
      getTargets(
        document.body
      );

    targets.forEach(
      el => {
        restoreOriginal(
          el
        );

        const px =
          parseFloat(
            getComputedStyle(
              el
            ).fontSize
          );

        if (
          Number.isFinite(
            px
          ) &&
          px > 0
        ) {
          el.dataset
            .twTextBasePx =
            String(
              px
            );
        }
      }
    );
  }


  /* -------------------------------------------------
     更新 Aa 選單顯示
  ------------------------------------------------- */

  function updateLabel(
    scale
  ) {
    const label =
      document.getElementById(
        "fontScaleValue"
      );

    if (
      label
    ) {
      label.textContent =
        `${
          Math.round(
            scale *
            100
          )
        }%`;
    }
  }


  /* -------------------------------------------------
     套用整站文字倍率
  ------------------------------------------------- */

  function applyScale(
    scale
  ) {
    const safeScale =
      LEVELS.includes(
        scale
      )
        ? scale
        : 1;

    /*
      在 100% 狀態下切換時
      重新抓目前裝置真正的 responsive 字級
    */
    if (
      currentScale === 1
    ) {
      refreshBasesAt100();
    }

    currentScale =
      safeScale;

    /*
      舊版 CSS variable 固定回 1
      避免又多縮放一次
    */
    document
      .documentElement
      .style
      .setProperty(
        "--user-font-scale",
        "1"
      );

    localStorage
      .setItem(
        STORAGE_KEY,
        String(
          safeScale
        )
      );

    applyToRoot(
      document.body,
      safeScale
    );

    updateLabel(
      safeScale
    );
  }


  /* -------------------------------------------------
     重新接管 Aa 的 +/- 按鈕
  ------------------------------------------------- */

  function bindControls() {
    const minus =
      document.querySelector(
        '[data-font-action="minus"]'
      );

    const plus =
      document.querySelector(
        '[data-font-action="plus"]'
      );

    if (
      minus
    ) {
      minus.onclick =
        e => {
          e.stopPropagation();

          const current =
            Number(
              localStorage
                .getItem(
                  STORAGE_KEY
                ) ||
              1
            );

          let index =
            LEVELS
              .indexOf(
                current
              );

          if (
            index < 0
          ) {
            index =
              1;
          }

          applyScale(
            LEVELS[
              Math.max(
                0,
                index - 1
              )
            ]
          );
        };
    }

    if (
      plus
    ) {
      plus.onclick =
        e => {
          e.stopPropagation();

          const current =
            Number(
              localStorage
                .getItem(
                  STORAGE_KEY
                ) ||
              1
            );

          let index =
            LEVELS
              .indexOf(
                current
              );

          if (
            index < 0
          ) {
            index =
              1;
          }

          applyScale(
            LEVELS[
              Math.min(
                LEVELS.length -
                1,
                index + 1
              )
            ]
          );
        };
    }
  }


  /* -------------------------------------------------
     監控動態新增內容
  ------------------------------------------------- */

  function observeDynamicContent() {
    if (
      observer ||
      !document.body
    ) {
      return;
    }

    observer =
      new MutationObserver(
        mutations => {
          mutations.forEach(
            mutation => {
              mutation
                .addedNodes
                .forEach(
                  node => {
                    if (
                      node.nodeType ===
                      1
                    ) {
                      applyToRoot(
                        node,
                        currentScale
                      );
                    }

                    if (
                      node.nodeType ===
                        Node.TEXT_NODE &&
                      node.parentElement
                    ) {
                      applyToRoot(
                        node.parentElement,
                        currentScale
                      );
                    }
                  }
                );
            }
          );
        }
      );

    observer.observe(
      document.body,
      {
        childList:
          true,

        subtree:
          true
      }
    );
  }


  /* -------------------------------------------------
     啟動
  ------------------------------------------------- */

  function boot() {
    injectResetStyle();

    /*
      舊版整頁倍率固定回 1
    */
    document
      .documentElement
      .style
      .setProperty(
        "--user-font-scale",
        "1"
      );

    currentScale =
      1;

    /*
      先記住目前所有
      100% 原始字體大小
    */
    refreshBasesAt100();

    /*
      接管 Aa 控制
    */
    bindControls();

    /*
      監控之後 AJAX / JS
      新增的內容
    */
    observeDynamicContent();

    /*
      套用之前使用者儲存的倍率
    */
    const saved =
      Number(
        localStorage
          .getItem(
            STORAGE_KEY
          ) ||
        1
      );

    applyScale(
      LEVELS.includes(
        saved
      )
        ? saved
        : 1
    );

    /*
      ui_v2.js 的 Aa 控制
      有可能稍晚才插入
      再補綁兩次
    */
    setTimeout(
      () => {
        bindControls();

        updateLabel(
          currentScale
        );

        applyToRoot(
          document.body,
          currentScale
        );
      },
      300
    );

    setTimeout(
      () => {
        bindControls();

        updateLabel(
          currentScale
        );

        applyToRoot(
          document.body,
          currentScale
        );
      },
      1200
    );
  }


  if (
    document.readyState ===
    "loading"
  ) {
    document.addEventListener(
      "DOMContentLoaded",
      boot
    );
  } else {
    boot();
  }

})();
