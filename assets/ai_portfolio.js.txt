/* Forward portfolio presentation. All returns come from the persisted ledger. */
(() => {
  'use strict';
  let data = null, tab = 'holdings', request = 0;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => Number(n || 0).toLocaleString('zh-TW', {maximumFractionDigits:0});
  const pct = n => `${Number(n || 0) > 0 ? '+' : ''}${Number(n || 0).toFixed(2)}%`;
  const tone = n => Number(n)>0 ? 'ap-up' : Number(n)<0 ? 'ap-down' : '';
  const company = x => `<div class="ap-company"><strong>${esc(x.name)}</strong><span>${esc(x.ticker)}</span><span data-stock-nav-code="${esc(x.ticker)}" data-stock-nav-name="${esc(x.name)}"></span></div>`;
  function chart(rows) {
    if (!rows.length) return '<p class="ap-note">首個模擬交易日收盤後開始累積淨值，不倒填舊策略績效。</p>';
    const values=rows.map(r=>r.equity), min=Math.min(...values)*.998,max=Math.max(...values)*1.002;
    const points=values.map((v,i)=>`${20+i*660/Math.max(1,values.length-1)},${180-(v-min)*150/(max-min)}`).join(' ');
    return `<svg class="ap-chart" viewBox="0 0 700 225" role="img" aria-label="${esc(rows[0].date)} 至 ${esc(rows.at(-1).date)} 的持倉淨值，共 ${rows.length} 個資料日"><line x1="20" x2="680" y1="180" y2="180" stroke="currentColor" opacity=".15"/><polyline points="${points}" fill="none" stroke="#4976e9" stroke-width="3"/><text x="20" y="215" fill="currentColor" font-size="12">${esc(rows[0].date)}</text><text x="680" y="215" text-anchor="end" fill="currentColor" font-size="12">${esc(rows.at(-1).date)}</text></svg>`;
  }
  function evidence(x) {
    return `<details class="ap-evidence"><summary>入選依據與風險</summary><ul>${(x.evidence||x.entry_reason||[]).map(s=>`<li>${esc(s)}</li>`).join('')}</ul>${(x.risks||[]).length?`<p>需留意</p><ul>${x.risks.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:''}${x.etf_details?.length?`<p>ETF持股變動：${x.etf_details.map(v=>`${esc(v.fund)} ${money(v.shares_delta/1000)}張`).join('、')}</p>`:''}</details>`;
  }
  function render() {
    const root=document.getElementById('aiPortfolioRoot'); if(!root||!data)return;
    const positions=Object.values(data.positions||{}), decisions=data.decisions||[], decision=decisions.at(-1);
    const targets=decision?.targets||[], targetIds=new Set(targets.map(x=>x.ticker)), held=new Set(positions.map(x=>x.ticker));
    const rows=data.equity||[], last=rows.at(-1), initial=data.config.initial_cash;
    const equity=last?.equity??initial, net=equity-initial, sells=(data.trades||[]).filter(x=>x.side==='sell');
    const drawdown=Math.min(0,...rows.map(r=>r.drawdown_pct));
    const errors=data.latest_attempt?.errors||[];
    let content='';
    if(tab==='holdings') content=positions.length?positions.map(x=>{const value=x.mark*x.shares,pnl=value-x.cost;return `<article class="ap-stock">${company(x)}<div class="ap-row"><span class="ap-state">${decision&&!targetIds.has(x.ticker)?'待賣出':'持有中'}</span><strong class="${tone(pnl)}">${pct(pnl/x.cost*100)}</strong></div><div class="ap-meta"><span>${money(x.shares)} 股 · ${esc(x.entry_date)} 買入</span><span>市值 $${money(value)}</span><span>含買入費成本 $${(x.cost/x.shares).toFixed(2)}/股</span><span>未實現 ${pnl>=0?'+':''}$${money(pnl)}</span></div>${x.mark_date!==last?.date?'<p class="ap-note">收盤標記未更新，沿用前次價格</p>':''}${evidence(x)}</article>`;}).join(''):'<div class="ap-empty">目前持有現金。正式入選名單公布後，在其後第一個可驗證交易日開盤模擬買進。</div>';
    if(tab==='targets') content=`<p class="ap-note">正式名單 ${esc(decision?.date||'尚未產生')} · 公布 ${esc(decision?.available_at||'—')}<br>名單最多${data.config.max_positions}檔。續留不重買；移出於下一開盤賣出。觀察清單不下單。</p>${targets.map(x=>`<article class="ap-stock">${company(x)}<div class="ap-row"><span class="ap-state">${held.has(x.ticker)?'續抱':'待買入'}</span><strong>${x.score.toFixed(1)} 分</strong></div><div class="ap-pillars">${[['chip','籌碼'],['fundamental','基本面'],['momentum','動能']].map(([k,l])=>`<span>${l} <b>${x.pillars[k].toFixed(0)}</b></span>`).join('')}</div>${evidence(x)}</article>`).join('')}${decision&&!targets.length?'<p class="ap-note">完整資料下無股票達標，下個可成交開盤退出全部持倉。</p>':''}${positions.filter(x=>decision&&!targetIds.has(x.ticker)).map(x=>`<article class="ap-stock">${company(x)}<p class="ap-down">待賣出 · 移出正式名單</p></article>`).join('')}<details class="ap-evidence"><summary>未入選觀察名單（不交易）</summary>${(decision?.candidates||data.latest_attempt?.candidates||[]).filter(x=>!targetIds.has(x.ticker)).slice(0,10).map(x=>`<article class="ap-stock">${company(x)}<p>${x.score.toFixed(1)} 分 · 未達門檻或名額已滿</p>${evidence(x)}</article>`).join('')}</details>`;
    if(tab==='trades') content=(data.trades||[]).length?`<div class="ap-scroll"><table><thead><tr><th>成交日／決策日</th><th>股票</th><th>買賣／股數</th><th>價格／費稅</th><th>已實現損益</th></tr></thead><tbody>${[...data.trades].reverse().slice(0,200).map(x=>`<tr><td>${esc(x.date)}<small>${esc(x.decision_date)}</small></td><td>${esc(x.name)}<small>${esc(x.ticker)}</small></td><td>${x.side==='buy'?'買進':'賣出'} ${money(x.shares)}股</td><td>${x.price.toFixed(2)}<small>費稅 $${money(x.commission+x.tax)}</small></td><td class="${tone(x.realized_pnl)}">${x.side==='sell'?money(x.realized_pnl):'—'}</td></tr>`).join('')}</tbody></table></div><p class="ap-note">顯示最近200筆，完整交易仍保存在帳本。</p>`:'<p class="ap-empty">尚無已成交交易，不把待買名單算成持倉。</p>';
    if(tab==='equity') content=`${chart(rows)}<div class="ap-scroll"><table><thead><tr><th>日期</th><th>淨值</th><th>累積報酬</th><th>回撤</th></tr></thead><tbody>${[...rows].reverse().slice(0,90).map(r=>`<tr><td>${esc(r.date)}${r.stale_marks?.length?'<small>含沿用價格</small>':''}</td><td>${money(r.equity)}</td><td class="${tone(r.return_pct)}">${pct(r.return_pct)}</td><td>${pct(r.drawdown_pct)}</td></tr>`).join('')}</tbody></table></div>`;
    root.innerHTML=`<div class="ap-topline"><span>開始 ${esc(data.started_at?.slice(0,10))} · 收盤後更新</span><button type="button" data-ap-refresh>重新載入</button></div>${errors.length?`<div role="status" class="ap-warning">暫停新決策，保留已公布名單與持倉：${errors.map(esc).join('；')}</div>`:''}<div class="ap-summary"><div><small>組合淨值</small><strong>$${money(equity)}</strong><span class="${tone(net)}">${pct(net/initial*100)} · ${net>=0?'+':''}$${money(net)}</span></div><div><small>持倉／現金</small><strong>${positions.length} 檔</strong><span>$${money(data.cash)} 現金</span></div></div><div class="ap-stats"><span>已實現 <b>${money(sells.reduce((s,x)=>s+x.realized_pnl,0))}</b></span><span>最大回撤 <b>${pct(drawdown)}</b></span><span>已平倉 <b>${sells.length} 筆</b></span></div><div class="ap-tabs" role="tablist" aria-label="模擬投資組合">${[['holdings','持倉'],['targets','下次名單'],['trades','交易紀錄'],['equity','每日淨值']].map(([k,v])=>`<button type="button" role="tab" aria-selected="${tab===k}" tabindex="${tab===k?'0':'-1'}" data-ap-tab="${k}" class="${tab===k?'active':''}">${v}</button>`).join('')}</div><div role="tabpanel" class="ap-content">${content}</div>${data.execution_warnings?.length?`<details class="ap-evidence"><summary>未成交／資料提醒（${data.execution_warnings.length}）</summary>${data.execution_warnings.slice(-20).reverse().map(x=>`<p>${esc(x.date)} ${esc(x.ticker)} ${x.side==='buy'?'買入':x.side==='sell'?'賣出':'估值'}：${esc(x.reason)}</p>`).join('')}</details>`:''}<details class="ap-rules"><summary>選股與交易規則</summary><p>籌碼40%／基本面40%／動能20%。既有AI研究資料搭配固定規則選股，分數不是上漲機率。</p><p>初始 $${money(initial)}，最多${data.config.max_positions}檔，新買約占資產${data.config.entry_weight*100}%。繼續入選保留原股數。缺資料不觸發清倉；完整資料下空名單才退出。</p><p>決策公布後的下一個開盤才可成交。手續費每邊${data.config.commission_rate*100}%（最低$${data.config.minimum_commission}）、賣出稅${data.config.sell_tax*100}%、單邊滑價${data.config.slippage*100}%，均列入帳本。</p>${data.limitations.map(x=>`<p>${esc(x)}</p>`).join('')}</details><p class="ap-note">帳本更新 ${esc(data.updated_at)} · 累積${rows.length}個交易日，尚未驗證策略有效性。</p>`;
    root.querySelectorAll('[data-ap-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.apTab;render();root.querySelector(`[data-ap-tab="${tab}"]`)?.focus({preventScroll:true});});
    root.querySelector('.ap-tabs').onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const keys=['holdings','targets','trades','equity'];let i=keys.indexOf(tab);i=e.key==='Home'?0:e.key==='End'?3:(i+(e.key==='ArrowRight'?1:3))%4;tab=keys[i];render();root.querySelector(`[data-ap-tab="${tab}"]`).focus();};
    root.querySelector('[data-ap-refresh]').onclick=()=>window.renderAiPortfolio(true);
  }
  window.renderAiPortfolio=async () => {
    const root=document.getElementById('aiPortfolioRoot');if(!root)return;
    const id=++request;
    if(!data)root.innerHTML='<p role="status">正在載入模擬投資組合…</p>';
    try {
      const response=await fetch('./data/ai_portfolio.json?v='+Date.now(),{cache:'no-store'});
      if(!response.ok)throw Error('portfolio not ready');
      const next=await response.json();if(next.schema!==1||!next.config||!Array.isArray(next.decisions))throw Error('invalid portfolio');
      if(id!==request)return;data=next;render();
    } catch(e) {
      if(id!==request)return;
      if(data){render();const p=document.createElement('p');p.className='ap-warning';p.textContent='載入失敗，目前顯示上次成功的帳本。';root.prepend(p);}
      else root.innerHTML='<div class="ap-empty">模擬帳本尚未建立。上傳程式後執行 Daily close update，首次只建立名單，之後才累積交易與績效。</div>';
    }
  };
})();
