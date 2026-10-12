    async function loadBranches() {
      try {
        /*
         * 每次開啟個股都重新取得最新分點資料
         *
         * 不使用舊的 branchCache
         * 避免 GitHub 更新後仍顯示前一次的資料
         *
         * 時間戳記確保瀏覽器與 CDN
         * 不會直接回傳相同 URL 的舊快取
         */
        const url =
          './data/broker_branches/' +
          encodeURIComponent(ticker) +
          '.json?_=' +
          Date.now();

        const response = await fetch(url, {
          cache: 'no-store',
          signal: branchAbort.signal
        });

        if (!response.ok) {
          throw new Error(
            '尚未建立分點資料，請確認 Broker branch charts 已執行成功'
          );
        }

        const data = await response.json();

        if (token.dead || !host.isConnected) {
          return;
        }

        /*
         * 驗證股票代號、期間及資料格式
         */
        if (
          String(data.ticker) !== String(ticker) ||
          data.period !== 60 ||
          !Array.isArray(data.branches) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.start) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(data.date)
        ) {
          throw new Error(
            '分點資料格式或股票代號不符'
          );
        }

        /*
         * 驗證每個分點的每日交易明細
         *
         * 缺少資料的日期不補零
         * 避免把沒有來源資料誤判成零交易
         */
        const usable = data.branches.filter(b =>
          b.status === 'ok' &&
          Array.isArray(b.days) &&
          b.days.length > 0 &&
          b.days.every(d =>
            /^\d{4}-\d{2}-\d{2}$/.test(d.time) &&
            d.time >= data.start &&
            d.time <= data.date &&
            ['buy', 'sell', 'net'].every(
              k => Number.isFinite(d[k])
            )
          ) &&
          new Set(
            b.days.map(d => d.time)
          ).size === b.days.length
        );

        if (!usable.length) {
          throw new Error(
            '分點明細尚未取得，請查看 Broker branch charts 執行紀錄'
          );
        }

        /*
         * 使用這次實際取得的最新資料
         */
        branchData = data;

        branchSelect.replaceChildren();

        /*
         * 建立前五大買超、前五大賣超選單
         */
        for (
          const [side, label] of [
            ['buy', '近60日前五大買超'],
            ['sell', '近60日前五大賣超']
          ]
        ) {
          const group = document.createElement('optgroup');

          group.label = label;

          for (
            const b of data.branches.filter(
              b => b.side === side
            )
          ) {
            const option = document.createElement('option');

            option.value = b.id;

            option.disabled = !usable.includes(b);

            option.textContent =
              `${b.rank}. ${b.name}（` +
              `${b.net_lots > 0 ? '+' : ''}` +
              `${fmt(b.net_lots, 0)}張）` +
              (
                option.disabled
                  ? '－明細待補'
                  : ''
              );

            group.append(option);
          }

          branchSelect.append(group);
        }

        branchSelect.disabled = false;

        /*
         * 預設選擇第一個有完整明細的分點
         */
        branchSelect.value = usable[0].id;

        /*
         * 更新圖表及分點日期
         */
        chooseBranch();

      } catch (e) {
        if (
          token.dead ||
          e.name === 'AbortError'
        ) {
          return;
        }

        branchSelect.disabled = true;

        branchSelect.replaceChildren();

        const option = document.createElement('option');

        option.textContent = '分點資料暫不可用';

        branchSelect.append(option);

        branchStatus.textContent = e.message;

        fitCanvas();
      }
    }

    loadBranches();
