"""指标档案：一口径、覆盖范围、变动来源、待处理动作与资源决策建议。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from .analytics import BridgeResult, category_growth, revenue_bridge
from .members import MemberEngine
from .models import Dataset
from .registry import Registry
from .reopen import ReopenAssessment, assess_report
from .workflow import WorkflowState


@dataclass
class DecisionAdvice:
    level: str                  # ready | conditional | blocked
    title: str
    guidance: list[str] = field(default_factory=list)
    usable_for: list[str] = field(default_factory=list)
    not_usable_for: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"level": self.level, "title": self.title,
                "guidance": self.guidance, "usable_for": self.usable_for,
                "not_usable_for": self.not_usable_for}


def advise_for_report(reg: Registry, assessment: ReopenAssessment,
                      bridge: BridgeResult | None = None) -> DecisionAdvice:
    metric = assessment.metric
    if assessment.should_reopen:
        return DecisionAdvice(
            "blocked",
            f"{assessment.report} 应重开：原结论暂停用于下月资源决策",
            guidance=assessment.reasons,
            not_usable_for=["预算追加/收缩", "渠道与门店资源分配", "品类备货与投放",
                            "团队绩效兑现"],
            usable_for=["仅可作为已发布历史版本留存"])

    if assessment.headline_restated is None:
        return DecisionAdvice(
            "blocked", "当前导入数据不足以按最新口径重算该结论",
            guidance=["缺少指标事实或会员/分类明细；在补齐并完成治理确认前，"
                      "不得把缺失主体视为零，也不应据原百分比做资源决策。"],
            not_usable_for=["下月预算与资源分配", "绩效考核"])

    if metric in {"revenue", "comparable-sales"} and bridge is not None:
        open_conf = [c for c in bridge.conflicts if c.status == "open"]
        if bridge.gaps or open_conf:
            gap_cn = {"missing": "缺失", "partial": "部分期间"}
            return DecisionAdvice(
                "blocked", "覆盖不完整或存在未裁决冲突，暂不能支撑全量资源决策",
                guidance=[g for g in [
                    *(f"覆盖缺口：{x.entity} {gap_cn.get(x.kind, x.kind)}"
                      for x in bridge.gaps),
                    *(f"未裁决冲突：{c.key_text}" for c in open_conf)]],
                not_usable_for=["全渠道预算分配", "门店/渠道排名与奖惩"])

        comp = bridge.component("comparable")
        scope_new = bridge.component("scope_new")
        pnew = bridge.component("portfolio_new")
        pdisc = bridge.component("portfolio_discontinued")
        total_delta = bridge.delta or 1.0
        organic = comp.amount if comp else 0.0
        scope_amt = scope_new.amount if scope_new else 0.0
        mix_net = ((pnew.amount if pnew else 0.0)
                   + (pdisc.amount if pdisc else 0.0))
        headline_up = (bridge.growth_rate or 0) > 0
        organic_down = (bridge.comparable_rate or 0) < 0

        if headline_up and organic_down and abs(scope_amt) + max(mix_net, 0) > abs(organic):
            return DecisionAdvice(
                "conditional",
                "总体增长由范围扩张/商品组合驱动，可比业务仍在下滑："
                "总量结论可用，结构性分配不能看汇总同比",
                guidance=[
                    f"总体同比 {bridge.growth_rate:.1f}%，但可比实体同比 "
                    f"{bridge.comparable_rate:.1f}%；",
                    f"范围扩张贡献 {scope_amt:+.1f}，商品组合净贡献 "
                    f"{mix_net:+.1f}，可比经营贡献 {organic:+.1f}（单位：登记币种单位）；",
                    "新增门店/平台的产出属于经营范围扩大，不能用于证明既有团队改善；",
                    "套装/新品的正向组合贡献可作为下月加投实验依据，"
                    "但应单独考核复购与毛利。"],
                usable_for=["总盘现金流与库存计划",
                            "对已验证有效的新品/套装做小规模追加实验"],
                not_usable_for=["按汇总同比给可比门店/传统品类追加预算",
                                "据此认定多数渠道负责人经营改善"])

        if (bridge.comparable_rate or 0) > 0 and bridge.covered:
            return DecisionAdvice(
                "ready", "可比口径为正且覆盖完整，可用于下月资源决策",
                guidance=[f"可比实体同比 {bridge.comparable_rate:.1f}%，"
                          "桥接各分量可解释且数据覆盖完整。"],
                usable_for=["可比门店/渠道的资源倾斜", "有效品类的备货与投放"])

    if assessment.severity == "watch":
        return DecisionAdvice(
            "conditional", "存在需要关注的口径事项，结论可谨慎使用",
            guidance=assessment.reasons,
            usable_for=["方向性参考"], not_usable_for=["高精度预算与绩效兑现"])

    return DecisionAdvice(
        "ready", "口径、覆盖与确认状态正常，可用于下月资源决策",
        usable_for=["月度经营调度", "常规资源配置"])


@dataclass
class PendingItem:
    kind: str                  # action | conflict | confirmation | coverage | reopen
    ref: str
    title: str
    owner: str
    state: str
    detail: str = ""
    report: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def pending_items(reg: Registry,
                  assessments: list[ReopenAssessment] | None = None
                  ) -> list[PendingItem]:
    items: list[PendingItem] = []
    for a in reg.ds.actions:
        if a.state != "complete":
            items.append(PendingItem(
                "action", a.action, a.title or f"行动 {a.action}",
                a.owner, a.state, f"关联发布 {a.report}"
                + (f"，到期 {a.due_on}" if a.due_on else ""),
                report=a.report))
    for a in reg.state.extra_actions:
        if a.get("state") != "complete":
            items.append(PendingItem(
                "action", a["action"], a.get("title", ""),
                a.get("owner", ""), a.get("state", "issued"),
                f"重开跟进，关联 {a.get('report')}",
                report=a.get("report", "")))

    # 未裁决冲突
    from .quality import select_facts
    _, conflicts = select_facts(reg.ds.facts, reg)
    for c in conflicts:
        if c.status == "open":
            items.append(PendingItem(
                "conflict", c.key_text,
                f"指标事实冲突：{c.key[0]} {c.key[1]} {c.key[2]} {c.key[3]}",
                "metric-governance", "open",
                "候选值 " + " / ".join(str(v) for v in c.distinct_values)))

    # 覆盖缺口（按当前期间集合去重）
    seen_gaps: set[str] = set()
    for report in reg.ds.reports:
        b = revenue_bridge(reg, report.period, report.compare_period or None)
        for g in b.gaps:
            token = f"{g.metric}:{g.period}:{g.entity}:{g.kind}"
            if token in seen_gaps:
                continue
            seen_gaps.add(token)
            items.append(PendingItem(
                "coverage", token,
                f"{g.period} {g.entity} 覆盖{g.kind == 'partial' and '部分' or '缺失'}",
                "channel-owner", g.kind, g.reason))

    # 待确认的关键谱系/新品关系
    for edge in reg.ds.lineage:
        key = f"{edge.entity}:{edge.relation}:{edge.related}"
        if not reg._edge_effectively_confirmed(edge):
            role = ("product-owner" if edge.kind == "product"
                    else "channel-owner")
            items.append(PendingItem(
                "confirmation", key,
                f"待确认{edge.kind}谱系：{edge.entity} {edge.relation} {edge.related}",
                role, "pending", edge.note))

    # 重开个案（工作流中已登记）
    for case in reg.state.reopen_cases:
        if case.get("status") == "reopened":
            items.append(PendingItem(
                "reopen", case["report"],
                f"发布 {case['report']} 已登记重开",
                case.get("owner", "analytics-governance"), "reopened",
                "；".join(case.get("reasons", []))[:200],
                report=case["report"]))
    return items


@dataclass
class MetricDossier:
    metric: str
    definitions: list[dict]
    calibers: list[dict]
    reports: list[dict]
    bridge: Optional[dict]
    category: Optional[dict]
    members: Optional[dict]
    assessments: list[dict]
    pending: list[dict]
    corrections: list[dict]
    coverage: list[dict]
    advice: list[dict]

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def build_dossier(reg: Registry, metric: str) -> MetricDossier:
    defs = [{"metric": d.metric, "version": d.version, "formula": d.formula,
             "from": d.effective_from.isoformat() if d.effective_from else "",
             "owner": d.owner, "unit": d.unit,
             "description": d.description}
            for d in reg.ds.definitions if d.metric == metric]

    teams = {f.team for f in reg.ds.facts if f.metric == metric}
    formula_basis = {d.formula for d in reg.ds.definitions if d.metric == metric}
    calibers = [c.__dict__ for c in reg.ds.calibers
                if c.team in teams or c.basis in formula_basis]

    related_reports = [r for r in reg.ds.reports if r.metric == metric]
    assessments = [assess_report(reg, r).to_dict() for r in related_reports]

    bridge_dict = None
    category_dict = None
    members_dict = None
    advice_dicts = []
    if metric == "members":
        engine = MemberEngine(reg.ds)
        if related_reports:
            rep = related_reports[0]
            members_dict = engine.growth(
                rep.period, rep.compare_period or rep.period,
                engine.latest_version())
    elif metric == "category-growth":
        if related_reports:
            rep = related_reports[0]
            category_dict = category_growth(
                reg, rep.period, "skincare",
                rep.compare_period or None).to_dict()
    else:
        # revenue / comparable-sales 都由 revenue 指标事实经范围规则计算
        if related_reports:
            rep = related_reports[0]
            b = revenue_bridge(reg, rep.period,
                               rep.compare_period or None,
                               metric="revenue")
            bridge_dict = b.to_dict()
            for r in related_reports:
                a = assess_report(reg, r, bridge=b)
                advice_dicts.append(advise_for_report(reg, a, b).to_dict())

    if not advice_dicts:
        for r in related_reports:
            a = assess_report(reg, r)
            advice_dicts.append(advise_for_report(reg, a).to_dict())

    report_ids = {r.report for r in related_reports}
    all_pending = pending_items(reg)
    pending = [p.to_dict() for p in all_pending
               if p.report in report_ids
               or metric in p.detail
               or (p.kind == "confirmation"
                   and metric in {"revenue", "category-growth",
                                  "comparable-sales"})]

    domain_map = {
        "members": {"member_identity"},
        "comparable-sales": {"store_status", "scope", "fact"},
        "category-growth": {"product_classification"},
        "revenue": {"fact", "store_status", "scope", "product_classification"},
    }
    domains = domain_map.get(metric)
    corrections = []
    for c in reg.ds.corrections:
        if domains is not None and c.domain not in domains:
            continue
        corrections.append(c.__dict__ | {
            "detected_on": c.detected_on.isoformat() if c.detected_on else None,
            "effective_from": c.effective_from.isoformat()
            if c.effective_from else None})
    coverage = [c.__dict__ | {"effective_from": c.effective_from.isoformat()
                              if c.effective_from else None,
                              "effective_to": c.effective_to.isoformat()
                              if c.effective_to else None}
                for c in reg.ds.coverage]
    if metric == "category-growth":
        coverage = [c for c in coverage if c["kind"] == "sku"]
    elif metric == "members":
        coverage = []
    else:
        coverage = [c for c in coverage
                    if c["kind"] in {"store", "platform", "channel"}]

    return MetricDossier(
        metric=metric, definitions=defs, calibers=calibers,
        reports=[r.__dict__ | {"published_on": r.published_on.isoformat()
                               if r.published_on else None}
                 for r in related_reports],
        bridge=bridge_dict, category=category_dict, members=members_dict,
        assessments=assessments, pending=pending, corrections=corrections,
        coverage=coverage, advice=advice_dicts)
