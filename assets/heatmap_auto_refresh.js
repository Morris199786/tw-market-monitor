  /* =========================================================
     Squarified Treemap
     - 面積嚴格依成交金額
     - 使用實際手機容器寬高計算
     - 避免細長直條
     - 填滿整個 Treemap
     ========================================================= */

  function sumValues(items) {
    return items.reduce(
      (sum, item) =>
        sum +
        Math.max(
          0,
          Number(item.value || 0)
        ),
      0
    );
  }


  /*
   * 計算目前一列最差的長寬比
   */

  function worstRatio(
    row,
    side
  ) {
    if (
      !row.length ||
      side <= 0
    ) {
      return Infinity;
    }

    const areas =
      row
        .map(
          item =>
            Math.max(
              0,
              item._area || 0
            )
        )
        .filter(
          value =>
            value > 0
        );

    if (!areas.length) {
      return Infinity;
    }

    const sum =
      areas.reduce(
        (a, b) =>
          a + b,
        0
      );

    const max =
      Math.max(
        ...areas
      );

    const min =
      Math.min(
        ...areas
      );

    if (
      sum <= 0 ||
      min <= 0
    ) {
      return Infinity;
    }

    const sideSquared =
      side * side;

    const sumSquared =
      sum * sum;

    return Math.max(
      (
        sideSquared *
        max
      ) /
        sumSquared,

      sumSquared /
        (
          sideSquared *
          min
        )
    );
  }


  /*
   * 把一列真正放進剩餘矩形
   */

  function placeRow(
    row,
    rect,
    output
  ) {
    if (!row.length) {
      return rect;
    }

    const rowArea =
      row.reduce(
        (
          sum,
          item
        ) =>
          sum +
          item._area,
        0
      );

    if (
      rowArea <= 0 ||
      rect.w <= 0 ||
      rect.h <= 0
    ) {
      return rect;
    }


    /*
     * 剩餘區域比較寬
     *
     * → 左邊切一個直欄
     *
     * 但欄內的方塊會依 squarify
     * 自動控制比例
     */

    if (
      rect.w >=
      rect.h
    ) {
      const stripWidth =
        rowArea /
        rect.h;

      let currentY =
        rect.y;

      row.forEach(
        (
          item,
          index
        ) => {
          let height;

          if (
            index ===
            row.length - 1
          ) {
            height =
              (
                rect.y +
                rect.h
              ) -
              currentY;
          } else {
            height =
              item._area /
              stripWidth;
          }

          output.push({
            ...item,

            xPx:
              rect.x,

            yPx:
              currentY,

            wPx:
              stripWidth,

            hPx:
              Math.max(
                0,
                height
              )
          });

          currentY +=
            height;
        }
      );


      return {
        x:
          rect.x +
          stripWidth,

        y:
          rect.y,

        w:
          Math.max(
            0,
            rect.w -
              stripWidth
          ),

        h:
          rect.h
      };
    }


    /*
     * 剩餘區域比較高
     *
     * → 上方切一個橫列
     */

    const stripHeight =
      rowArea /
      rect.w;

    let currentX =
      rect.x;

    row.forEach(
      (
        item,
        index
      ) => {
        let width;

        if (
          index ===
          row.length - 1
        ) {
          width =
            (
              rect.x +
              rect.w
            ) -
            currentX;
        } else {
          width =
            item._area /
            stripHeight;
        }

        output.push({
          ...item,

          xPx:
            currentX,

          yPx:
            rect.y,

          wPx:
            Math.max(
              0,
              width
            ),

          hPx:
            stripHeight
        });

        currentX +=
          width;
      }
    );


    return {
      x:
        rect.x,

      y:
        rect.y +
        stripHeight,

      w:
        rect.w,

      h:
        Math.max(
          0,
          rect.h -
            stripHeight
        )
    };
  }


  /*
   * 真正的 Squarified Treemap
   *
   * 注意：
   * 這裡不能再用 100 x 100
   *
   * 因為手機實際可能是
   * 350 x 780
   *
   * 若拿正方形去算，
   * 最後就會變成你剛才看到的
   * 一堆超細直條
   */

  function treemapLayout(
    items,
    pixelWidth,
    pixelHeight
  ) {
    const sorted =
      items
        .filter(
          item =>
            Number(
              item.value || 0
            ) > 0
        )
        .sort(
          (
            a,
            b
          ) =>
            Number(
              b.value || 0
            ) -
            Number(
              a.value || 0
            )
        );


    if (
      !sorted.length ||
      pixelWidth <= 0 ||
      pixelHeight <= 0
    ) {
      return [];
    }


    const total =
      sumValues(
        sorted
      );


    if (
      total <= 0
    ) {
      return [];
    }


    const totalArea =
      pixelWidth *
      pixelHeight;


    /*
     * 成交金額轉成實際 pixel 面積
     */

    const work =
      sorted.map(
        item => ({
          ...item,

          _area:
            (
              Number(
                item.value || 0
              ) /
              total
            ) *
            totalArea
        })
      );


    let remaining = {
      x: 0,
      y: 0,

      w:
        pixelWidth,

      h:
        pixelHeight
    };


    let row = [];

    const output =
      [];

    let index =
      0;


    while (
      index <
      work.length
    ) {
      const item =
        work[index];


      /*
       * Squarify 使用目前剩餘區域
       * 的短邊判斷長寬比
       */

      const side =
        Math.min(
          remaining.w,
          remaining.h
        );


      if (!row.length) {
        row.push(
          item
        );

        index += 1;

        continue;
      }


      const currentWorst =
        worstRatio(
          row,
          side
        );


      const nextWorst =
        worstRatio(
          [
            ...row,
            item
          ],
          side
        );


      /*
       * 加進去後比例更漂亮
       *
       * → 繼續放同一列
       */

      if (
        nextWorst <=
        currentWorst
      ) {
        row.push(
          item
        );

        index += 1;
      } else {

        /*
         * 再加就會變醜
         *
         * → 把目前這列固定
         */

        remaining =
          placeRow(
            row,
            remaining,
            output
          );

        row = [];
      }
    }


    /*
     * 最後一列
     */

    if (
      row.length
    ) {
      remaining =
        placeRow(
          row,
          remaining,
          output
        );
    }


    /*
     * pixel → %
     *
     * HTML 還是使用百分比定位，
     * 因此手機旋轉／不同寬度仍能正常顯示
     */

    return output.map(
      item => ({
        ...item,

        x:
          (
            item.xPx /
            pixelWidth
          ) *
          100,

        y:
          (
            item.yPx /
            pixelHeight
          ) *
          100,

        width:
          (
            item.wPx /
            pixelWidth
          ) *
          100,

        height:
          (
            item.hPx /
            pixelHeight
          ) *
          100
      })
    );
  }
