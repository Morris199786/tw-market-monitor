#!/usr/bin/env python3
"""Publish only prediction-owned data using an isolated Git index."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import datetime as dt
import update_self_reports as collector
import self_report_forecast_export as exporter
import self_report_v17_settle_actuals as settlement

ROOT = collector.ROOT

def publish(state_only=False):
    paths = ['data/self_report_digest_sent.json'] if state_only else [
        'data/self_reports_history.json', 'data/self_reports.json',
        'data/self_report_forecast.json', 'data/self_report_v17_forecast_ledger.json',
        'data/self_report_v17_actuals_verified.json']
    original = {p: exporter.load(ROOT/p, {}) for p in paths}
    for attempt in range(8):
        collector.delivery_git(['fetch', '--quiet', 'origin', 'main'])
        base = collector.delivery_git(['rev-parse', 'FETCH_HEAD']).stdout.strip()
        data = dict(original)
        if state_only:
            path = paths[0]
            remote = collector.delivery_json_at(base, path)
            data[path] = {'sent': {**remote.get('sent', {}), **original[path].get('sent', {})}}
        else:
            # Do not silently overwrite another prediction producer.
            for path in paths[2:]:
                remote = collector.delivery_json_at(base, path)
                checked_out = collector.delivery_json_at('HEAD', path)
                if remote != checked_out and remote != original[path]:
                    raise RuntimeError('Concurrent forecast change; rerun against latest main')
            hp, sp = paths[:2]
            remote = collector.delivery_json_at(base, hp)
            local = original[hp]
            rows = {}
            for item in local.get('items', []) + remote.get('items', []):
                key = collector.identity(item)
                rows[key] = collector.merge_item(rows.get(key, {}), item)
            for row in rows.values():
                metrics = collector.extract_metrics((row.get('subject') or '')+' '+(row.get('detail') or ''))
                if metrics.get('monthly_eps') is not None:
                    row.update(metrics)
            items = sorted(rows.values(), key=lambda x: (x.get('publish_date',''), x.get('publish_time',''), x.get('ticker','')), reverse=True)
            failed = [collector.diagnostic_entry(x) for x in items if not collector.valid_eps_item(x)]
            stamp = max(local.get('updated_at',''), remote.get('updated_at',''))
            history = dict(local, items=items, parse_failed=failed, updated_at=stamp,
                           parsed_count=sum(collector.valid_eps_item(x) for x in items),
                           parse_failed_count=len(failed), candidate_count=len(items))
            site = dict(original[sp], items=[x for x in items if collector.valid_eps_item(x)], updated_at=stamp)
            site['diagnostics'] = {**site.get('diagnostics', {}), 'parse_failed': failed,
                                   'parse_failed_count': len(failed), 'parsed_count': len(site['items'])}
            exporter.save(ROOT/hp, history)
            exporter.save(ROOT/sp, site)
            ledger = original['data/self_report_v17_forecast_ledger.json']
            verified = settlement.settle(history, exporter.load(ROOT/'data/master.json'), ledger,
                original['data/self_report_v17_actuals_verified.json'], dt.datetime.now(settlement.TZ))
            exporter.save(ROOT/'data/self_report_v17_actuals_verified.json', verified)
            exporter.run(SimpleNamespace(
                ledger=ROOT/'data/self_report_v17_forecast_ledger.json',
                predictions=ROOT/'self_report_live/predictions.json', target_date='',
                verified_actuals=ROOT/'data/self_report_v17_actuals_verified.json',
                output=ROOT/'data/self_report_forecast.json'))
            data = {p: exporter.load(ROOT/p) for p in paths}
        files = {p: json.dumps(v, ensure_ascii=False, indent=2)+'\n' for p,v in data.items()}
        if collector.delivery_commit(base, files, 'main', 'data: self report forecast and website settlement'):
            print('PUBLISHED_TO_MAIN', len(files), 'files')
            return
    raise RuntimeError('Publish retries exhausted')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--state-only', action='store_true')
    publish(p.parse_args().state_only)
