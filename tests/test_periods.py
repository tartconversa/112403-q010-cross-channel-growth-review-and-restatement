"""期间模型测试。"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metric_governance.periods import Period  # noqa: E402


class PeriodTests(unittest.TestCase):
    def test_quarter_parse_and_bounds(self):
        q = Period.parse("2026-Q2")
        self.assertEqual((q.year, q.index, q.kind), (2026, 2, "quarter"))
        self.assertEqual(q.start, date(2026, 4, 1))
        self.assertEqual(q.end, date(2026, 6, 30))
        self.assertEqual([m.key for m in q.months()],
                         ["2026-04", "2026-05", "2026-06"])

    def test_prior_year(self):
        self.assertEqual(Period.parse("2026-Q3").prior_year().key, "2025-Q3")
        self.assertEqual(Period.parse("2026-06").prior_year().key, "2025-06")

    def test_month_parse(self):
        m = Period.parse("2026-2")
        self.assertEqual(m.key, "2026-02")
        self.assertEqual(m.end, date(2026, 2, 28))

    def test_bad_period(self):
        with self.assertRaises(ValueError):
            Period.parse("2026-Q9")


if __name__ == "__main__":
    unittest.main()
