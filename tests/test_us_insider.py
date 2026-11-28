import unittest
from scripts.update_us_insider import filing_rows,clean,calc,classify
XML=b"""<ownershipDocument><documentType>4</documentType><issuer><issuerCik>123</issuerCik></issuer><reportingOwner><reportingOwnerId><rptOwnerCik>456</rptOwnerCik><rptOwnerName>Test Owner</rptOwnerName></reportingOwnerId><reportingOwnerRelationship><isDirector>1</isDirector></reportingOwnerRelationship></reportingOwner><nonDerivativeTable><nonDerivativeTransaction><securityTitle><value>Common Stock</value></securityTitle><transactionDate><value>2026-01-02</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding><transactionAmounts><transactionShares><value>10000</value></transactionShares><transactionPricePerShare><value>50</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts><postTransactionAmounts><sharesOwnedFollowingTransaction><value>20000</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
class TestInsider(unittest.TestCase):
 def rows(self,xml=XML):return filing_rows(xml,"TEST","123","2026-01-05","https://www.sec.gov/test")
 def test_purchase(self):
  r=self.rows()[0];self.assertEqual(r["amount"],500000);self.assertEqual(r["role"],"董事")
 def test_sale(self):
  r=self.rows(XML.replace(b">P<",b">S<").replace(b">A<",b">D<"))[0]
  self.assertEqual(r["side"],"sell");self.assertFalse(classify(r)["research_eligible"])
 def test_classification_evidence(self):
  r=self.rows()[0]
  self.assertEqual(classify(r)["purchase_class"],"discretionary_candidate")
  r["footnotes"]=["Purchased in the open market"]
  self.assertEqual(classify(r)["purchase_class"],"confirmed_market")
  r["footnotes"]=["Pursuant to a Rule 10b5-1 trading plan"]
  self.assertEqual(classify(r)["purchase_class"],"scheduled_plan")
  r["footnotes"]=[];r["plan_10b5"]=True
  self.assertEqual(classify(r)["purchase_class"],"plan_uncertain")
 def test_award_excluded(self):self.assertEqual(self.rows(XML.replace(b">P<",b">A<")),[])
 def test_duplicate(self):
  r=self.rows();self.assertEqual(len(clean(r+r)[0]),1)
 def test_amendment_quarantine(self):
  r=self.rows()+self.rows(XML.replace(b">4<",b">4/A<"));self.assertEqual(len(clean(r)[0]),0)
 def test_backtest_public_date(self):
  p={"TEST":[{"date":"2026-01-05","open":1,"close":1}]+[{"date":f"2026-01-{d:02d}","open":100,"close":110} for d in range(6,11)]}
  r=calc(self.rows(),p)[0];self.assertEqual(r["n"],1);self.assertAlmostEqual(r["mean"],10)
  self.assertEqual(calc(self.rows(),p)[1]["n"],0)
if __name__=="__main__":unittest.main()
