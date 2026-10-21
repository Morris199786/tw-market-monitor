上市自結款項研究套件（非正式上線版）

已包含：
1. 歷史候選快照 walk_forward_scores.csv
2. 注意交易自結標籤 event_audit.csv
3. 由證交所官方注意交易資料補齊逐日款項的程式 backfill_clauses.py
4. 研究版 self_report_predict.py（不是經過款項樣本外驗證的正式模型）

重要限制：目前執行環境無法從 Python 連線證交所下載完整原始資料，故本套件沒有聲稱完成款項回填與正式新舊模型比較。請勿將研究版直接覆蓋正式 GitHub 模型。

在可連線證交所的環境執行：
python backfill_clauses.py --start 2026-06-01 --end 2026-09-30

會輸出：
- twse_notice_clauses.json（官方歷史注意交易紀錄）
- clause_enriched_scores.csv（加入款項的候選特徵）

後續仍須：正式 V12 對照、樣本外回測與款項條件統計；未完成前不可宣稱模型改善。
