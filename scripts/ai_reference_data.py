"""Versioned reference snapshots and website-consistent adapters; no network writes."""
import hashlib,json,re
from contextvars import ContextVar
from pathlib import Path
from collections import defaultdict
from statistics import mean
CAPTURE=ContextVar('ai_reference_capture',default=None)
VOLATILE={'updated_at','generated_at','checked_at','fetched_on','ai_processed_at','telegram_attempted_at','telegram_sent_at','last_attempt_at'}

def canonical(value):
    if isinstance(value,dict):return {k:(str(v)[:10] if k=='observed_at' else canonical(v)) for k,v in sorted(value.items()) if k not in VOLATILE}
    if isinstance(value,list):return [canonical(v) for v in value]
    return value

def digest(value):return hashlib.sha256(json.dumps(canonical(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def record(path,value,exists):
    capture=CAPTURE.get()
    if capture is not None:capture[str(Path(path).resolve())]={'hash':digest(value),'exists':exists}

def reference_snapshot(data,cfg,files,now):
    root=data.parent.resolve();inventory={}
    for p,meta in sorted(files.items()):
        try:key=str(Path(p).relative_to(root))
        except ValueError:continue
        inventory[key]=meta
    config_path=root/'config/ai_portfolio.json'
    inventory['config/ai_portfolio.json']={'hash':digest(cfg),'exists':config_path.exists()}
    algorithms={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py') if p.name in {'ai_portfolio_engine.py','ai_allocation.py','ai_reference_data.py','update_ai_portfolio.py','ai_signal_model.py','ai_content_research.py','ai_evidence.py'}}
    for name,hash_value in algorithms.items():inventory['scripts/'+name]={'hash':hash_value,'exists':True}
    # Execution time is not a reference. Calendar date is: age/availability gates
    # can legitimately change when a new calendar day starts, even on a weekend.
    material={'files':inventory,'config':cfg,'algorithms':algorithms,'evaluation_date':now.date().isoformat()}
    return {'reference_hash':digest(material),'files':inventory,'evaluation_date':now.date().isoformat(),'algorithm_hashes':algorithms}

def merge_earnings(primary,recovered):
    merged={};nullable=('eps','gross_margin','prev_eps','prev_gross_margin')
    for row in list(recovered.get('reports',[]))+list(primary.get('reports',[])):
        key=(str(row.get('ticker')),row.get('period'));prev=merged.get(key,{})
        out={**prev,**row}
        for k in nullable:out[k]=row.get(k) if row.get(k) is not None else prev.get(k)
        merged[key]=out
    return sorted(merged.values(),key=lambda r:(str(r.get('ticker')),str(r.get('period')),str(r.get('publish_date'))))

def research_index(rows):
    """Use explicit per-company AI-extracted views, never guess company identity
    from generic industry prose or transfer a parent's company target to peers.
    """
    indexed=defaultdict(list)
    for r in sorted(rows,key=lambda r:(str(r.get('received_at','')),str(r.get('id','')))):
        parent=str(r.get('ticker') or '')
        views={str(v.get('ticker')):v for v in r.get('stock_views',[]) if isinstance(v,dict) and re.fullmatch(r'\d{4}',str(v.get('ticker','')))}
        if re.fullmatch(r'\d{4}',parent):indexed[parent].append({**r,**views.get(parent,{})})
        for t,v in sorted(views.items()):
            if t==parent:continue
            out={k:r.get(k) for k in ('id','broker','date','group_date','received_at','report_type','source_url','category','original_type','type','meeting_date')}
            out.update(v);out['ticker']=t
            out['summary']=v.get('summary') or v.get('evidence') or ''
            indexed[t].append(out)
    return indexed

def holder_values(holder,current,previous,number):
    """Full registered holdings history first; top rankings are only a fallback."""
    out={};hdate=holder.get('date');pdate=holder.get('previous_date')
    full=(current.get('date')==hdate and previous.get('date')==pdate and hdate and pdate)
    if full:
        for t,row in sorted(current.get('stocks',{}).items()):
            old=previous.get('stocks',{}).get(t)
            if not old:continue
            values={}
            for group in ('400','1000'):
                a,b=number(row.get(group+'_ratio')),number(old.get(group+'_ratio'))
                if a is not None and b is not None:values[group]={'ratio':a,'delta':a-b}
            if values:out[str(t)]=values
    # Don't throw away valid full-universe rows just because the page only ranks30.
    for market in ('twse','tpex'):
        for group in ('400','1000'):
            for row in holder.get(market,{}).get(group,[]):
                t=str(row.get('ticker'));delta=number(row.get('delta'));ratio=number(row.get('ratio'))
                if delta is not None:out.setdefault(t,{}).setdefault(group,{'ratio':ratio,'delta':delta})
    return out,('full_weekly_history' if full else 'ranked_fallback')
