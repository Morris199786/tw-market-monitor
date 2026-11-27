#!/usr/bin/env python3
"""Evidence-dated EPS comparison; offline, deterministic, no paid calls.

Only actual EPS with an explicit, verified announcement date may match a
broker report whose date is earlier than or equal to. Never derive a disclosure date
from a fiscal period, file mtime, or a scheduled board meeting.
"""
from __future__ import annotations
import json
import math
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUARTER = re.compile(r'^20\d{2}-Q[1-4]$')
MONTH = re.compile(r'^20\d{2}-(?:0[1-9]|1[0-2])$')
TICKER = re.compile(r'^\d{4}$')

def load(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default

def valid_date(value):
    s = str(value or '')[:10]
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return ''

def gm_valid_date(value):
    """Normalize broker report dates for gross margin without changing EPS logic."""
    return valid_date(str(value or '')[:10].replace('/', '-'))

def number(value):
    if isinstance(value, bool) or value is None or str(value).strip() == '':
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None

def actuals(data):
    """All verifiably dated monthly/quarterly announcements, including history."""
    seen = set()
    sources = (
        ('self_reports.json', 'items'),
        ('self_reports_history.json', 'items'),
        ('quarterly_earnings.json', 'reports'),
        ('quarterly_earnings_announcements_history.json', 'items'),
    )
    for filename, key in sources:
        for r in load(data / filename, {}).get(key, []):
            ticker = str(r.get('ticker') or '')
            day = valid_date(r.get('publish_date'))
            if not TICKER.fullmatch(ticker) or not day:
                continue
            candidates = []
            if filename.startswith('self_reports'):
                month = str(r.get('monthly_period') or '')
                if MONTH.fullmatch(month):
                    period = f'{month[:4]}-Q{(int(month[5:])-1)//3+1}'
                    candidates.append(('monthly', month, period, number(r.get('monthly_eps'))))
                # A self-report may also explicitly disclose last quarter's EPS.
                # Its own publication date, not the financial period, is used.
                qp = str(r.get('quarter_period') or '')
                if QUARTER.fullmatch(qp):
                    candidates.append(('quarterly', qp, qp, number(r.get('quarter_eps'))))
            else:
                qp = str(r.get('period') or '')
                if QUARTER.fullmatch(qp):
                    candidates.append(('quarterly', qp, qp, number(r.get('eps'))))
            for kind, actual_period, period, eps in candidates:
                if eps is None:
                    continue
                ident = (ticker, kind, actual_period, day, eps)
                if ident in seen:
                    continue
                seen.add(ident)
                yield {'ticker': ticker, 'name': r.get('name') or '', 'kind': kind,
                       'actual_period': actual_period, 'period': period,
                       'announcement_date': day, 'actual_eps': eps,
                       'actual_source': filename}

def compare(root=ROOT):
    data = root / 'data'
    # Keep the legacy EPS JSON (including sealed historical forecasts).
    # Supplement only missing report+quarter pairs from the ONE-SHOT AI data.
    # No calls to the model and no PDF reads in this comparison action.
    forecasts = list(load(data / 'broker_eps_forecasts.json', {'items': []}).get('items', []))
    known = {(str(x.get('report_id')), str(x.get('period'))) for x in forecasts}
    ai_added = 0
    from broker_eps_pipeline import ai_eps_rows, saved_reports
    for report in saved_reports(data):
        if not isinstance(report, dict):
            continue
        rid = str(report.get('source_file_id') or report.get('id') or '')
        ticker = str(report.get('ticker') or '')
        broker = str(report.get('broker') or '')
        report_day = gm_valid_date(report.get('date'))
        if not rid or not TICKER.fullmatch(ticker) or not broker or not report_day:
            continue
        rows, _ = ai_eps_rows(report)
        for row in rows:
            key = (rid, row['period'])
            if key in known:
                continue
            forecasts.append({'report_id':rid, 'ticker':ticker, 'broker':broker,
                              'report_date':report_day, 'source_url':report.get('source_url') or '',
                              'period':row['period'], 'eps':row['eps']})
            known.add(key)
            ai_added += 1
    by_key = {}
    for f in forecasts:
        ticker, period = str(f.get('ticker') or ''), str(f.get('period') or '')
        day, eps = valid_date(f.get('report_date')), number(f.get('eps'))
        if not TICKER.fullmatch(ticker) or not QUARTER.fullmatch(period) or not day or eps in (None, 0) or not f.get('report_id'):
            continue
        by_key.setdefault((ticker, period), []).append((f, day, eps))
    matches = {}
    audit = {'direct_ai_forecasts_added': ai_added, 'forecasts': len(forecasts), 'valid_forecasts': sum(map(len, by_key.values())),
             'dated_actuals': 0, 'potential_same_ticker_period': 0,
             'excluded_late': 0, 'matches': 0}
    for a in actuals(data):
        audit['dated_actuals'] += 1
        for f, report_day, estimate in by_key.get((a['ticker'], a['period']), []):
            audit['potential_same_ticker_period'] += 1
            if report_day > a['announcement_date']:
                audit['excluded_late'] += 1
                continue
            rid = str(f['report_id'])
            key = (a['ticker'], a['kind'], a['actual_period'], a['announcement_date'], a['actual_eps'], rid)
            matches[key] = {
                'ticker': a['ticker'], 'name': a['name'], 'period': a['period'],
                'actual_kind': a['kind'], 'actual_period': a['actual_period'],
                'announcement_date': a['announcement_date'], 'actual_eps': a['actual_eps'],
                'broker': f.get('broker') or '', 'report_date': report_day,
                'report_id': rid, 'forecast_eps': estimate,
                'ratio_pct': round(a['actual_eps'] / estimate * 100, 1),
                'ratio_label': '單月／季預估比' if a['kind'] == 'monthly' else '季度達成率',
                'source_url': f.get('source_url') or '',
                'actual_source': a['actual_source']}
    output = {'version': 3, 'items': sorted(matches.values(), key=lambda x:
              (x['ticker'], x['period'], x['actual_period'], x['announcement_date'], x['report_date'], x['report_id']))}
    audit['matches'] = len(output['items'])
    for filename, value in (('broker_eps_comparisons.json', output), ('broker_eps_compare_audit.json', audit)):
        p = data / filename
        content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        if not p.exists() or p.read_text(encoding='utf-8') != content:
            p.write_text(content, encoding='utf-8')
    print('EPS compare audit:', json.dumps(audit, ensure_ascii=False))
    gm_output = compare_gross_margin(root)
    print('Quarterly gross-margin matches:', len(gm_output['items']))
    compare_operating_margin(root)
    print('API calls=0; PDF parses=0')
    return output



def parse_quarter(value):
    """Recognize explicit *quarter* periods only; never turn an annual figure into a quarter."""
    value = str(value or '').strip().upper().replace(' ', '').replace("'", '').replace('’', '')
    patterns = (
        r'(20\d{2})-?Q([1-4])(?:E|F)?',   # 2026-Q4 / 2026-Q4E
        r'([1-4])Q(20\d{2}|\d{2})(?:E|F)?', # 3Q26 / 4Q2026E
        r'Q([1-4])(20\d{2}|\d{2})(?:E|F)?', # Q326 / Q4'26 (without apostrophe)
        r'(20\d{2})\u5e74\u7b2c?([\u4e00-\u56db1-4])\u5b63(?:\u5ea6)?',
    )
    for i, pattern in enumerate(patterns):
        m = re.fullmatch(pattern, value)
        if not m:
            continue
        if i == 0 or i == 3:
            year, q = m.groups()
            if i == 3:
                q = {'\u4e00':'1','\u4e8c':'2','\u4e09':'3','\u56db':'4'}.get(q, q)
        else:
            q, year = m.groups()
            if len(year) == 2:
                year = '20' + year
        return f'{year}-Q{q}'
    return ''


def table_margin_value(cell):
    """Accept an unambiguous percentage cell only, never ranges, deltas or text explanations."""
    if isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        value = number(cell)
    else:
        s = str(cell or '').strip().replace(',', '')
        if not re.fullmatch(r'\d+(?:\.\d+)?\s*%?', s):
            return None
        value = number(s.rstrip('%').strip())
    return value if value is not None and 0 <= value <= 100 else None


def quarter_mentions(text):
    """Look for a unique explicit fiscal quarter within a title or header."""
    s = str(text or '').upper()
    spans = re.findall(r'20\d{2}-Q[1-4]|[1-4]Q(?:20)?\d{2}|20\d{2}\u5e74\u7b2c?[\u4e00-\u56db1-4]\u5b63', s)
    periods = {p for fragment in spans if (p := parse_quarter(fragment))}
    return next(iter(periods)) if len(periods) == 1 else ''


def table_gm_forecasts(report):
    """Read pre-parsed AI visualization tables; require explicit broker estimate provenance.

    Supported: (A) quarter-per-row tables with GM column and forecast row;
    (B) metric-per-row tables with quarter-specific broker-estimate column.
    Never infer quarter from report date or a single annual estimate.
    """
    for table in report.get('visualizations') or []:
        if not isinstance(table, dict) or table.get('type') != 'table':
            continue
        headers = table.get('headers') or []
        rows = table.get('rows') or []
        if not isinstance(headers, list) or not isinstance(rows, list):
            continue
        headers = [str(h or '').strip() for h in headers]
        gm_cols = [i for i,h in enumerate(headers) if re.search(r'\u6bdb\u5229\u7387|gross\s*margin', h, re.I)]
        # A: period in first cell, GM in designated column, explicitly labeled forecast.
        for row in rows:
            if not isinstance(row, list) or not row:
                continue
            period = parse_quarter(row[0])
            if period and gm_cols:
                hint = ' '.join(str(x or '') for x in row)
                # Disallow historical/actual/consensus even when an E suffix occurs elsewhere.
                marked_forecast = (bool(re.search(r'\u5238\u5546\u9810\u4f30|\u5206\u6790\u5e2b\u9810\u4f30|\u6295\u9867\u9810\u4f30', hint))
                                   or bool(re.fullmatch(r'.*(?:E|F)', str(row[0]).strip().upper())))
                marked_actual = bool(re.search(r'\u5be6\u969b|\u5be6\u7e3e|\u6b77\u53f2|\u5171\u8b58|consensus', hint, re.I))
                if marked_forecast and not marked_actual:
                    for i in gm_cols:
                        if i < len(row) and (v := table_margin_value(row[i])) is not None:
                            yield period, v, f'table:{table.get("title") or ""}'
            # B: metric in first cell, explicit quarterly forecast in column header.
            if not re.search(r'\u6bdb\u5229\u7387|gross\s*margin', str(row[0]), re.I):
                continue
            title_quarter = quarter_mentions(table.get('title'))
            for i, header in enumerate(headers[1:], start=1):
                if i >= len(row):
                    continue
                if not re.search(r'\u9810\u4f30|estimate|forecast|\u9810\u6e2c', header, re.I):
                    continue
                if re.search(r'\u5171\u8b58|consensus|\u516c\u53f8\u6307\u5f15|guidance|\u5be6\u969b|\u5be6\u7e3e', header, re.I):
                    continue
                period = quarter_mentions(header) or title_quarter
                if not period:
                    continue
                # Do not use '2026 Q4 company guidance' as broker forecast.
                # A specific broker must be named in the header or table description.
                named_broker = str(report.get('broker') or '').lower() in header.lower()
                explicit_broker = bool(re.search(r'\u5238\u5546\u9810\u4f30|\u6295\u9867\u9810\u4f30|\u5206\u6790\u5e2b\u9810\u4f30', header))
                short_broker = bool(re.search(r'\b(?:citi|morgan stanley|goldman sachs|daiwa|ubs|clsa)\b', header, re.I))
                if not (named_broker or explicit_broker or short_broker):
                    continue
                if (v := table_margin_value(row[i])) is not None:
                    yield period, v, f'table:{table.get("title") or ""}'



METRIC_ALIASES = {
    'gross_margin': r'毛利率|gross\s*(?:profit\s*)?margin|\bGPM\b|\bGM\b',
    'operating_margin': r'營業利益率|營業利潤率|營益率|營利率|operating\s*(?:profit\s*)?margin|\bOPM\b|\bOP\s*margin\b',
    'eps': r'每股盈餘|每股純益|\bEPS\b',
}
FORECAST_MARK = re.compile(r'預估|預測|估計|forecast|estimate|projection|(?:\d|季)[EF]\b', re.I)
NON_BROKER = re.compile(r'共識|consensus|公司指引|公司預估|管理層|guidance|management|前次|原估|previous|old estimate|實績|實際|actual|歷史', re.I)

def saved_metric_rows(report, metric):
    """Read existing structured rows and explicitly dated forecast tables/text only."""
    pattern = METRIC_ALIASES[metric]
    def value_of(v):
        return number(str(v).strip().replace(',', '').rstrip('%').strip()) if not isinstance(v, bool) else None
    for row in report.get('financial_forecasts') or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get('metric') or '').replace('_', ' ')
        if not re.fullmatch(pattern, label, re.I):
            continue
        if str(row.get('type') or '').lower() not in ('forecast','estimate','projection'):
            continue
        if str(row.get('source') or '').lower() not in ('broker','analyst','research',''):
            continue
        if str(row.get('scope') or 'company').lower() not in ('company','consolidated'):
            continue
        unit = str(row.get('unit') or '').lower()
        if metric != 'eps' and unit and not any(x in unit for x in ('%','百分','percent','pct')):
            continue
        period = parse_quarter(row.get('period')) or quarter_mentions(row.get('period'))
        v = value_of(row.get('value'))
        if period and v is not None:
            yield period, v, 'structured'
    for table in report.get('visualizations') or []:
        if not isinstance(table, dict) or table.get('type') != 'table':
            continue
        headers = table.get('headers') or []
        rows = table.get('rows') or []
        if not isinstance(headers, list) or not isinstance(rows, list):
            continue
        title = str(table.get('title') or '')
        context = title + ' ' + str(table.get('description') or '')
        for row in rows:
            if not isinstance(row,list) or not row:
                continue
            label = str(row[0])
            for i, header in enumerate(headers[1:],1):
                if i >= len(row):
                    continue
                header = str(header)
                if re.search(pattern, header, re.I):
                    period = parse_quarter(label) or quarter_mentions(label)
                    hint = label + ' ' + header
                elif re.search(pattern,label,re.I):
                    period = parse_quarter(header) or quarter_mentions(header) or quarter_mentions(title)
                    hint = header + ' ' + label
                else:
                    continue
                if not period or NON_BROKER.search(hint):
                    continue
                # A comparison-table title does not identify which cell is a forecast.
                # Require explicit forecast label on the actual row/column.
                axis = label if re.search(pattern, header, re.I) else header
                explicit = FORECAST_MARK.search(axis) or re.search(r'(?:[EF])
                if re.search(r'年增|季增|變動|調整幅度|差異|change|growth|delta|bps|pp\b',hint,re.I):
                    continue
                v = value_of(row[i])
                if v is not None:
                    yield period, v, 'table:'+title
    # Text fallback: only a single explicit quarter and a forecast marker in the same clause.
    for field in ('summary','detail','key_points','forecast_changes'):
        raw=report.get(field)
        chunks=raw if isinstance(raw,list) else [raw]
        for chunk in chunks:
            if not isinstance(chunk,str):
                continue
            for clause in re.split(r'[。；;\n]',chunk):
                period=quarter_mentions(clause)
                if not period or not FORECAST_MARK.search(clause) or NON_BROKER.search(clause) or re.search(r'FY\d{2,4}|20\d{2}年(?:度|全年)|全年|annual',clause,re.I):
                    continue
                # Require forecast before the metric, not elsewhere after an actual.
                # Reject result commentary ('達', '創高', '優於預期') and comparisons.
                if re.search(r'優於|低於|符合|高於|不及|創新高|創高|公布|公告|達成|較預期|beat|miss|reported|results',clause,re.I):
                    continue
                if re.search(r'年增|季增|上修|下修|調升|調降|由.+至|從.+到|區間|range|同比|環比',clause,re.I):
                    continue
                suffix=r'\s*%' if metric!='eps' else r'\s*(?:元|NTD|TWD)?'
                for m in re.finditer('(?:'+pattern+r')\s*(?:預估|預測|估計|estimate|forecast)?\s*(?:為|達|約|:|：|=|of|at)?\s*([+-]?\d+(?:\.\d+)?)'+suffix,clause,re.I):
                    prefix=clause[:m.start()]
                    if not (FORECAST_MARK.search(prefix) or FORECAST_MARK.search(m.group(0))):
                        continue
                    v=number(m.group(1))
                    if v is not None:
                        yield period,v,'text:'+field

def compare_margin_metric(root, metric):
    from broker_eps_pipeline import saved_reports
    data=root/'data'
    forecasts={}
    audit={'candidates':0,'conflicting_report_quarters':0,'excluded_late':0,'matches':0}
    for report in saved_reports(data):
        rid=str(report.get('source_file_id') or report.get('id') or '')
        ticker=str(report.get('ticker') or '')
        broker=str(report.get('broker') or '')
        day=gm_valid_date(report.get('date'))
        if not rid or not TICKER.fullmatch(ticker) or not broker or not day:
            continue
        values={}
        for period,value,evidence in saved_metric_rows(report,metric):
            values.setdefault(period,{})
            existing=next((v for v in values[period] if abs(v-value)<=0.011),None)
            if existing is None:
                values[period][value]=evidence
        for period, estimates in values.items():
            conflict=len(estimates)>1
            audit['conflicting_report_quarters']+=int(conflict)
            for value,evidence in estimates.items():
                audit['candidates']+=1
                forecasts.setdefault((ticker,period),[]).append((rid,broker,day,value,report.get('source_url') or '',evidence,conflict))
    matches={}
    # Mirror the earnings page: recovered announcements first, current records
    # win, and the official standalone OPM series overrides the embedded value.
    merged={}
    for source in ('quarterly_earnings_recovered.json','quarterly_earnings.json'):
        for row in load(data/source,{}).get('reports',[]):
            k=(str(row.get('ticker') or ''),str(row.get('period') or ''))
            prev=merged.get(k,({},source))[0]
            combined={**prev,**row}
            if row.get('gross_margin') is None:
                combined['gross_margin']=prev.get('gross_margin')
            merged[k]=(combined,source)
    opm=load(data/'quarterly_opm.json',{}) if metric=='operating_margin' else {}
    opm_metrics=opm.get('metrics',{}) if opm.get('schema')==1 else {}
    audit['dated_actuals']=0
    audit['opm_sidecar_values']=0
    for (ticker,period),(actual,source) in merged.items():
            day=valid_date(actual.get('publish_date'))
            value=number(actual.get(metric))
            if metric=='operating_margin':
                side=opm_metrics.get(ticker+'|'+period) or {}
                side_value=number(side.get('value'))
                if side_value is not None:
                    value=side_value
                    audit['opm_sidecar_values']+=1
            if day and value is not None:
                audit['dated_actuals']+=1
            if not day or value is None:
                continue
            for rid,broker,report_day,estimate,url,evidence,conflict in forecasts.get((ticker,period),[]):
                if report_day>=day:
                    audit['excluded_late']+=1
                    continue
                matches[(ticker,period,day,value,rid,estimate)]=dict(ticker=ticker,name=actual.get('name') or '',period=period,announcement_date=day,actual_kind='quarterly',broker=broker,report_date=report_day,report_id=rid,source_url=url,actual_source=source,evidence=evidence,needs_review=conflict,difference_pp=round(value-estimate,2),**{'actual_'+metric:value,'forecast_'+metric:estimate})
    output={'version':2,'metric':metric,'unit':'%','items':[matches[k] for k in sorted(matches)]}
    audit['matches']=len(matches)
    dest=data/('broker_'+metric+'_comparisons.json')
    content=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
    if not dest.exists() or dest.read_text(encoding='utf-8')!=content:
        dest.write_text(content,encoding='utf-8')
    print(metric+' audit:',json.dumps(audit,ensure_ascii=False))
    return output

def compare_gross_margin(root=ROOT):
    return compare_margin_metric(root,'gross_margin')

def compare_operating_margin(root=ROOT):
    return compare_margin_metric(root,'operating_margin')


if __name__ == '__main__':
    compare()
,axis.strip(),re.I)
                broker_name = str(report.get('broker') or '').strip()
                named = bool(broker_name and broker_name.lower() in axis.lower())
                if not (explicit or named):
                    # Quarter columns in a pure forecast table are allowed only
                    # when every quarter column is explicitly forecast-marked by context.
                    pure = bool(re.search(r'財務預測|財務預估|獲利預測|獲利預覽|financial forecasts|earnings preview',title,re.I))
                    if not (pure and parse_quarter(axis) and not NON_BROKER.search(context) and not re.search(r'比較|vs\.?|comparison|業績|財報',title,re.I)):
                        continue
                if NON_BROKER.search(axis) or re.search(r'差異|達成率|surprise|variance|差距',axis,re.I):
                    continue
                if re.search(r'年增|季增|變動|調整幅度|差異|change|growth|delta|bps|pp\b',hint,re.I):
                    continue
                v = value_of(row[i])
                if v is not None:
                    yield period, v, 'table:'+title
    # Text fallback: only a single explicit quarter and a forecast marker in the same clause.
    for field in ('summary','detail','key_points','forecast_changes'):
        raw=report.get(field)
        chunks=raw if isinstance(raw,list) else [raw]
        for chunk in chunks:
            if not isinstance(chunk,str):
                continue
            for clause in re.split(r'[。；;\n]',chunk):
                period=quarter_mentions(clause)
                if not period or not FORECAST_MARK.search(clause) or NON_BROKER.search(clause):
                    continue
                if re.search(r'年增|季增|上修|下修|調升|調降|由.+至|從.+到|區間|range|同比|環比',clause,re.I):
                    continue
                suffix=r'\s*%' if metric!='eps' else r'\s*(?:元|NTD|TWD)?'
                for m in re.finditer('(?:'+pattern+r')\s*(?:預估|預測|估計|estimate|forecast)?\s*(?:為|達|約|:|：|=|of|at)?\s*([+-]?\d+(?:\.\d+)?)'+suffix,clause,re.I):
                    v=number(m.group(1))
                    if v is not None:
                        yield period,v,'text:'+field

