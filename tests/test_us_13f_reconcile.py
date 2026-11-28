import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from us_13f_reconcile import reconcile,compare
def e(pos,form="13F-HR",typ=None,n=None,safe=True):
 return dict(positions=pos,form=form,amendment_type=typ,amendment_number=n,absence_safe=safe)
class TestReconcile(unittest.TestCase):
 def test_replace(self):
  state,status=reconcile([e({"A":[10,100]}),e({"A":[15,150]},"13F-HR/A","RESTATEMENT",1)])
  self.assertEqual(state["positions"]["A"],[15,150])
 def test_add(self):
  state,status=reconcile([e({"A":[10,100]}),e({"B":[15,150]},"13F-HR/A","NEW HOLDINGS",1)])
  self.assertEqual(len(state["positions"]),2)
 def test_overlap(self):
  self.assertIsNone(reconcile([e({"A":[10,100]}),e({"A":[15,150]},"13F-HR/A","NEW HOLDINGS",1)])[0])
 def test_unknown(self):
  self.assertIsNone(reconcile([e({}),e({},"13F-HR/A",None,1)])[0])
 def test_absence(self):
  a=reconcile([e({})])[0];b=reconcile([e({"A":[10,100]})])[0]
  self.assertEqual(compare(a,b,"A")[2],"newly_reported")
  self.assertEqual(compare(b,a,"A")[2],"no_longer_reported")
  self.assertIsNone(compare(reconcile([e({},safe=False)])[0],b,"A"))
if __name__=="__main__":unittest.main()
