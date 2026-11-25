"""端到端：内置合成数据集的勾稽关系、重开判定与快照保留。"""
import sys
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metric_governance import (  # noqa: E402
    Registry, WorkflowState, load_dataset, revenue_bridge, MemberEngine,
    category_growth,
)
from metric_governance.reopen import assess_report, load_snapshot, write_snapshot  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds = load_dataset(DATA)
        cls.reg = Registry(cls.ds, WorkflowState())

    def test_no_import_errors(self):
        errors = [i for i in self.ds.issues if i.level == "error"]
        self.assertEqual(errors, [])

    # ------------------------------------------------------- Q2 / R1
    def test_q2_headline_matches_published_12_4(self):
        b = revenue_bridge(self.reg, "2026-Q2")
        self.assertEqual(b.base_total, 1000.0)
        self.assertEqual(b.current_total, 1124.0)
        self.assertAlmostEqual(b.growth_rate, 12.4, places=6)

    def test_q2_bridge_components_and_additivity(self):
        b = revenue_bridge(self.reg, "2026-Q2")
        by = {c.code: round(c.amount) for c in b.components}
        self.assertEqual(by["comparable"], -66)
        self.assertEqual(by["portfolio_new"], 141)
        self.assertEqual(by["portfolio_discontinued"], -93)
        self.assertEqual(by["scope_new"], 142)
        self.assertAlmostEqual(sum(c.amount for c in b.components), b.delta)
        # 可比实体整体同比 -1.8%，与汇总 +12.4% 形成对照
        self.assertAlmostEqual(b.comparable_rate, -1.8, places=6)
        self.assertTrue(b.covered)

    # ------------------------------------------------------- Q3 / R3
    def test_q3_restated_comparable_flips_to_minus_4_3(self):
        b = revenue_bridge(self.reg, "2026-Q3")
        self.assertAlmostEqual(b.comparable_rate, -4.2574257, places=4)
        self.assertEqual(round(b.comparable_rate, 1), -4.3)
        self.assertIn("S0→S2", b.comparable_entities)
        self.assertIn("JD", b.comparable_entities)

    def test_q3_partial_xhs_excluded(self):
        b = revenue_bridge(self.reg, "2026-Q3")
        xhs = [g for g in b.gaps if g.entity == "XHS"]
        self.assertEqual(len(xhs), 1)
        self.assertEqual(xhs[0].kind, "partial")
        self.assertEqual(b.excluded_current, 18.0)

    def test_q3_open_conflict_cell_excluded(self):
        b = revenue_bridge(self.reg, "2026-Q3")
        open_keys = [c.key_text for c in b.conflicts if c.status == "open"]
        self.assertIn("revenue|2026-08|DY|P2", open_keys)
        self.assertFalse(b.covered)

    def test_publish_time_view_reproduces_4_3(self):
        reg0 = Registry(self.ds, WorkflowState(), as_of=date(2026, 10, 12))
        b = revenue_bridge(reg0, "2026-Q3", as_of=date(2026, 10, 12))
        self.assertEqual(round(b.comparable_rate, 1), 4.3)
        self.assertEqual(b.comparable_entities, ["S1", "TM"])
        self.assertTrue(any(g.entity == "JD" and g.kind == "missing"
                            for g in b.gaps))

    # ------------------------------------------------------- members R2
    def test_member_versions(self):
        eng = MemberEngine(self.ds)
        l1 = eng.growth("2026-Q2", "2025-Q2", "L1")
        l2 = eng.growth("2026-Q2", "2025-Q2", "L2")
        self.assertEqual((l1["base"]["persons"], l1["current"]["persons"]),
                         (37, 40))
        self.assertEqual(round(l1["growth_rate"], 1), 8.1)
        self.assertEqual((l2["base"]["persons"], l2["current"]["persons"]),
                         (38, 39))
        self.assertEqual(round(l2["growth_rate"], 1), 2.6)

    # ------------------------------------------------------- category R4
    def test_category_versions(self):
        old = category_growth(self.reg, "2026-Q3", "skincare",
                              classification_version="2")
        new = category_growth(self.reg, "2026-Q3", "skincare")
        self.assertEqual(round(old.growth_rate, 1), 14.8)
        self.assertEqual(round(new.growth_rate, 1), -4.1)

    # ------------------------------------------------------- reopen
    def test_reopen_decisions(self):
        by_id = {r.report: assess_report(self.reg, r) for r in self.ds.reports}
        self.assertFalse(by_id["R1"].should_reopen)
        for rid in ("R2", "R3", "R4"):
            self.assertTrue(by_id[rid].should_reopen, rid)
        self.assertEqual(by_id["R3"].headline_restated, "-4.3%")

    def test_completed_action_preserved_when_reopened(self):
        r2 = next(r for r in self.ds.reports if r.report == "R2")
        a = assess_report(self.reg, r2)
        a2 = next(x for x in a.actions if x["action"] == "A2")
        self.assertEqual(a2["state"], "complete")
        self.assertEqual(a2["completed_on"], "2026-07-28")
        self.assertTrue(a.snapshot_preserved)

    def test_snapshots_are_write_once(self):
        r1 = load_snapshot(self.ds, "R1")
        self.assertEqual(r1["headline_numeric"], 12.4)
        with tempfile.TemporaryDirectory() as td:
            p = write_snapshot(td, "X", {"ok": True})
            self.assertTrue(p.exists())
            with self.assertRaises(FileExistsError):
                write_snapshot(td, "X", {"ok": False})

    def test_decision_advice_levels(self):
        from metric_governance.dossier import advise_for_report
        by_id = {r.report: assess_report(self.reg, r) for r in self.ds.reports}
        # R1 数字稳定但增长由范围/组合驱动 => 有条件可用
        b = revenue_bridge(self.reg, "2026-Q2")
        a1 = advise_for_report(self.reg, by_id["R1"], b)
        self.assertEqual(a1.level, "conditional")
        self.assertTrue(a1.usable_for and a1.not_usable_for)
        # R2/R3/R4 => 阻断，不能用于下月资源决策
        for rid in ("R2", "R3", "R4"):
            self.assertEqual(
                advise_for_report(self.reg, by_id[rid]).level, "blocked", rid)


if __name__ == "__main__":
    unittest.main()
