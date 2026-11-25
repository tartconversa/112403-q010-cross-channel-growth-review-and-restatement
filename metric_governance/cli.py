"""命令行入口：总览、指标档案、重开判定、待办、确认与冲突裁决、HTML 产出。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .dossier import build_dossier, pending_items
from .io_csv import load_dataset
from .overview import build_overview
from .registry import Registry
from .render_text import render_dossier, render_overview, pct_text
from .workflow import WorkflowState

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / "data"
DEFAULT_STATE = REPO_ROOT / "out" / "workflow_state.json"


def build_registry(args: argparse.Namespace) -> Registry:
    data_dir = Path(args.data) if args.data else DEFAULT_DATA
    ds = load_dataset(data_dir)
    state_path = Path(args.state) if args.state else DEFAULT_STATE
    state = WorkflowState.load(state_path if state_path.exists() else state_path)
    return Registry(ds, state)


# ---------------------------------------------------------------- commands

def cmd_overview(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    ov = build_overview(reg)
    print(render_overview(ov))
    return 0


def cmd_metric(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    names = reg.metrics()
    name = args.name
    if name not in names:
        # 宽松匹配
        alias = {n.replace("-", "").lower(): n for n in names}
        name = alias.get(name.replace("-", "").lower(), name)
    dossier = build_dossier(reg, name)
    print(render_dossier(dossier))
    return 0


def cmd_metrics(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    print("已登记指标：")
    for m in reg.metrics():
        d = reg.definition(m)
        print(f"  - {m:<18} 最新定义 {d.version} / {d.formula} / 责任人 {d.owner}")
    return 0


def cmd_reopen(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    from .reopen import assess_report
    for rep in reg.ds.reports:
        a = assess_report(reg, rep)
        flag = "应重开" if a.should_reopen else a.severity
        print(f"{rep.report} [{flag}] {rep.metric} {rep.period} "
              f"{a.headline_original} -> {a.headline_restated or '—'}")
        for r in a.reasons:
            print(f"    · {r}")
        if args.apply and a.should_reopen:
            reg.state.open_reopen_case(
                rep.report, a.reasons,
                {"headline": a.headline_original},
                {"headline": a.headline_restated, "delta_pp": a.delta_pp},
                owner=rep.owner)
            print(f"    => 已登记重开个案并生成跟进动作（原快照与行动记录未改动）")
    if args.apply:
        print(f"工作流状态写入 {reg.state.path}")
    return 0


def cmd_actions(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    items = pending_items(reg) if args.pending else None
    if args.pending:
        for p in items:
            print(f"[{p.kind}] {p.ref} | {p.title} | {p.owner} | {p.state}")
        return 0
    for a in reg.ds.actions:
        print(f"{a.action} [{a.state}] {a.report} {a.title} "
              f"owner={a.owner} completed={a.completed_on or ''}")
    for a in reg.state.extra_actions:
        print(f"{a['action']} [{a['state']}] {a['report']} {a['title']} (workflow)")
    return 0


def cmd_conflicts(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    from .quality import select_facts
    _, conflicts = select_facts(reg.ds.facts, reg)
    if not conflicts:
        print("未发现事实冲突。")
    for c in conflicts:
        print(f"[{c.status}] {c.key_text} 候选值={c.distinct_values}"
              + (f" 裁决={c.resolution}" if c.resolution else " 待治理裁决"))
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    from .quality import select_facts, coverage_gaps
    period = args.period or "2026-Q3"
    cells, _ = select_facts(reg.ds.facts, reg)
    gaps = coverage_gaps(reg, args.metric or "revenue", period, cells)
    if not gaps:
        print(f"{period} 覆盖完整，无缺口。")
    for g in gaps:
        print(f"[{g.kind}] {g.entity} 应报 {g.expected_months} "
              f"实有 {g.observed_months} —— {g.reason}")
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    rec = reg.state.confirm(
        args.subject_type, args.subject_key, args.role, args.person,
        decision=args.decision, note=args.note or "")
    print("已记录确认决定：")
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    print(f"状态文件: {reg.state.path}")
    return 0


def cmd_resolve_conflict(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    value = float(args.value) if args.value not in (None, "") else None
    rec = reg.state.resolve_conflict(
        args.key, chosen_fact_id=args.fact_id or "", chosen_value=value,
        person=args.person or "", note=args.note or "")
    print("已记录冲突裁决：")
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    return 0


def cmd_complete_action(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    rec = reg.state.complete_action(args.action, person=args.person or "",
                                    note=args.note or "")
    if not rec:
        # 种子行动不能被覆盖修改：完成记录应通过工作流动作登记
        print(f"行动 {args.action} 是 CSV 台账中的已发布记录，不能就地改写。")
        print("如确需登记新的完成证据，请在行动台账 CSV 中按治理流程更新，"
              "或完成 workflow 生成的 A-REOPEN-* 动作。")
        return 1
    print("已完成工作流动态：", json.dumps(rec, ensure_ascii=False))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    ds = reg.ds
    print(f"导入完成: 定义 {len(ds.definitions)}，期间口径 {len(ds.calibers)}，"
          f"事实 {len(ds.facts)}，范围行 {len(ds.coverage)}，"
          f"谱系 {len(ds.lineage)}，会员映射 {len(ds.member_links)}，"
          f"发布 {len(ds.reports)}，快照 {len(list(Path(ds.snapshots_dir).glob('*.json'))) if ds.snapshots_dir else 0}")
    errors = [i for i in ds.issues if i.level == "error"]
    for i in ds.issues:
        print(f"  [{i.level}] {i.code}: {i.message}")
    return 1 if errors else 0


def cmd_confirmations(args: argparse.Namespace) -> int:
    reg = build_registry(args)
    print("角色确认记录（CSV 种子 + 工作流覆盖层最新决定）：")
    seen: set[tuple[str, str]] = set()
    for c in reg.ds.confirmations:
        key = (c.subject_type, c.subject_key)
        seen.add(key)
        print(f"  {c.on} [{c.role}] {c.person} {c.decision} "
              f"{c.subject_type}:{c.subject_key} {('— ' + c.note) if c.note else ''}")
    for c in reg.state.confirmations:
        print(f"  {c.get('on')} [{c.get('role')}] {c.get('person')} "
              f"{c.get('decision')} {c.get('subject_type')}:{c.get('subject_key')} (workflow)")
    return 0


def cmd_html(args: argparse.Namespace) -> int:
    from .render_html import render_dashboard
    reg = build_registry(args)
    ov = build_overview(reg)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_dashboard(ov), encoding="utf-8")
    print(f"HTML 仪表盘已生成: {out}")
    if args.metric_pages:
        mdir = out.parent / "metrics"
        mdir.mkdir(exist_ok=True)
        from .render_html import render_metric_page
        for m in reg.metrics():
            html = render_metric_page(build_dossier(reg, m))
            (mdir / f"{m}.html").write_text(html, encoding="utf-8")
        print(f"指标档案页已生成于: {mdir}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .webapp import serve
    reg = build_registry(args)
    serve(reg, host=args.host, port=args.port)
    return 0


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python3 -m metric_governance",
        description="经营指标口径治理、同比桥接与管理层结论重开系统")
    p.add_argument("--data", help="数据目录（默认内置 data/，也可指向 samples/）")
    p.add_argument("--state", help="工作流 JSON 状态路径（默认 out/workflow_state.json）")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("overview", help="输出经营治理总览（默认命令）")
    sub.add_parser("demo", help="同 overview")

    pm = sub.add_parser("metric", help="查询单项指标档案")
    pm.add_argument("name")
    pm.set_defaults(func=cmd_metric)

    sub.add_parser("metrics", help="列出全部指标定义").set_defaults(func=cmd_metrics)

    pr = sub.add_parser("reopen", help="重开判定；--apply 登记重开个案")
    pr.add_argument("--apply", action="store_true")
    pr.set_defaults(func=cmd_reopen)

    pa = sub.add_parser("actions", help="行动台账；--pending 只看当前待处理")
    pa.add_argument("--pending", action="store_true")
    pa.set_defaults(func=cmd_actions)

    sub.add_parser("conflicts", help="事实冲突与裁决状态").set_defaults(func=cmd_conflicts)

    sub.add_parser("confirmations", help="查看三角色确认记录").set_defaults(
        func=cmd_confirmations)

    pc = sub.add_parser("coverage", help="覆盖缺口检查")
    pc.add_argument("--period")
    pc.add_argument("--metric")
    pc.set_defaults(func=cmd_coverage)

    pcf = sub.add_parser("confirm", help="登记角色确认决定")
    pcf.add_argument("--subject-type", required=True)
    pcf.add_argument("--subject-key", required=True)
    pcf.add_argument("--role", required=True,
                     choices=["governance", "channel-owner", "product-owner"])
    pcf.add_argument("--person", required=True)
    pcf.add_argument("--decision", default="confirmed",
                     choices=["confirmed", "changes-requested", "rejected"])
    pcf.add_argument("--note")
    pcf.set_defaults(func=cmd_confirm)

    prc = sub.add_parser("resolve-conflict", help="裁决事实冲突")
    prc.add_argument("--key", required=True, help="metric|period|entity|sku")
    prc.add_argument("--fact-id")
    prc.add_argument("--value")
    prc.add_argument("--person")
    prc.add_argument("--note")
    prc.set_defaults(func=cmd_resolve_conflict)

    pac = sub.add_parser("complete-action", help="完成 workflow 动态生成的行动")
    pac.add_argument("--action", required=True)
    pac.add_argument("--person")
    pac.add_argument("--note")
    pac.set_defaults(func=cmd_complete_action)

    sub.add_parser("check", help="仅导入并校验数据").set_defaults(func=cmd_check)

    ph = sub.add_parser("html", help="生成 HTML 仪表盘")
    ph.add_argument("--out", default=str(REPO_ROOT / "out" / "dashboard.html"))
    ph.add_argument("--metric-pages", action="store_true")
    ph.set_defaults(func=cmd_html)

    ps = sub.add_parser("serve", help="启动只读查询 Web 界面")
    ps.add_argument("--host", default="127.0.0.1")
    ps.add_argument("--port", type=int, default=8765)
    ps.set_defaults(func=cmd_serve)

    p.set_defaults(func=cmd_overview)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"找不到文件: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
