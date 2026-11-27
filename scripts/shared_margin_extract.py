import re
from broker_eps_compare import number, parse_quarter, quarter_mentions

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
                explicit = FORECAST_MARK.search(axis) or re.search(r'(?:[EF])$',axis.strip(),re.I)
                broker_name = str(report.get('broker') or '').strip()
                named = bool(broker_name and broker_name.lower() in axis.lower())
                if not (explicit or named):
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
                if not period or not FORECAST_MARK.search(clause) or NON_BROKER.search(clause) or re.search(r'FY\d{2,4}|20\d{2}年(?:度|全年)|全年|annual',clause,re.I):
                    continue
                # Require forecast before the metric, not elsewhere after an actual.
                # Reject result commentary ('達', '創高', '優於預期') and comparisons.
                if re.search(r'優於|低於|符合|高於|不及|創新高|創高|公布|公告|達成|較預期|beat|miss|reported|results',clause,re.I):
                    continue
                if re.search(r'年增|季增|上修|下修|調升|調降|由.+至|從.+到|區間|range|同比|環比',clause,re.I):
                    continue
                # Parallel metric/value lists must be paired by position, never nearest label.
                both = re.search(r'(毛利率|營業利益率|營益率|營業利潤率)\s*(?:與|及|和|、)\s*(毛利率|營業利益率|營益率|營業利潤率)\s*(?:分別)?\s*(?:為|預估為|約)?\s*([+-]?\d+(?:\.\d+)?)\s*%\s*(?:與|及|和|、)\s*([+-]?\d+(?:\.\d+)?)\s*%',clause)
                if both:
                    for label,raw_value in ((both.group(1),both.group(3)),(both.group(2),both.group(4))):
                        if re.fullmatch(pattern,label,re.I):
                            yield period,float(raw_value),'text:'+field
                    continue
                # Unresolved multi-metric lists are not safe to interpret.
                if re.search(r'毛利率\s*(?:與|及|和|、)\s*(?:營業利益率|營益率|營業利潤率)|(?:營業利益率|營益率|營業利潤率)\s*(?:與|及|和|、)\s*毛利率',clause):
                    continue
                suffix=r'\s*%' if metric!='eps' else r'\s*(?:元|NTD|TWD)?'
                for m in re.finditer('(?:'+pattern+r')\s*(?:預估|預測|估計|estimate|forecast)?\s*(?:為|達|約|:|：|=|of|at)?\s*([+-]?\d+(?:\.\d+)?)'+suffix,clause,re.I):
                    prefix=clause[:m.start()]
                    if not (FORECAST_MARK.search(prefix) or FORECAST_MARK.search(m.group(0))):
                        continue
                    v=number(m.group(1))
                    if v is not None:
                        yield period,v,'text:'+field
