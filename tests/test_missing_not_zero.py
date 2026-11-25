"""关键不变量：缺失渠道/部分期间/空单元格绝不按零处理。"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metric_governance import Registry, WorkflowState, load_dataset, revenue_bridge  # noqa: E402
from metric_governance.quality import coverage_gaps, select_facts  # noqa: E402

HEADER = ["fact_id", "team", "metric", "period", "entity", "sku", "value",
          "basis", "submitted_on", "received_on", "batch", "note"]


def write(path: Path, name: str, header, rows):
    with (path / name).open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


class MissingNotZeroTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        write(self.dir, "coverage.csv",
              ["entity", "kind", "group", "state", "from", "to", "version"], [
                  {"entity": "E1", "kind": "store", "group": "east",
                   "state": "comparable", "from": "2024-01-01", "to": "", "version": "1"},
                  {"entity": "E2", "kind": "platform", "group": "online",
                   "state": "comparable", "from": "2024-01-01", "to": "", "version": "1"},
              ])
        rows = []
        fid = 0
        for m in ("2025-01", "2025-02", "2025-03"):
            fid += 1
            rows.append({"fact_id": f"B{fid}", "team": "t", "metric": "revenue",
                         "period": m, "entity": "E1", "sku": "P1", "value": 10,
                         "basis": "settled-sales", "submitted_on": "",
                         "received_on": "2025-04-05", "batch": "b", "note": ""})
            rows.append({"fact_id": f"E2B{fid}", "team": "t", "metric": "revenue",
                         "period": m, "entity": "E2", "sku": "P1", "value": 10,
                         "basis": "settled-sales", "submitted_on": "",
                         "received_on": "2025-04-05", "batch": "b", "note": ""})
        for m in ("2026-01", "2026-02", "2026-03"):
            fid += 1
            rows.append({"fact_id": f"C{fid}", "team": "t", "metric": "revenue",
                         "period": m, "entity": "E1", "sku": "P1", "value": 12,
                         "basis": "settled-sales", "submitted_on": "",
                         "received_on": "2026-04-05", "batch": "b", "note": ""})
        # 一行空值：来源未提供，不能变成 0
        rows.append({"fact_id": "EMPTY", "team": "t", "metric": "revenue",
                     "period": "2026-03", "entity": "E1", "sku": "P2", "value": "",
                     "basis": "", "submitted_on": "", "received_on": "",
                     "batch": "b", "note": "empty source cell"})
        write(self.dir, "facts.csv", HEADER, rows)

        self.ds = load_dataset(self.dir)
        self.reg = Registry(self.ds, WorkflowState())

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_cell_is_none(self):
        empty = [f for f in self.ds.facts if f.fact_id == "EMPTY"][0]
        self.assertIsNone(empty.value)

    def test_missing_channel_creates_gap(self):
        cells, _ = select_facts(self.ds.facts, self.reg)
        gaps = coverage_gaps(self.reg, "revenue", "2026-Q1", cells)
        entities = {g.entity: g.kind for g in gaps}
        self.assertEqual(entities.get("E2"), "missing")

    def test_missing_channel_not_treated_as_zero(self):
        b = revenue_bridge(self.reg, "2026-Q1")
        # E2 两侧剔除：周边界只有 E1，30 -> 36 = +20%
        self.assertEqual((b.base_total, b.current_total), (30.0, 36.0))
        self.assertAlmostEqual(b.growth_rate, 20.0)
        # E2 基期 30 仅作为剔除备忘，而不是 -30 的“下降贡献”
        self.assertEqual(b.excluded_base, 30.0)
        codes = {c.code for c in b.components}
        self.assertNotIn("scope_closed", codes)
        self.assertTrue(any(g.entity == "E2" for g in b.gaps))
        # 桥接分量精确可加
        self.assertAlmostEqual(sum(c.amount for c in b.components), b.delta)


if __name__ == "__main__":
    unittest.main()
