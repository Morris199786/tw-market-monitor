#!/usr/bin/env python3
"""Idempotently wire structured EPS parsing into the existing offline parser."""
from pathlib import Path
p=Path(__file__).with_name('test_broker_eps_pdf.py')
s=p.read_text(encoding='utf-8')
needle='                    safe,review=reconcile_results(safe,coords,review)'
replacement='''                    # Multi-row year / quarter / broker subcolumn tables.
                    from broker_eps_structured import parse_layout
                    structured,structured_review=parse_layout(proc.stdout,report.get('date'))
                    coords.extend(structured)
                    review.extend(structured_review)
                    safe,review=reconcile_results(safe,coords,review)'''
if replacement in s:print('Structured parser already installed')
elif needle in s:
 p.write_text(s.replace(needle,replacement,1),encoding='utf-8');print('Structured parser installed')
else:raise SystemExit('Parser integration anchor changed; refusing silent installation')
