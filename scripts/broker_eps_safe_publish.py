#!/usr/bin/env python3
"""Local, zero-API publication. Refuse first run until baseline is sealed.
Run `python scripts/broker_eps_pipeline.py seal` ONCE on baseline before enabling.
"""
import json
from pathlib import Path
from broker_eps_pipeline import publish_new
from broker_eps_compare import compare
ROOT = Path(__file__).resolve().parents[1]

def main():
    marker=ROOT/'data/broker_eps_baseline_sealed.json'
    if not marker.exists() or not json.loads(marker.read_text(encoding='utf-8')).get('sealed'):
        raise SystemExit('STOP: baseline not sealed; no API called')
    ledger=ROOT/'data/broker_eps_processed.json'
    if not ledger.exists():
        raise SystemExit('STOP: missing processed ledger; seal historical reports first; no API called')
    data=json.loads(ledger.read_text(encoding='utf-8'))
    if not isinstance(data.get('reports'),dict) or not data['reports']:
        raise SystemExit('STOP: empty ledger; seal historical reports first; no API called')
    publish_new()
    compare()

if __name__=='__main__': main()