def compare_margin_metric(root, metric):
    from broker_eps_pipeline import saved_reports
    data=root/'data'
    forecasts={}
    audit={'candidates':0,'conflicting_report_quarters':0,'excluded_late':0,'matches':0}
    for report in saved_reports(data):
        rid=str(report.get('source_file_id') or report.get('id') or '')
        ticker=str(report.get('ticker') or '')
        broker=str(report.get('broker') or '')
        day=gm_valid_date(report.get('date'))
        if not rid or not TICKER.fullmatch(ticker) or not broker or not day:
            continue
        values={}
        for period,value,evidence in saved_metric_rows(report,metric):
            values.setdefault(period,{})
            existing=next((v for v in values[period] if abs(v-value)<=0.011),None)
            if existing is None:
                values[period][value]=evidence
        for period, estimates in values.items():
            conflict=len(estimates)>1
            audit['conflicting_report_quarters']+=int(conflict)
            for value,evidence in estimates.items():
                audit['candidates']+=1
                forecasts.setdefault((ticker,period),[]).append((rid,broker,day,value,report.get('source_url') or '',evidence,conflict))
    matches={}
    for source,key in (('quarterly_earnings.json','reports'),('quarterly_earnings_announcements_history.json','items')):
        for actual in load(data/source,{}).get(key,[]):
            ticker=str(actual.get('ticker') or '')
            period=str(actual.get('period') or '')
            day=valid_date(actual.get('publish_date'))
            value=number(actual.get(metric))
            if not day or value is None:
                continue
            for rid,broker,report_day,estimate,url,evidence,conflict in forecasts.get((ticker,period),[]):
                if report_day>day:
                    audit['excluded_late']+=1
                    continue
                matches[(ticker,period,day,value,rid,estimate)]=dict(ticker=ticker,name=actual.get('name') or '',period=period,announcement_date=day,actual_kind='quarterly',broker=broker,report_date=report_day,report_id=rid,source_url=url,actual_source=source,evidence=evidence,needs_review=conflict,difference_pp=round(value-estimate,2),**{'actual_'+metric:value,'forecast_'+metric:estimate})
    output={'version':2,'metric':metric,'unit':'%','items':[matches[k] for k in sorted(matches)]}
    audit['matches']=len(matches)
    dest=data/('broker_'+metric+'_comparisons.json')
    content=json.dumps(output,ensure_ascii=False,indent=2)+'\n'
    if not dest.exists() or dest.read_text(encoding='utf-8')!=content:
        dest.write_text(content,encoding='utf-8')
    print(metric+' audit:',json.dumps(audit,ensure_ascii=False))
    return output

def compare_gross_margin(root=ROOT):
    return compare_margin_metric(root,'gross_margin')

def compare_operating_margin(root=ROOT):
    return compare_margin_metric(root,'operating_margin')


if __name__ == '__main__':
    compare()
