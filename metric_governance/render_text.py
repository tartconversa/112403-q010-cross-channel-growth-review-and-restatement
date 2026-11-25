"""命令行中文文本报告渲染。"""
from __future__ import annotations

from .dossier import MetricDossier
from .overview import Overview

LEVEL_ICON = {"ready": "✅", "conditional": "⚠️", "blocked": "⛔"}
SEV_ICON = {"reopen": "🔴", "watch": "🟠", "stable": "🟢"}
PENDING_ICON = {"action": "📌", "conflict": "⚡", "confirmation": "🔎",
                "coverage": "🧩", "reopen": "🔁"}
GAP_KIND_CN = {"missing": "缺失", "partial": "部分期间"}


def pct_text(x, signed: bool = True, dash: str = "—") -> str:
    if x is None:
        return dash
    if signed:
        return f"{x:+.1f}%"
    return f"{x:.1f}%"


def num(x: float) -> str:
    if abs(x - round(x)) < 1e-6:
        return f"{x:,.0f}"
    return f"{x:,.1f}"


def _bar(value: float, scale: float, width: int = 24) -> str:
    n = int(round(min(abs(value) / scale, 1.0) * width)) if scale else 0
    if value >= 0:
        return "█" * n
    return "▓" * n


def render_overview(ov: Overview) -> str:
    L: list[str] = []
    w = L.append
    w("=" * 78)
    w("全域经营指标治理 · 同比桥接与管理层结论重述总览")
    w(f"数据目录: {ov.data_dir}    生成日期: {ov.generated_on}")
    w("=" * 78)

    if ov.issues:
        w("\n[导入问题]")
        for i in ov.issues:
            w(f"  · [{i['level']}] {i['message']}")

    # -------------------------------------------------- 发布结论与决策
    w("\n一、已发布管理结论：是否重开 / 能否用于下月资源决策")
    w("-" * 78)
    for p in ov.publications:
        a, adv = p["assessment"], p["advice"]
        w(f"\n{p['report']} · {p['metric']} {p['period']}  "
          f"发布值 {p['value']}（定义 {p['definition']}，{p['published_on']}）")
        w(f"  结论原文: {p['conclusion']}")
        icon = SEV_ICON.get(a["severity"], "")
        restated = a["headline_restated"] or "无法重述"
        w(f"  {icon} 重开判定: {'应重开' if a['should_reopen'] else a['severity']}"
          f" | 原发布 {a['headline_original']} -> 当前口径 {restated}"
          + (f" | 差异 {a['delta_pp']:+.1f}pp" if a["delta_pp"] is not None else ""))
        for r in a["reasons"]:
            w(f"      - {r}")
        w(f"  {LEVEL_ICON.get(adv['level'], '')} 决策可用性: {adv['title']}")
        for g in adv["guidance"]:
            w(f"      · {g}")
        if adv["usable_for"]:
            w("      可用于: " + "；".join(adv["usable_for"]))
        if adv["not_usable_for"]:
            w("      不可用于: " + "；".join(adv["not_usable_for"]))
        acts = a["actions"]
        if acts:
            w("      关联行动: " + "，".join(
                f"{x['action']}[{x['state']}"
                + (f"/{x['completed_on']} 完成记录保留" if x.get("completed_on") else "")
                + "]" for x in acts))

    # -------------------------------------------------- Q2 桥
    w("\n\n二、总体同比如何构成（金额单位以指标登记单位为准，示例为万元）")
    for key, title in [
        ("2026-Q2", "2026-Q2 vs 2025-Q2（R1 发布期，数据完整）"),
        ("2026-Q3-current", "2026-Q3 vs 2025-Q3（当前全部已导入数据）"),
        ("2026-Q3-publish-view", "2026-Q3 发布时点视图（仅 2026-10-12 前收到的数据）"),
    ]:
        b = ov.bridges[key]
        w("\n" + "-" * 78)
        w(f"【{title}】")
        w(f"  周边界内基期 {num(b['base_total'])}  本期 {num(b['current_total'])}"
          f"  总变动 {num(b['delta'])}（{pct_text(b['growth_rate'])}）")
        scale = max((abs(c["amount"]) for c in b["components"]), default=1.0)
        for c in b["components"]:
            w(f"    {c['label'][:34]:<36} {c['amount']:>+8.1f}  {_bar(c['amount'], scale)}")
        w(f"  其中可比实体 {', '.join(b['comparable_entities']) or '无'}")
        w(f"  可比口径同比: {pct_text(b['comparable_rate'], signed=False)}"
          f"（基 {num(b['comparable_base'])} / 本 {num(b['comparable_current'])}）")
        if b["scope_new_entities"]:
            w(f"  范围新增主体: {', '.join(b['scope_new_entities'])}（其贡献属于经营范围扩大）")
        if b["scope_closed_entities"]:
            w(f"  范围收缩主体: {', '.join(b['scope_closed_entities'])}")
        for g in b["gaps"]:
            kind_cn = GAP_KIND_CN.get(g["kind"], g["kind"])
            w(f"  🧩 覆盖{kind_cn}: {g['entity']} 应报 {len(g['expected_months'])} 个月、"
              f"实有 {g['observed_months'] or '无'} —— {g['reason']}")
        for ck in b["open_conflicts"]:
            w(f"  ⚡ 未裁决冲突: {ck}（冲突单元格未计入）")
        if b.get("excluded_base") or b.get("excluded_current"):
            w(f"  调节: 缺口主体基期金额 {num(b['excluded_base'])}、"
              f"本期金额 {num(b['excluded_current'])} 已移出桥接，绝未按 0 处理")

    # -------------------------------------------------- 月度
    w("\n  月度收入与覆盖标记（缺失/部分主体不补零）：")
    w(f"    {'月份':<9}{'去年同月':<10}{'基期':>8}{'本期':>9}{'同比':>9}  覆盖/冲突标记")
    for m in ov.monthly:
        flags = "，".join(m["coverage_flags"]
                          + [f"冲突 {c.split('|')[2]}/{c.split('|')[3]}"
                             for c in m["open_conflicts"]])
        w(f"    {m['month']:<9}{m['prior_month']:<10}{num(m['base']):>8}"
          f"{num(m['current']):>9}{pct_text(m['yoy']):>9}  {flags}")

    # -------------------------------------------------- 会员
    w("\n\n三、会员身份版本影响（R2）")
    w("-" * 78)
    for ver in ("L1", "L2"):
        v = ov.member_views[ver]
        w(f"  {ver}: 基期去重人数 {v['base']['persons']} -> "
          f"本期 {v['current']['persons']}，同比 {pct_text(v['growth_rate'])}")

    # -------------------------------------------------- 品类
    w("\n四、商品分类版本影响（R4：skincare）")
    w("-" * 78)
    for key, label in [("published_v2", "发布时 v2 口径"),
                       ("restated_v3", "当前 v3 追溯重述")]:
        c = ov.category_views[key]
        w(f"  {label}: 基期 {num(c['base_amount'])} / 本期 {num(c['current_amount'])}"
          f" / 同比 {pct_text(c['growth_rate'], signed=False)}")

    # -------------------------------------------------- 待办
    w("\n五、当前待处理动作（行动 / 冲突 / 确认 / 覆盖 / 重开）")
    w("-" * 78)
    if not ov.pending:
        w("  无待处理事项。")
    for p in ov.pending:
        icon = PENDING_ICON.get(p["kind"], "•")
        w(f"  {icon} [{p['kind']}] {p['ref']} | {p['title']} | "
          f"责任人 {p['owner'] or '未指定'} | 状态 {p['state']}")
        if p.get("detail"):
            w(f"       {p['detail']}")
    w("\n" + "=" * 78)
    w("提示: python3 -m metric_governance metric revenue 查看单项指标档案；")
    w("      python3 -m metric_governance html --out out/dashboard.html 生成可查询 HTML。")
    return "\n".join(L)


