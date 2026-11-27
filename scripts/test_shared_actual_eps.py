import unittest
from shared_actual_eps import explicit_quarter
class ActualTest(unittest.TestCase):
    def test_prior_year_column(self):
        self.assertEqual(explicit_quarter('單季 115年第3季 114年第3季 與去年同期增減% 營業收入 338 204 66% 每股盈餘(元) 2.33 1.45 61% 最近四季累計','2026-Q3'),2.33)
    def test_combined(self):
        self.assertEqual(explicit_quarter('最近一月 與去年 最近一季 與去年 科目 115年09月 同期增減% 115年第3季 同期增減% 最近四季累計 (合併核閱數) 每股盈餘 1.85 213.56% 4.60 513.33% 9.79 (元)','2026-Q3'),4.6)
    def test_negative(self):
        self.assertEqual(explicit_quarter('單季 115年第3季 114年第3季 每股盈餘(元) (0.41) (0.95) 56.84%','2026-Q3'),-0.41)
    def test_no_prior_header(self):
        self.assertIsNone(explicit_quarter('單季 114年第3季 每股盈餘 1.45','2026-Q3'))
if __name__=='__main__':unittest.main()
