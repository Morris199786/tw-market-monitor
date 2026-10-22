import json
import tempfile
import unittest
from pathlib import Path
from repair_verified_broker_eps import repair,CASES
from broker_eps_selective_retry import select

class TestEPSFix(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'data').mkdir()
        reports=[{'id':rid,'ticker':ticker,'broker':broker,'date':date} for rid,(ticker,broker,date,_) in CASES.items()]
        (self.root/'data/reports.json').write_text(json.dumps({'items':reports}))
        rid=list(CASES)[1]
        self.existing=[{'report_id':rid,'ticker':'3406','period':'2026-Q4','eps':11.76},
                       {'report_id':'other','ticker':'9999','period':'2026-Q3','eps':1.23}]
        (self.root/'data/broker_eps_forecasts.json').write_text(json.dumps({'items':self.existing}))
        (self.root/'data/broker_eps_processed.json').write_text(json.dumps({'reports':{rid:{'status':'processed','accepted_forecasts':0} for rid in CASES}}))
    def tearDown(self):self.tmp.cleanup()
    def test_correct_all_and_preserve_unrelated(self):
        repair(self.root)
        a=json.loads((self.root/'data/broker_eps_forecasts.json').read_text())['items']
        for rid,(_,_,_,quarters) in CASES.items():
            self.assertEqual({x['period']:x['eps'] for x in a if x['report_id']==rid},quarters)
        self.assertEqual([x for x in a if x['report_id']=='other'],self.existing[1:])
        self.assertEqual(len(a),16) # 15 corrected + 1 unrelated
    def test_idempotent(self):
        repair(self.root);p=self.root/'data/broker_eps_forecasts.json';a=p.read_bytes();repair(self.root);self.assertEqual(p.read_bytes(),a)
    def test_reject_identity_mismatch(self):
        p=self.root/'data/reports.json';j=json.loads(p.read_text());j['items'][0]['broker']='wrong';p.write_text(json.dumps(j))
        with self.assertRaises(ValueError):repair(self.root)
    def test_do_not_reparse_completed_even_if_selected(self):
        rid=list(CASES)[0]
        (self.root/'data/broker_eps_new_reports.json').write_text(json.dumps({'items':[{'id':rid},{'id':'new'}]}))
        self.assertEqual([x['id'] for x in select(self.root)],['new'])
        self.assertEqual((self.root/'data/broker_eps_new_count.txt').read_text().strip(),'1')

if __name__=='__main__':unittest.main()