def render_dossier(d: MetricDossier) -> str:
    L: list[str] = []
    w = L.append
    w("=" * 78)
    w(f"指标档案 · {d.metric}")
    w("=" * 78)

    w("\n[1 口径定义]")
    if not d.definitions:
        w("  无已登记定义。")
    for x in d.definitions:
        w(f"  {x['metric']} {x['version']} = {x['formula']} "
          f"(自 {x['from']}, 责任人 {x['owner']}, 单位 {x['unit']})")
        if x["description"]:
            w(f"    {x['description']}")
    if d.calibers:
        w("  团队确认期间口径:")
        for c in d.calibers:
            w(f"    - {c['team']}: {c['basis']} / {c['date_field']} / {c['boundary']}")

    w("\n[2 关联发布与重开判定]")
    for a in d.assessments:
        w(f"  {a['report']} {a['period']}: 原 {a['headline_original']} -> "
          f"当前 {a['headline_restated'] or '—'} | "
          f"{'应重开' if a['should_reopen'] else a['severity']}")
        for r in a["reasons"]:
            w(f"      - {r}")
    for adv in d.advice:
        w(f"  {LEVEL_ICON.get(adv['level'], '')} {adv['title']}")

    if d.bridge:
        b = d.bridge
        w("\n[3 覆盖与同比桥接]")
        w(f"  期间 {b['base_period']} -> {b['current_period']}；"
          f"基 {num(b['base_total'])} 本 {num(b['current_total'])} "
          f"Δ {num(b['delta'])} ({pct_text(b['growth_rate'])})")
        for c in b["components"]:
            w(f"    {c['label'][:36]:<38} {c['amount']:>+9.1f}")
        w(f"  可比实体: {', '.join(b['comparable_entities']) or '无'}"
          f"；可比同比 {pct_text(b['comparable_rate'], signed=False)}")
        w(f"  范围新增: {', '.join(b['scope_new_entities']) or '无'}"
          f"；范围收缩: {', '.join(b['scope_closed_entities']) or '无'}")
        for g in b["gaps"]:
            kind_cn = GAP_KIND_CN.get(g["kind"], g["kind"])
            w(f"  🧩 {g['entity']} 覆盖{kind_cn}: 应报 {g['expected_months']}，"
              f"实有 {g['observed_months']}（缺失不置零）")
        for ck in b["open_conflicts"]:
            w(f"  ⚡ 未裁决冲突 {ck}")

    if d.members:
        m = d.members
        w("\n[3 会员去重]")
        w(f"  版本 {m['link_version']}: {m['base']['persons']} -> "
          f"{m['current']['persons']}，同比 {pct_text(m['growth_rate'])}")

    if d.category:
        c = d.category
        w("\n[3 品类归集（最新分类版本）]")
        for row in c["by_category"]:
            w(f"    {row['category']:<12} 基 {row['base']:>7.1f}  "
              f"本 {row['current']:>7.1f}  同比 {pct_text(row['growth_rate'], signed=False)}")

    w("\n[4 范围/分类登记]")
    for c in d.coverage:
        w(f"  {c['entity']:<4} {c['kind']:<8} group={c['group']:<10} "
          f"state={c['state']:<13} {c['effective_from'] or '?'}~"
          f"{c['effective_to'] or '至今'} v{c['version']}")

    w("\n[5 追溯修正]")
    if not d.corrections:
        w("  无。")
    for c in d.corrections:
        w(f"  {c['correction_id']} [{c['domain']}] {c['summary']}")

    w("\n[6 当前待处理动作]")
    if not d.pending:
        w("  无。")
    for p in d.pending:
        w(f"  {PENDING_ICON.get(p['kind'], '•')} {p['ref']} · {p['title']} "
          f"· {p['owner']} · {p['state']}")
    w("=" * 78)
    return "\n".join(L)
