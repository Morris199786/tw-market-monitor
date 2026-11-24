/* Forward portfolio presentation. All returns come from the persisted ledger. */
(() => {
  'use strict';
  let data = null, marketData = null, tab = null, request = 0;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => Number(n || 0).toLocaleString('zh-TW', {maximumFractionDigits:0});
  const pct = n => `${Number(n || 0) > 0 ? '+' : ''}${Number(n || 0).toFixed(2)}%`;
  const tone = n => Number(n)>0 ? 'ap-up' : Number(n)<0 ? 'ap-down' : '';
  const dateLabel = value => { if(!value)return '—'; const d=new Date(value); return Number.isNaN(d.valueOf())?String(value):new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d); };
  const company = x => `<div class="ap-company"><strong>${esc(x.name)}</strong><span>${esc(x.ticker)}${x.asset_type==='etf'?' · ETF':''}</span><span data-stock-nav-code="${esc(x.ticker)}" data-stock-nav-name="${esc(x.name)}"></span></div>`;
  function benchmark(rows, raw) {
    if (!rows.length) return {start:null, values:new Map()};
    const valid=(raw||[]).filter(r=>typeof r.index==='number'&&Number.isFinite(r.index)&&r.index>0).sort((a,b)=>a.date.localeCompare(b.date));
    const start=valid.filter(r=>r.date<rows[0].date).at(-1);
    const prices=new Map(valid.map(r=>[r.date,r.index]));
    return {start:start?.date||null, values:new Map(rows.map(r=>{
      const price=prices.get(r.date);
      const value=start&&price!==undefined?(price/start.index-1)*100:null;
      return [r.date,value];
    }))};
  }
  const comparisonPct = n => n===null||n===undefined?'待補':pct(n);
  function chart(rows) {
    if (!rows.length) return '<p class="ap-note">首個模擬交易日收盤後開始累積淨值，不倒填舊策略績效。</p>';
    const values=rows.map(r=>r.equity), min=Math.min(...values)*.998,max=Math.max(...values)*1.002;
    const points=values.map((v,i)=>`${20+i*660/Math.max(1,values.length-1)},${180-(v-min)*150/(max-min)}`).join(' ');
    return `<svg class="ap-chart" viewBox="0 0 700 225" role="img" aria-label="${esc(rows[0].date)} 至 ${esc(rows.at(-1).date)} 的持倉淨值，共 ${rows.length} 個資料日"><line x1="20" x2="680" y1="180" y2="180" stroke="currentColor" opacity=".15"/><polyline points="${points}" fill="none" stroke="#4976e9" stroke-width="3"/><text x="20" y="215" fill="currentColor" font-size="12">${esc(rows[0].date)}</text><text x="680" y="215" text-anchor="end" fill="currentColor" font-size="12">${esc(rows.at(-1).date)}</text></svg>`;
  }
  function evidence(x) {
    return `<details class="ap-evidence"><summary>查看評分依據與風險</summary><ul>${(x.evidence||x.entry_reason||[]).map(s=>`<li>${esc(s)}</li>`).join('')}</ul>${(x.risks||[]).length?`<p>需留意</p><ul>${x.risks.map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:''}${x.etf_details?.length?`<p>ETF持股變動：${x.etf_details.map(v=>`${esc(v.fund)} ${money(v.shares_delta/1000)}張`).join('、')}</p>`:''}</details>`;
  }
  function holdingsTable(positions, decision, equity, date) {
    const prices = new Intl.NumberFormat('zh-TW', {minimumFractionDigits:2, maximumFractionDigits:2});
    const lots = new Intl.NumberFormat('zh-TW', {maximumFractionDigits:3});
    const targets = new Map((decision?.targets || []).map(x => [x.ticker, x.weight]));
    const holdings = positions.map(x => {
      const shares = Number.isFinite(x.shares) && x.shares > 0 ? x.shares : null;
      const mark = Number.isFinite(x.mark) && x.mark > 0 ? x.mark : null;
      const value = shares !== null && mark !== null ? shares * mark : null;
      return {x, shares, mark, value};
    });
    const total = holdings.every(h => h.value !== null)
      ? holdings.reduce((sum, h) => sum + h.value, 0) : null;
    holdings.sort((a, b) => (b.value ?? -1) - (a.value ?? -1));
    const rows = holdings.map(({x, shares, mark, value}, i) => {
      const weight = value !== null && equity > 0 ? (100 * value / equity).toFixed(2) + '%' : '—';
      const cost = Number.isFinite(x.cost) && x.cost >= 0 ? x.cost : null;
      const pnl = value !== null && cost !== null ? value - cost : null;
      const stale = mark !== null && (!x.mark_date || x.mark_date !== date);
      const id = 'ap-position-' + i;
      const status = decision && !targets.has(x.ticker) ? '計畫賣出' : '持有中';
      return `<tr class="ap-position-row">
        <th scope="row"><button type="button" class="ap-position-toggle" aria-expanded="false" aria-controls="${id}" aria-label="${esc(x.name)}持倉明細">
          <b>${esc(x.name)}</b><small>${esc(x.ticker)} <i aria-hidden="true"></i></small>
        </button>${status==='計畫賣出'?'<small class="ap-pending-sale">計畫賣出</small>':''}</th>
        <td>${mark===null?'—':prices.format(mark)}${stale?'<small>前次收盤</small>':''}</td>
        <td>${cost!==null && shares!==null?prices.format(cost/shares):'—'}</td>
        <td>${shares!==null?lots.format(shares/1000):'—'}</td>
        <td>${weight}</td>
        <td class="${tone(pnl)}"><b>${pnl===null?'—':(pnl>0?'+':'')+money(pnl)}</b><small>${pnl!==null && cost>0?pct(pnl/cost*100):'—'}</small></td>
      </tr><tr id="${id}" class="ap-position-detail" hidden><td colspan="6">
        ${company(x)}
        <div class="ap-meta"><span>${status} · ${shares===null?'—':money(shares)} 股</span><span>買入日 ${esc(x.entry_date||'—')}</span>
        <span>收盤日 ${esc(x.mark_date||'—')}</span>
        <span>佔帳戶淨值 ${value!==null && equity>0?(value/equity*100).toFixed(1)+'%':'—'}</span>
        <span>目標帳戶權重 ${decision?((targets.get(x.ticker)??0)*100).toFixed(1)+'%':'待確認'}</span></div>
        ${evidence(x)}</td></tr>`;
    }).join('');
    return `<section class="ap-inventory"><p>收盤市價 · 均價含買入費 · 損益以新台幣計 · 持股占比以帳戶淨值（含現金）計算${total === null ? '（持倉估值未齊）' : ''}</p>
      <div class="ap-inventory-scroll"><table aria-label="實際持倉庫存表"><thead><tr><th scope="col">股票</th><th scope="col">市價</th>
      <th scope="col">均價</th><th scope="col">張數</th><th scope="col" aria-sort="descending">帳戶占比 ↓</th><th scope="col">未實現損益</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
  }

  function render() {
    const root=document.getElementById('aiPortfolioRoot'); if(!root||!data)return;
    const positions=Object.values(data.positions||{}), decisions=data.decisions||[], lastDecision=decisions.at(-1), decision=data.latest_attempt?.valid===false?null:lastDecision;
    if (!tab) tab=positions.length?'holdings':'targets';
    const targets=decision?.targets||[], targetIds=new Set(targets.map(x=>x.ticker)), held=new Set(positions.map(x=>x.ticker));
    const rows=data.equity||[], last=rows.at(-1), initial=data.config.initial_cash;
    const equity=last?.equity??initial, net=equity-initial, sells=(data.trades||[]).filter(x=>x.side==='sell');
    const comparison=benchmark(rows,marketData?.raw), marketReturn=comparison.values.get(last?.date)??null;
    const excess=marketReturn===null?null:last.return_pct-marketReturn;
    const benchmarkPanel=`<div class="ap-stats"><span>組合累積報酬<b class="${tone(last?.return_pct)}">${rows.length?pct(last.return_pct):'尚未開始'}</b></span><span>同期加權指數<b class="${tone(marketReturn)}">${comparisonPct(marketReturn)}</b></span><span>超額報酬<b class="${tone(excess)}">${excess===null?'待補':pct(excess).replace('%',' 個百分點')}</b></span></div><p class="ap-note">比較期間：${esc(comparison.start||'基準日待補')} 收盤 → ${esc(last?.date||'尚無淨值')} 收盤。組合含現金、費稅與滑價；大盤為價格指數報酬。超額＝組合報酬－同期大盤報酬。</p>`;
    const drawdown=Math.min(0,...rows.map(r=>r.drawdown_pct));
    const errors=data.latest_attempt?.errors||[], warnings=data.latest_attempt?.warnings||[];
    let content='';
    if(tab==='holdings') content=positions.length?holdingsTable(positions, decision, equity, last?.date):'<div class="ap-empty">目前持有現金。正式入選名單公布後，在其後第一個可驗證交易日開盤模擬買進。</div>';
    if(tab==='targets') content=`<div class="ap-section-heading"><div><h2>預計持有標的 <span>${targets.length}</span></h2><p>以下為最新決策的目標配置，非已成交部位</p></div><span class="ap-caption">下一交易日嘗試執行</span></div><div class="ap-cards">${targets.map((x,i)=>`<article class="ap-stock ap-target"><div class="ap-card-top"><span class="ap-rank">${String(i+1).padStart(2,'0')}</span><span class="ap-state">${held.has(x.ticker)?'續抱／調整':'計畫買入'}</span><span class="ap-score"><b>${x.score.toFixed(1)}</b><small>綜合評分</small></span></div>${company(x)}<div class="ap-allocation"><div><small>目標帳戶權重</small><strong>${((x.weight||0)*100).toFixed(2)}<em>%</em></strong></div><div><small>目標投入金額</small><span>$${money(equity*(x.weight||0))}</span></div></div><div class="ap-pillars">${[['chip','籌碼'],['fundamental','基本面'],['momentum','動能']].map(([k,l])=>`<div><span>${l}<b>${x.pillars[k].toFixed(0)}</b></span><i><i style="width:${Math.max(0,Math.min(100,x.pillars[k]))}%"></i></i></div>`).join('')}</div><details class="ap-evidence ap-allocation-detail"><summary>配置依據${Number(x.self_report_bonus)?` · 自結 ${Number(x.self_report_bonus)>0?'+':''}${Number(x.self_report_bonus).toFixed(2)}分`:''}</summary><p>${esc(x.confidence||'')} · ${esc(x.allocation_reason||'依綜合評分與單檔／產業上限配置')}</p></details>${evidence(x)}</article>`).join('')}</div>${positions.filter(x=>decision&&!targetIds.has(x.ticker)).length?`<div class="ap-plan-heading"><strong>計畫賣出</strong><span>${positions.filter(x=>!targetIds.has(x.ticker)).length} 檔 · 下一可成交交易日嘗試執行</span></div><div class="ap-sell-grid">${positions.filter(x=>!targetIds.has(x.ticker)).map(x=>`<article class="ap-sell-item">${company(x)}<span>目標帳戶權重 0%${decision.regime?.target_exposure===0?' · 大盤風控減倉':' · 配置調整'}</span></article>`).join('')}</div>`:''}<details class="ap-evidence ap-observe"><summary>未入選觀察名單 · 不交易</summary>${(decision?.candidates||[]).filter(x=>!targetIds.has(x.ticker)).slice(0,10).map(x=>`<article class="ap-stock">${company(x)}<p>${x.score.toFixed(1)} 分 · ${x.research_pending?'研究待核對，本次排除':'未達門檻或配置限制'}</p>${evidence(x)}</article>`).join('')}</details>`;
    if(tab==='targets'&&!targets.length) content+=decision?.regime?.target_exposure===0?'<div class="ap-plan-notice"><strong>目前採取全現金防禦配置</strong><p>風控模型目標持股 0%。此為有效配置決策，並非選股失敗；風控決策仍須依開盤減碼門檻與成交條件執行。</p></div>':decision?'<div class="ap-plan-notice"><strong>本次沒有配置買入標的</strong><p>可投資標的或配置條件不足，請查看大盤配置依據。</p></div>':'<div class="ap-empty">本次資料尚未通過檢查，沒有新的正式配置計畫；既有部位不會因資料缺漏自動清倉。</div>';
    if(tab==='trades') content=(data.trades||[]).length?`<div class="ap-scroll"><table><thead><tr><th>成交日／決策日</th><th>股票</th><th>買賣／股數</th><th>價格／費稅</th><th>已實現損益</th></tr></thead><tbody>${[...data.trades].reverse().slice(0,200).map(x=>`<tr><td>${esc(x.date)}<small>${esc(x.decision_date)}</small></td><td>${esc(x.name)}<small>${esc(x.ticker)}</small></td><td>${x.side==='buy'?'買進':'賣出'} ${money(x.shares)}股</td><td>${x.price.toFixed(2)}<small>費稅 $${money(x.commission+x.tax)}</small></td><td class="${tone(x.realized_pnl)}">${x.side==='sell'?money(x.realized_pnl):'—'}</td></tr>`).join('')}</tbody></table></div><p class="ap-note">顯示最近200筆，完整交易仍保存在帳本。</p>`:'<p class="ap-empty">尚無已成交交易，不把待買名單算成持倉。</p>';
    if(tab==='equity') content=`${chart(rows)}<div class="ap-scroll"><table><thead><tr><th>日期</th><th>淨值</th><th>累積報酬</th><th>同期大盤</th><th>超額（百分點）</th><th>回撤</th></tr></thead><tbody>${[...rows].reverse().slice(0,90).map(r=>`<tr><td>${esc(r.date)}${r.stale_marks?.length?'<small>含沿用價格</small>':''}</td><td>${money(r.equity)}</td><td class="${tone(r.return_pct)}">${pct(r.return_pct)}</td><td>${comparisonPct(comparison.values.get(r.date))}</td><td>${comparison.values.get(r.date)==null?'待補':(r.return_pct-comparison.values.get(r.date)).toFixed(2)}</td><td>${pct(r.drawdown_pct)}</td></tr>`).join('')}</tbody></table></div>`;
    const cashRatio=Math.max(0,Math.min(1,data.cash/equity)), exposure=decision?.target_exposure||0;
    const modelReady=decision?.model?.startsWith('relative-content-v6');
    const currentExposure=Math.max(0,Math.min(1,1-cashRatio));
    const validTarget=Boolean(decision?.regime?.valid);
    const targetExposure=validTarget?Math.max(0,Math.min(1,Number(decision?.regime?.target_exposure??0))):null;
    const delta=targetExposure===null?null:(targetExposure-currentExposure)*100;
    const deltaLabel=delta===null?'資料待確認':Math.abs(delta)<0.05?'維持水位':`${delta>0?'預計增加':'預計減少'} ${Math.abs(delta).toFixed(1)} 個百分點`;
    const riskScore=Number(decision?.regime?.risk_score);
    const hasV12=validTarget&&Number.isFinite(riskScore)&&Number.isInteger(decision?.regime?.risk_level);
    const lightTone=hasV12?['green','yellow','orange','red'][decision.regime.risk_level]:'neutral';
    const regime=decision?.regime||{};
    const t6=regime.exposure_model==='H2+T6';
    const k20=regime.sox_model==='K20';
    const soxReady=k20&&regime.sox_status==='ready';
    const pp=v=>Number.isFinite(v)?`${v>0?'+':''}${(v*100).toFixed(1)}pp`:'—';
    const band=t6?(delta>=0?regime.exposure_up_band:regime.exposure_down_band)*100:null;
    const withinBand=t6&&delta!==null&&Math.abs(delta)<band;
    const trialTag=t6&&regime.trial_today===true?'<span class="ap-risk-chip ap-trial-chip">試單機會</span>':'';
    const pendingSales=validTarget?positions.filter(x=>!targetIds.has(x.ticker)).length:0;
    const lastExecution=(data.exposure_execution||[]).at(-1);
    root.innerHTML=`<div class="ap-toolbar"><div role="status" class="ap-status ${decision?'':'ap-status-pending'}"><i></i>${decision?'配置計畫已更新':'本次配置待確認'}<span>${esc(dateLabel(data.latest_attempt?.available_at||data.updated_at))}</span></div><button type="button" data-ap-refresh aria-label="重新載入最新帳本">↻ 重新載入</button></div>${errors.length?`<div role="status" class="ap-warning">本次未發布新名單，暫停新調倉：${errors.map(esc).join('；')}</div>`:''}
    <div class="ap-balance ap-balance-main"><div class="ap-balance-label">投資組合淨值 <span>TWD</span></div><strong>$${money(equity)}</strong><span class="ap-return ${tone(net)}">${pct(net/initial*100)} <small>累積損益 · ${net>=0?'+':''}$${money(net)}</small></span><div class="ap-balance-foot"><span>初始本金 $${money(initial)}</span><span>持有 ${positions.length} 檔 · 現金 $${money(data.cash)}</span></div></div>
    <div class="ap-stats ap-head-stats"><span>已實現損益<b class="${tone(sells.reduce((v,x)=>v+x.realized_pnl,0))}">$${money(sells.reduce((v,x)=>v+x.realized_pnl,0))}</b></span><span>最大回撤<b>${pct(drawdown)}</b></span><span>已賣出<b>${sells.length} 筆</b></span></div>
    <section class="ap-waterfall" aria-label="大盤風控與持股水位"><div class="ap-waterfall-heading"><div><h2>大盤風控與持股水位</h2><p>最新風控決策 ${esc(decision?.regime?.date||'資料待補')} · 實際持倉截至 ${esc(last?.date||'尚無紀錄')}</p></div><div class="ap-risk-tags">${hasV12?`<span class="ap-risk-chip ap-risk-${lightTone}">${esc(decision.regime.risk_light||'風險警示')} · ${riskScore.toFixed(1)} 分</span>`:'<span class="ap-risk-chip">風險待確認</span>'}${trialTag}</div></div>
      <div class="ap-waterfall-figures"><div><span>目前持股水位</span><strong>${(currentExposure*100).toFixed(1)}<small>%</small></strong></div><div><span>下個交易日目標水位</span><strong>${targetExposure===null?'—':(targetExposure*100).toFixed(1)}${targetExposure===null?'':'<small>%</small>'}</strong></div></div>
      <div class="ap-waterfall-bars"><div class="ap-meter-label"><span>目前持股水位</span><b>${(currentExposure*100).toFixed(1)}%</b></div><div class="ap-meter"><i style="width:${(currentExposure*100).toFixed(2)}%"></i></div><div class="ap-meter-label"><span>下個交易日目標水位</span><b>${targetExposure===null?'—':(targetExposure*100).toFixed(1)+'%'}</b></div><div class="ap-meter ap-meter-target"><i style="width:${targetExposure===null?0:(targetExposure*100).toFixed(2)}%"></i></div></div>
      <div class="ap-waterfall-bottom"><strong>${withinBand?`未達${delta>=0?'加碼':'減碼'}門檻 ${band.toFixed(0)}pp，暫不因大盤調倉`:deltaLabel}</strong><span>目前現金 ${(cashRatio*100).toFixed(1)}% · 目標現金 ${targetExposure===null?'待確認':((1-targetExposure)*100).toFixed(1)+'%'}</span></div>
      ${t6?`<div class="ap-t6-details"><div><span>V12 原始水位</span><b>${(regime.raw_exposure*100).toFixed(1)}%</b></div><div><span>H2 平滑水位</span><b>${(regime.smoothed_exposure*100).toFixed(1)}%</b></div>${regime.trial_active?`<div><span>試單額外水位</span><b class="ap-trial-value">+${(regime.trial_extra*100).toFixed(1)}pp</b></div><div><span>試單剩餘有效期間</span><b>${regime.trial_remaining} 個交易日</b></div>`:''}${regime.trial_today&&!regime.trial_active?'<div><span>試單狀態</span><b>未啟用額外水位</b></div>':''}</div>`:''}
      ${k20?`<div class="ap-sox-details"><div class="ap-sox-heading"><strong>費半動能調控 · K20</strong><span>${soxReady?'資料有效':'未採用 · 回歸原始水位'}</span></div><div class="ap-t6-details"><div><span>H2＋T6 調整前水位</span><b>${(regime.sox_base_exposure*100).toFixed(1)}%</b></div><div><span>費半交易日</span><b>${esc(regime.sox_date||'待補')}${regime.sox_expected_date&&regime.sox_date!==regime.sox_expected_date?'／應為 '+esc(regime.sox_expected_date):''}</b></div><div><span>費半近20交易日漲跌幅</span><b class="${soxReady?tone(regime.sox_return20):''}">${soxReady?pct(regime.sox_return20):'待補'}</b></div><div><span>規則調整幅度</span><b>${soxReady?pp(regime.sox_requested_adjustment):'—'}</b></div><div><span>實際水位調整（限制0～100%）</span><b class="${tone(regime.sox_adjustment)}">${pp(regime.sox_adjustment)}</b></div>${soxReady?`<div><span>來源／取得時間</span><b>${esc(regime.sox_source)} · ${esc(dateLabel(regime.sox_available_at))}</b></div>`:''}</div><p class="ap-note">${esc((regime.reasons||[]).at(-1)||'')}</p></div>`:''}
      ${validTarget?`<p class="ap-waterfall-note">${pendingSales?`目前 ${pendingSales} 檔持股計畫賣出。`:targetExposure===0?'目前已無待賣持股。':'依最新名單調整個股權重。'} 下一可驗證交易日依開盤實際持股判斷門檻並嘗試成交；未達門檻仍可能因個股換股或配置限制交易，實際持股比例可能受流動性與交易條件影響。</p>`:'<p class="ap-waterfall-note">大盤或選股資料待確認，目前不以缺漏資料推定 0% 目標，也不觸發新調倉。</p>'}
      <details class="ap-evidence ap-risk-evidence"><summary>查看 V12 大盤風險與水位配置依據</summary>${lastExecution?`<p>最近開盤水位判斷 ${esc(lastExecution.date)}：開盤持股 ${(lastExecution.opening_exposure*100).toFixed(1)}%，${lastExecution.adjust?'達調倉門檻':'未達調倉門檻'}，執行配置目標 ${(lastExecution.effective_target*100).toFixed(1)}%。</p>`:''}${(decision?.regime?.reasons||[]).map(x=>`<p>${esc(x)}</p>`).join('')}<p>${esc(decision?.regime?.note||'')}</p></details>
    </section>
    <details class="ap-update-details"><summary>更新詳情${!modelReady?' · 待執行新版模型':''}${warnings.length?' · 有資料提醒':''}</summary><dl><dt>最新計算</dt><dd>${esc(data.latest_attempt?.available_at||data.updated_at)}</dd><dt>正式名單</dt><dd>${esc(decision?.available_at||'本次未發布')} · 第${decision?.revision||'—'}版</dd><dt>模型</dt><dd>${esc(decision?.model||'—')}</dd><dt>大戶資料</dt><dd>${esc(decision?.sources?.holder_date||'—')}</dd><dt>財報更新</dt><dd>${esc(decision?.sources?.earnings_updated_at||'—')}</dd><dt>研究更新</dt><dd>${esc(decision?.sources?.research_updated_at||'—')}</dd><dt>帳戶開始</dt><dd>${esc(data.started_at?.slice(0,10))}</dd></dl>${!modelReady?'<p>已載入新版介面；目前名單仍為前版模型結果，執行 AI paper portfolio 後才會使用新評分。</p>':''}${warnings.map(x=>`<p>${esc(x)}</p>`).join('')}<p>${(data.latest_attempt?.excluded_research||[]).map(x=>`${esc(x.name)} ${esc(x.ticker)}（${x.pending_documents}份待核對）`).join('、')}</p></details>${benchmarkPanel}<div class="ap-tabs" role="tablist" aria-label="模擬投資組合">${[['holdings','實際持倉'],['targets','配置計畫'],['trades','交易紀錄'],['equity','每日淨值']].map(([k,v])=>`<button type="button" role="tab" id="ap-tab-${k}" aria-controls="ap-panel" aria-selected="${tab===k}" tabindex="${tab===k?'0':'-1'}" data-ap-tab="${k}" class="${tab===k?'active':''}">${v}</button>`).join('')}</div><div id="ap-panel" role="tabpanel" aria-labelledby="ap-tab-${tab}" class="ap-content">${content}</div>${data.execution_warnings?.length?`<details class="ap-evidence"><summary>未成交／資料提醒（${data.execution_warnings.length}）</summary>${data.execution_warnings.slice(-20).reverse().map(x=>`<p>${esc(x.date)} ${esc(x.ticker)}：${esc(x.reason)}</p>`).join('')}</details>`:''}<details class="ap-rules"><summary>選股、時效與配置規則</summary>
<p><strong>模型 v6｜自結加扣分與大戶訊號確認</strong><br>${modelReady?'目前正式名單已採用v6。':'目前名單尚未採用v6；下次執行後才套用以下新規則，舊名單不倒填新分數。'}</p><p>個股總分＝籌碼40%＋基本面40%＋動能20%，另有單月自結−8～＋4分調整，分數不是上漲機率。內容由AI讀取網站已保存的原文／詳細解析，依來源證據判斷；不是只看評等與目標價，也不是逐次隨機重選。</p>
<details class="ap-evidence"><summary>籌碼：金額與相對強度一起看</summary><p>籌碼分數＝三大法人35%＋主動式ETF35%＋大戶20%＋成交金額排名10%。法人、ETF各自將「當日淨額金額排名」與「淨額占收盤市值排名」各占50%；市值＝同日收盤價×網站master已發行股數，缺股數的比例因子維持中性。保留資金規模，也辨識中小型股的相對買盤強度。</p><p>400張以上與千張以上大戶各占大戶因子一半，比較本週與前週持股比例變化，從公布後首個交易日起，前5日依序保留100%／80%／55%／35%／20%，第6、7日10%／5%，之後歸零；新一期直接取代舊一期。公布前維持中性，公布後尚未收盤保留100%。缺實際公布時間採統計日後週六15:00估計並標示。優先用完整歷史，缺級距不當成零變化。正面大戶訊號另比較公布前最後收盤至今的同期走勢：有足夠同業時比較大盤60%＋族群40%，否則比較大盤。連續兩個交易日的單日報酬落後比較基準，且公布後累計落後至少3百分點，剩餘正面加分減半；落後至少5百分點且收盤跌破公布後前兩日低點，正面加分歸零。缺比較行情時正面加分暫減半；負面訊號僅按時效衰減。不重複扣動能分，不認定大戶已賣出。這些門檻為待驗證設定。法人、ETF目前採當日淨額，未把連買天數或申購造成的被動增持當成已確認的主動買盤。</p></details>
<details class="ap-evidence"><summary>財報：EPS、毛利率、OPM與上一季交叉比較</summary><p>基本面＝財務60%＋研究內容40%。財務持續性分數＝75%季變化＋25%獲利狀態；季變化由EPS30%、毛利率30%、OPM40%組成。EPS比較季增減，毛利率與OPM比較百分點；獲利狀態的EPS隨金額連續變動，不再只分賺錢／虧損。</p><p>Q3 EPS 20元、Q2 22元會辨識為季減。若EPS衰退但毛利率、OPM都未惡化，EPS負向偏離縮至四分之一、最低42分；只標示可能有業外、稅率或股數因素，沒有證據不認定原因。EPS增加但兩項本業利率都下降，EPS正向偏離縮至35%、最高60分，避免一次性收益掩蓋本業轉弱。</p><p>財務分數＝80%持續性＋20%公告事件；事件半衰期5個交易日，持續性保留至新財報，最長150個日曆日。缺單季時以官方累計狀態保守補充，不能把累計誤當單季、不能宣稱季成長。</p></details>
<details class="ap-evidence"><summary>自結：依單月表現加扣分，未公布維持中性</summary><p>比較基準＝前一季單季EPS÷3；達成率＝單月自結EPS÷比較基準。超過120%才加分，100%～120%中性，80%～未滿100%小扣分，低於80%加重。前季EPS 1元時，單月超過0.4元才加分，1/3～0.4元中性。採最新單一月份／最新公告，不要求連續兩月、不重複累加；未公布或前季資料缺值不加不扣。</p><p>原始調整：120%以上到300%由0線性增至＋4分；80%～100%由−1線性回升至0分；0%～80%由−6線性回升至−1分。盈轉虧扣6～8分，虧轉盈加2～4分；持續虧損按單月與前季月均EPS差額判斷，虧損縮小最多加1.5分、擴大最多扣4分。零／近零基期（前季EPS低於0.15元）不硬算百分比，採差額平滑換算，尺度至少0.05元，範圍±4分；明確盈虧轉換優先判斷。</p><p>加扣分直接調整個股總分，半衰期10個交易日；公告45日內、月份落後不超過2個月才採用。10月自結比較Q3，9月比較Q2。單月可能含業外，不直接推估整季。財報EPS同樣辨識虧轉盈、盈轉虧與虧損擴大／縮小；盈轉虧不適用一般EPS季減的扣分緩和。</p></details>
<details class="ap-evidence"><summary>券商報告與法說／訪談：根據內容與來源原句評估</summary><p>每家券商各取最新一份，納入所有可明確對應該公司的來源；不限制最近3家。以報告本身日期計算時效，近期權重較高，過90日排除；同一家券商舊報告不疊加。法說／訪談只用最新事件日期的一份最完整紀錄，有11月就不再拿10月加分，同事件重複紀錄不重複計分。</p><p>AI評估需求／訂單25%、本業獲利與產品組合25%、展望／財測修正25%、具體催化15%、風險10%。每項判斷-2至+2、乘0～1證據信心，風險只允許負向或中性；非零必須附可在來源逐字找到的原句。區分已實現業績、公司說法、券商預測與未確認情境，不把目標價、評等直接換成分數，不把其他公司數字移植。</p><p>研究內容分數由券商60%＋最新法說／訪談40%組成，缺某類維持中性。來源分數含75%長效觀點（半衰期30交易日）及25%短期事件（5交易日）；券商間再依新舊加權。保留各家理由與多空分歧，來源多不會自動多加分。同內容與模型沿用已驗證分析快取；最新資料待分析或無法核對時，該公司本次不直接交易並列出排除原因，其餘已驗證標的照常發布最新名單；不以評等或舊法說代替。沒有研究資料的公司研究因子維持中性。</p></details>
<details class="ap-evidence"><summary>動能、入選門檻與全市場範圍</summary><p>動能＝近5日相對分數60%＋近20日相對分數40%。每期先比較個股與同期加權指數報酬差；有足夠熱力圖族群同業時，大盤比較占60%、族群比較占40%。族群採排除自身的等權平均，至少3檔同業、涵蓋70%以上；優先子族群，重疊族群固定等權，不事後挑最好比較的族群。族群不足或不在名單內時，全數比較同期大盤。50分代表與基準相當，跑贏高於50、跑輸低於50；以tanh平滑換算（5日尺度5百分點、20日10百分點），不是單純看誰漲最多。每檔列出個股、大盤、同業報酬與超額百分點。近5日漲逾25%只提醒風險，不固定扣分。總分至少60、基本面至少50且財務可驗證、籌碼至少55、動能至少45；當日成交至少1,000萬元、近5日均量至少10萬股。缺基本面者需籌碼70、動能75及法人／ETF證據，最多5%部位。獨立型態選股尚未併入。</p><p>股票池：官方名冊 ${decision?.coverage?.register||data.latest_attempt?.coverage?.register||'—'} 檔；可驗證21日行情 ${decision?.coverage?.usable_stocks||data.latest_attempt?.coverage?.usable_stocks||'—'} 檔；可評估ETF ${decision?.coverage?.usable_etfs??data.latest_attempt?.coverage?.usable_etfs??'—'} 檔。上市上櫃普通股全市場掃描，興櫃、權證、特別股不在本版。缺價或歷史不足不當成不看好。</p></details>
<details class="ap-evidence"><summary>現金水位、ETF與模擬交易</summary><p>本金 $${money(initial)}；最多${data.config.max_positions}檔。個股上限${(data.config.max_stock_weight??.15)*100}%、ETF上限${(data.config.max_etf_weight??.25)*100}%，單一產業個股合計上限${(data.config.max_sector_weight??.35)*100}%、ETF合計50%、探索型個股上限${(data.config.discovery_weight??.05)*100}%。以上均以帳戶淨值（含現金）為基準，為目標配置上限而非固定權重。依 max(1,總分－50) 的平方加權，評分越高配置權重越大，受單檔／產業／ETF及大盤目標水位約束；不再除以波動率。高波動不直接扣分、降權或排除，波動僅作風險資訊，不代表預期報酬必然較高。</p><p>大盤配置依照「綜合指標」同一套 V12 風險分數，原始 Smoothstep 曲線0～100%；H2 減碼反應50%、加碼80%，總水位減碼門檻5pp、加碼15pp。T6 試單機會於觸發分數低於70時增加27.5pp（總水位上限100%），最長20交易日，較觸發日惡化5分即退出。標籤僅首次觸發日顯示，試單有效期間另列。費半 K20 僅調整 H2＋T6 後的總目標水位，不改 V12 燈號或個股分數。近20個美股交易日漲幅≥1%：原始水位低於40%加20pp、40%以上（含40%）加60pp；跌幅達8%減20pp；其餘不變。限制0～100%，40%門檻存在跳躍。資料缺漏、過期、收盤修正期間或來源衝突則回歸原始水位。K20 已做隔日收盤代理回測，尚未完成最新版本開盤驗證。實際開盤仍按總水位門檻、個股配置與成交限制執行。不設最低 20% 或最高 90% 水位限制；V12 日期或來源無法驗證時，本次不發布新名單，亦不會將資料缺漏誤當全現金訊號。投資水位於下一可驗證交易日開盤嘗試調整，實際部位可能因流動性、漲跌停或成交限制而不同。</p><p>ETF依大盤40%、可辨識持股基本面30%、動能30%評分，持股基本面涵蓋不足60%維持中性，不套公司EPS。整數股可含零股，決策公布後下一可驗證開盤才模擬成交；移出名單嘗試賣出，保留者持有或調整權重。含費稅、滑價，股票賣出稅${data.config.sell_tax*100}%、股票型ETF${(data.config.etf_sell_tax||.001)*100}%。</p></details>
<p>每次執行讀取網站資料快照；同步讀取已發布資料不等於代跑各資料更新流程。有效資料、計算日與模型相同時結果一致；來源或模型變更建立新版本，舊決策及成交紀錄保留，不倒填績效。研究待核對採個別公司排除；整體行情或大盤風險資料驗證失敗時，不發布新名單，也不沿用過期目標下新單。</p>
${(data.limitations||[]).map(x=>`<p>${esc(x)}</p>`).join('')}</details><p class="ap-note">累積 ${rows.length} 個交易日 · 模擬績效尚不足以驗證策略有效性。</p>`;
    root.querySelectorAll('.ap-position-toggle').forEach(button => {
      button.onclick = () => {
        const detail = document.getElementById(button.getAttribute('aria-controls'));
        detail.hidden = !detail.hidden;
        button.setAttribute('aria-expanded', String(!detail.hidden));
      };
    });
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
      const next=await response.json();if(![1,2].includes(next.schema)||!next.config||!Array.isArray(next.decisions))throw Error('invalid portfolio');
      const marketResponse=await fetch('./data/market_monitor.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null);
      const nextMarket=marketResponse?.ok?await marketResponse.json().catch(()=>null):null;
      if(id!==request)return;data=next;marketData=nextMarket;render();
    } catch(e) {
      if(id!==request)return;
      if(data){render();const p=document.createElement('p');p.className='ap-warning';p.textContent='載入失敗，目前顯示上次成功的帳本。';root.prepend(p);}
      else root.innerHTML='<div class="ap-empty">模擬帳本尚未建立。上傳程式後執行 AI paper portfolio，首次只建立名單，之後才累積交易與績效。</div>';
    }
  };
})();




