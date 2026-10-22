#!/usr/bin/env python3
"""One-shot AI report processing with quarterly EPS in the SAME API request.
Does not create any additional OpenAI call. Keeps original claim/Telegram logic.
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_reports_ai as base

_original_post = base.requests.post
_original_normalize = base.normalize_report

EPS_INSTRUCTION = '''\n25. 在原本同一次回覆 JSON 內新增 quarterly_eps 陣列，格式為
"quarterly_eps": [{"period":"2026-Q4","eps":10.15,"type":"forecast","source":"broker"}]。
只列報告作者自己明確預估的「單季 EPS」，以元/股表示；不得把市場共識、歷史實際值、年度 EPS、累計 EPS、情境試算當成券商單季預估。季度須有明確年度與 Q1~Q4，模糊時省略，不猜測；找不到就 []。不額外呼叫 API。\n'''

def _post(url, *args, **kwargs):
    if url == base.API_URL:
        payload = copy.deepcopy(kwargs.get('json'))
        if not isinstance(payload, dict):
            raise RuntimeError('Unexpected OpenAI payload; refusing unguarded call')
        try:
            messages = payload['input']
            system_text = messages[0]['content'][0]['text']
            if 'quarterly_eps' not in system_text:
                messages[0]['content'][0]['text'] = system_text + EPS_INSTRUCTION
            kwargs['json'] = payload
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError('Unexpected report prompt shape; refusing API call') from exc
    return _original_post(url, *args, **kwargs)

def _normalize(obj, src):
    report = _original_normalize(obj, src)
    from broker_eps_pipeline import normalize
    report['quarterly_eps'] = normalize(obj.get('quarterly_eps'))
    return report

def main():
    base.requests.post = _post
    base.normalize_report = _normalize
    base.main()

if __name__ == '__main__':
    main()
