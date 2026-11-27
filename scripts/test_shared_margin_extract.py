import unittest
from shared_margin_extract import saved_metric_rows
class ExtractionTest(unittest.TestCase):
    def test_paired_values(self):
        r={'key_points':['3Q26預估毛利率與營業利益率為48.5%與14.5%。']}
        self.assertEqual([x[:2] for x in saved_metric_rows(r,'gross_margin')],[('2026-Q3',48.5)])
        self.assertEqual([x[:2] for x in saved_metric_rows(r,'operating_margin')],[('2026-Q3',14.5)])
    def test_actual_column(self):
        r={'broker':'BofA','visualizations':[{'type':'table','title':'3Q26 季度業績與券商預估','headers':['指標','3Q26','券商預估'],'rows':[['毛利率','88.2%','85%']]}]}
        self.assertEqual([x[:2] for x in saved_metric_rows(r,'gross_margin')],[('2026-Q3',85)])
if __name__=='__main__':unittest.main()
