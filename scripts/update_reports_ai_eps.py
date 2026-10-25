#!/usr/bin/env python3
"""Single-call financial extraction for new broker/LINE reports. No second API call."""
import copy
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import update_reports_ai as base
_original_post=base.requests.post
_original_normalize=base.normalize_report
EPS_INSTRUCTION='''
25. 保留 quarterly_eps 欄位：[{"period":"2026-Q4","eps":10.15,"type":"forecast","source":"broker"}]；只列報告作者明確預估的單季 EPS，禁止共識、累計、年度 EPS 混入。
26. 同一次回覆 JSON 新增 financial_forecasts 陣列，無數字則 []，每筆：
{"period":"2027","metric":"eps","value":36.65,"unit":"元/股","type":"forecast","source":"broker","scope":"company","evidence":"EPS (元) 21.96 36.65 49.05"}
period 必須明確為 YYYY 或 YYYY-Q1..Q4；metric 限 eps,revenue,gross_margin,operating_margin,net_margin,operating_profit,net_income,roe,roa,capex,dividend,other；value 必須是數字，不是字串；unit 保留原文單位（百萬元/億元/美元/%/元等）；type 限 actual,forecast,previous_forecast,guidance；source 限 broker,company,consensus；scope 預設 company，業務部門要寫具體名稱。只列原文可核對的數字，不能從百分比推算 EPS，不能把 EPS 上修 12% 當 EPS=12，不能把目標價當 EPS。表格「原估／新估／差異」新估為 forecast，原估為 previous_forecast，差異不當作財務絕對數值。區分券商預估、公司指引、市場共識、歷史實績；有歧義省略。每筆 evidence 需附原文 20~160 字。年度/季度混合表都要逐欄解析。絕對不可捏造，沒有就 []。此要求不得另外呼叫 API。
'''
PERIOD=re.compile(r'^20\d{2}(?:-Q[1-4])?$')
METRICS={'eps','revenue','gross_margin','operating_margin','net_margin','operating_profit','net_income','roe','roa','capex','dividend','other'}
PERCENT={'gross_margin','operating_margin','net_margin','roe','roa'}
def normalize_financial(items):
    if not isinstance(items,list):return []
    out=[];seen=set()
    for x in items[:500]:
        if not isinstance(x,dict):continue
        period=str(x.get('period','')).strip().upper()
        metric=str(x.get('metric','')).strip().lower()
        val=x.get('value')
        if not PERIOD.fullmatch(period) or metric not in METRICS or isinstance(val,bool):continue
        try:val=float(val)
        except (TypeError,ValueError):continue
        if not -1e12<val<1e12:continue
        unit=str(x.get('unit') or '')[:40]
        if metric in PERCENT and not (-100<=val<=1000):continue
        typ=str(x.get('type') or 'forecast').lower()
        source=str(x.get('source') or 'broker').lower()
        if typ not in {'actual','forecast','previous_forecast','guidance'} or source not in {'broker','company','consensus'}:continue
        evidence=str(x.get('evidence') or '').strip()
        if len(evidence)<8:continue
        scope=str(x.get('scope') or 'company')[:80]
        key=(period,metric,typ,source,scope)
        if key in seen:continue
        seen.add(key)
        out.append({'period':period,'metric':metric,'value':val,'unit':unit,'type':typ,'source':source,'scope':scope,'evidence':evidence[:240]})
    return out

def _post(url,*args,**kwargs):
    if url==base.API_URL:
        payload=copy.deepcopy(kwargs.get('json'))
        if not isinstance(payload,dict):raise RuntimeError('Unexpected OpenAI payload; blocked')
        try:
            messages=payload['input'];content=messages[0]['content'][0]
            original=content['text']
            if 'financial_forecasts' not in original:content['text']=original+EPS_INSTRUCTION
            kwargs['json']=payload
        except (KeyError,IndexError,TypeError) as exc:
            raise RuntimeError('Unexpected prompt shape; blocked') from exc
    return _original_post(url,*args,**kwargs)

def _normalize(obj,src):
    report=_original_normalize(obj,src)
    from broker_eps_pipeline import normalize
    report['quarterly_eps']=normalize(obj.get('quarterly_eps'))
    report['financial_forecasts']=normalize_financial(obj.get('financial_forecasts'))
    return report

def main():
    base.requests.post=_post;base.normalize_report=_normalize;base.main()
if __name__=='__main__':main()
