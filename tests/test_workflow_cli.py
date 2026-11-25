"""工作流覆盖层与 CLI 冒烟测试。"""
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from metric_governance.cli import main  # noqa: E402
from metric_governance import Registry, WorkflowState, load_dataset  # noqa: E402
from metric_governance.quality import select_facts  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SAMPLES = ROOT / "samples"


class WorkflowTests(unittest.TestCase):
    def test_confirm_and_resolve_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            state = WorkflowState.load(Path(td) / "state.json")
            reg = Registry(load_dataset(DATA), state)
            self.assertFalse(reg.is_confirmed("lineage", "P5:new-line:"))
            state.confirm("lineage", "P5:new-line:", "product-owner", "钱芳")
            self.assertTrue(reg.is_confirmed("lineage", "P5:new-line:"))

            _, conflicts = select_facts(reg.ds.facts, reg)
            dy = next(c for c in conflicts if "DY" in c.key_text)
            self.assertEqual(dy.status, "open")
            state.resolve_conflict(dy.key_text, chosen_value=26.0,
                                   person="孙敏")
            _, conflicts = select_facts(reg.ds.facts, reg)
            dy = next(c for c in conflicts if "DY" in c.key_text)
            self.assertEqual(dy.status, "resolved")
            # 覆盖层确实落盘，且能从文件重新加载（模拟下一次 CLI 进程）
            self.assertTrue((Path(td) / "state.json").exists())
            reloaded = WorkflowState.load(Path(td) / "state.json")
            self.assertEqual(len(reloaded.confirmations), 1)
            self.assertEqual(len(reloaded.resolutions), 1)
            reg2 = Registry(load_dataset(DATA), reloaded)
            self.assertTrue(reg2.is_confirmed("lineage", "P5:new-line:"))

    def test_reopen_case_and_followup_action(self):
        with tempfile.TemporaryDirectory() as td:
            state = WorkflowState.load(Path(td) / "state.json")
            case = state.open_reopen_case(
                "R3", ["x"], {"h": "4.3"}, {"h": "-4.3"}, owner="陈澈")
            self.assertEqual(case["status"], "reopened")
            self.assertTrue(any(a["action"] == "A-REOPEN-R3"
                                for a in state.extra_actions))
            rec = state.complete_action("A-REOPEN-R3", person="陈澈", note="done")
            self.assertEqual(rec["state"], "complete")


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_metrics_and_metric_dossier(self):
        with tempfile.TemporaryDirectory() as td:
            state = str(Path(td) / "s.json")
            code, out = self.run_cli(["--data", str(DATA), "--state", state, "metrics"])
            self.assertEqual(code, 0)
            self.assertIn("comparable-sales", out)
            code, out = self.run_cli(["--data", str(DATA), "--state", state,
                                      "metric", "revenue"])
            self.assertEqual(code, 0)
            for token in ("口径定义", "覆盖", "待处理", "12.4"):
                self.assertIn(token, out)

    def test_overview_and_reopen_cli(self):
        with tempfile.TemporaryDirectory() as td:
            state = str(Path(td) / "s.json")
            code, out = self.run_cli(["--data", str(DATA), "--state", state,
                                      "overview"])
            self.assertEqual(code, 0)
            self.assertIn("应重开", out)
            self.assertIn("按 0 处理", out)
            self.assertIn("覆盖部分期间", out)
            code, out = self.run_cli(["--data", str(DATA), "--state", state,
                                      "reopen", "--apply"])
            self.assertEqual(code, 0)
            saved = json.loads(Path(state).read_text(encoding="utf-8"))
            self.assertEqual({c["report"] for c in saved["reopen_cases"]},
                             {"R2", "R3", "R4"})

    def test_html_output(self):
        from metric_governance.render_html import render_dashboard
        from metric_governance.overview import build_overview
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "dash.html"
            code, text = self.run_cli([
                "--data", str(DATA), "--state", str(Path(td) / "s.json"),
                "html", "--out", str(out), "--metric-pages"])
            self.assertEqual(code, 0)
            html = out.read_text(encoding="utf-8")
            self.assertIn("同比桥接", html)
            self.assertIn("R3", html)
            self.assertTrue((Path(td) / "metrics" / "members.html").exists())
            # 视图模型可直接渲染且包含表格双视图
            ov = build_overview(Registry(load_dataset(DATA), WorkflowState()))
            self.assertIn("<table>", render_dashboard(ov))

    def test_samples_directory_still_supported(self):
        ds = load_dataset(SAMPLES)
        self.assertEqual(len(ds.reports), 3)
        reg = Registry(ds, WorkflowState())
        # 无事实数据时总览也必须能构建，不抛异常
        from metric_governance.overview import build_overview
        ov = build_overview(reg)
        self.assertEqual(len(ov.publications), 3)


class WebApiTests(unittest.TestCase):
    def test_http_routes(self):
        import threading
        from http.server import ThreadingHTTPServer
        from metric_governance.webapp import make_handler

        reg = Registry(load_dataset(DATA), WorkflowState())
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(reg))
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            with urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as r:
                self.assertEqual(json.loads(r.read())["ok"], True)
            with urlopen(f"http://127.0.0.1:{port}/api/pending", timeout=5) as r:
                pending = json.loads(r.read())
                self.assertTrue(any(p["kind"] == "conflict" for p in pending))
            with urlopen(f"http://127.0.0.1:{port}/metric/revenue", timeout=5) as r:
                self.assertIn("text/html", r.headers["Content-Type"])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
