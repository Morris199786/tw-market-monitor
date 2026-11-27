import unittest
from shared_actual_eps import explicit_quarter, select_disclosure
class ActualTest(unittest.TestCase):
    def test_prior_year_column(self):
        self.assertEqual(explicit_quarter('單季 115年第3季 114年第3季 與去年同期增減% 營業收入 338 204 66% 每股盈餘(元) 2.33 1.45 61% 最近四季累計','2026-Q3'),2.33)
    def test_combined(self):
        self.assertEqual(explicit_quarter('最近一月 與去年 最近一季 與去年 科目 115年09月 同期增減% 115年第3季 同期增減% 最近四季累計 (合併核閱數) 每股盈餘 1.85 213.56% 4.60 513.33% 9.79 (元)','2026-Q3'),4.6)
    def test_negative(self):
        self.assertEqual(explicit_quarter('單季 115年第3季 114年第3季 每股盈餘(元) (0.41) (0.95) 56.84%','2026-Q3'),-0.41)
    def test_negative_without_unit(self):
        self.assertEqual(explicit_quarter('單季 115年第3季 114年第3季 每股盈餘 (0.41) (0.95) 56.84%','2026-Q3'),-0.41)
    def test_standalone(self):
        self.assertEqual(explicit_quarter('最近一季 科目 115年第二季 與去年同期增減(%) (IFRS合併核閱數) 每股盈餘(元) 1.59 37.1% 科目 114年第三季至115年第二季','2026-Q2'),1.59)
    def test_no_percent(self):
        self.assertEqual(explicit_quarter('最近一季 與去年同期增減% 115年第3季 (核閱數) 每股盈餘 0.43 177.94 1.56 164.41 1.22 (元)','2026-Q3'),1.56)
    def test_missing_yoy(self):
        self.assertEqual(explicit_quarter('最近一季 與去年同期增減% 115年第3季 (查核數) 每股盈餘(虧損) -0.52 -1.24 -3.51 (元)','2026-Q3'),-1.24)
    def test_correction(self):
        rows=[dict(date='2026-10-14',time='15:57:07',value=2.53),dict(date='2026-10-14',time='16:37:02',value=1.59,correction=True)]
        self.assertEqual(select_disclosure(rows),rows[1:])
    def test_cumulative_only(self):
        self.assertIsNone(explicit_quarter('本公司115年前3季自結合併損益資訊 稅後EPS 4.10 元','2026-Q3'))
    def test_no_prior_header(self):
        self.assertIsNone(explicit_quarter('單季 114年第3季 每股盈餘 1.45','2026-Q3'))
if __name__=='__main__':unittest.main()
