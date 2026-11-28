import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from us_buyback_verify import verified
class TestBuyback(unittest.TestCase):
 def doc(self,p):
  return dict(form="10-Q",period="2026-09-26",filed="2026-10-30",url="https://www.sec.gov/example",passages=[p],tables=[])
 def test_zero(self):
  p="We have an ongoing authorization to repurchase shares of our common stock. No shares were repurchased during the quarter ended September 26, 2026."
  self.assertEqual(verified("INTC",[self.doc(p)])["explicit_zero"][0]["value"],0)
 def test_false_positives(self):
  for p in ["Our subsidiary repurchased shares of its common stock.","We repurchased convertible senior notes.","Shares of our common stock were withheld for employee tax withholding.","We repurchased preferred stock under our stock repurchase program."]:
   v=verified("X",[self.doc(p)])
   self.assertFalse(v["common_candidates"]);self.assertEqual(v["rejected_passages"],1)
 def test_wrong_period(self):
  p="We did not repurchase any shares of our common stock during the quarter ended June 27, 2026."
  self.assertFalse(verified("X",[self.doc(p)])["explicit_zero"])
if __name__=="__main__":unittest.main()
