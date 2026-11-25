"""经营总览组装：把导入数据、分析、重开判定、建议和待办汇成单一视图模型。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .analytics import category_growth, monthly_trend, revenue_bridge
from .dossier import advise_for_report, pending_items
from .members import MemberEngine
from .registry import Registry
from .reopen import assess_report

PUBLISH_DATE_R3 = date(2026, 10, 12)


@dataclass
class Overview:
    data_dir: str
    generated_on: str
    issues: list[dict]
    publications: list[dict[str, Any]]
    bridges: dict[str, dict[str, Any]]
    monthly: list[dict[str, Any]]
    member_views: dict[str, Any]
    category_views: dict[str, Any]
    pending: list[dict]
    counts: dict[str, int]

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def build_overview(reg: Registry) -> Overview:
    ds = reg.ds

    # 每份发布：重开判定 + 决策建议
    publications: list[dict[str, Any]] = []
    bridge_q3 = revenue_bridge(reg, "2026-Q3")
    for rep in ds.reports:
        if rep.metric == "comparable-sales":
            assessment = assess_report(reg, rep, bridge=bridge_q3)
            advice = advise_for_report(reg, assessment, bridge_q3)
        elif rep.metric == "revenue":
            b = revenue_bridge(reg, rep.period, rep.compare_period or None)
            assessment = assess_report(reg, rep, bridge=b)
            advice = advise_for_report(reg, assessment, b)
        else:
            assessment = assess_report(reg, rep)
            advice = advise_for_report(reg, assessment)
        publications.append({
            "report": rep.report, "metric": rep.metric, "period": rep.period,
            "value": rep.value_text, "definition": rep.definition,
            "owner": rep.owner, "conclusion": rep.conclusion,
            "action": rep.action, "state": rep.state,
            "published_on": rep.published_on.isoformat() if rep.published_on else "",
            "assessment": assessment.to_dict(),
            "advice": advice.to_dict(),
        })

    bridges = {
        "2026-Q2": revenue_bridge(reg, "2026-Q2").to_dict(),
        "2026-Q3-current": bridge_q3.to_dict(),
        "2026-Q3-publish-view": revenue_bridge(
            Registry(ds, reg.state, as_of=PUBLISH_DATE_R3),
            "2026-Q3", as_of=PUBLISH_DATE_R3).to_dict(),
    }
    monthly = monthly_trend(reg)

    engine = MemberEngine(ds)
    member_views = {
        "versions": engine.versions(),
        "L1": engine.growth("2026-Q2", "2025-Q2", "L1"),
        "L2": engine.growth("2026-Q2", "2025-Q2", "L2"),
    }
    category_views = {
        "published_v2": category_growth(
            reg, "2026-Q3", "skincare", classification_version="2").to_dict(),
        "restated_v3": category_growth(
            reg, "2026-Q3", "skincare").to_dict(),
    }

    assessments = [assess_report(reg, r) for r in ds.reports]
    pending = [p.to_dict() for p in pending_items(reg, assessments)]

    issues = [{"level": i.level, "code": i.code, "message": i.message}
              for i in ds.issues]

    counts = {
        "definitions": len(ds.definitions), "facts": len(ds.facts),
        "coverage_rows": len(ds.coverage), "lineage_edges": len(ds.lineage),
        "reports": len(ds.reports), "actions": len(ds.actions),
        "corrections": len(ds.corrections),
        "pending": len(pending),
        "reopen": sum(1 for a in assessments if a.should_reopen),
    }

    return Overview(
        data_dir=ds.root, generated_on=date.today().isoformat(),
        issues=issues, publications=publications, bridges=bridges,
        monthly=monthly,
        member_views=member_views, category_views=category_views,
        pending=pending, counts=counts)
