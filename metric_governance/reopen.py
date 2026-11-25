"""发布结论的追溯影响分析与重开判定。

原则：
- 原发布版本以 snapshots/<report>.json 只读保存，重开分析永不改写；
- 行动完成记录（如 A2=complete）原样保留，重开结论不等于抹掉执行历史；
- 身份图谱、门店状态/谱系、商品分类出现追溯修正，或迟到数据/冲突
  导致已发布数字越过重要性阈值时，判定“应重开”。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .analytics import BridgeResult, category_growth, revenue_bridge
from .members import MemberEngine
from .models import Dataset, Report
from .periods import Period
from .registry import Registry

MATERIAL_PP = 0.5  # 同比增长率变动超过 0.5 个百分点视为重要


@dataclass
class ReopenAssessment:
    report: str
    metric: str
    period: str
    should_reopen: bool
    severity: str               # reopen | watch | stable
    headline_original: str
    headline_restated: Optional[str]
    delta_pp: Optional[float]
    reasons: list[str] = field(default_factory=list)
    correction_ids: list[str] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    snapshot_preserved: bool = True
    restated: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "report": self.report, "metric": self.metric, "period": self.period,
            "should_reopen": self.should_reopen, "severity": self.severity,
            "headline_original": self.headline_original,
            "headline_restated": self.headline_restated,
            "delta_pp": None if self.delta_pp is None else round(self.delta_pp, 3),
            "reasons": self.reasons, "correction_ids": self.correction_ids,
            "actions": self.actions,
            "snapshot_preserved": self.snapshot_preserved,
            "restated": self.restated,
        }


def load_snapshot(ds: Dataset, report_id: str) -> Optional[dict[str, Any]]:
    if not ds.snapshots_dir:
        return None
    path = Path(ds.snapshots_dir) / f"{report_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_snapshot(snapshots_dir: str | Path, report_id: str,
                   payload: dict[str, Any], overwrite: bool = False) -> Path:
    """写发布快照。默认 write-once：已存在则拒绝覆盖。"""
    d = Path(snapshots_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{report_id}.json"
    if path.exists() and not overwrite:
        raise FileExistsError(f"发布快照已存在，禁止覆盖: {path}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def _action_records(reg: Registry, report_id: str) -> list[dict]:
    rows = [{"action": a.action, "owner": a.owner, "title": a.title,
             "state": a.state, "completed_on":
             a.completed_on.isoformat() if a.completed_on else "",
             "completion_note": a.completion_note, "source": "actions.csv"}
            for a in reg.ds.actions if a.report == report_id]
    for a in reg.state.extra_actions:
        if a.get("report") == report_id:
            rows.append({**a, "source": "workflow-state"})
    return rows


def _corrections_for(ds: Dataset, metric: str, period: str,
                     snapshot: dict) -> list:
    # 只有能改变该指标解释/数值的修正领域才关联；总收入口径不受
    # 门店归类或品类重分类影响（它们改变的是结构与可比范围）。
    domain_for_metric = {
        "members": {"member_identity"},
        "comparable-sales": {"store_status", "scope", "fact"},
        "category-growth": {"product_classification"},
        "revenue": {"fact"},
    }
    domains = domain_for_metric.get(metric, set())
    try:
        p_end = Period.parse(period).end
    except ValueError:
        p_end = None
    hits = []
    snap_corr = set(snapshot.get("applied_corrections", []))
    for c in ds.corrections:
        if c.correction_id in snap_corr:
            continue  # 发布时已反映
        if c.domain not in domains and c.target not in {metric}:
            continue
        # 生效日晚于报告期末的修正不可能影响该期
        if p_end and c.effective_from and c.effective_from > p_end:
            continue
        hits.append(c)
    return hits


def assess_report(reg: Registry, report: Report,
                  bridge: BridgeResult | None = None) -> ReopenAssessment:
    ds = reg.ds
    snapshot = load_snapshot(ds, report.report) or {}
    original_text = report.value_text or str(snapshot.get("headline", ""))
    original_num = snapshot.get("headline_numeric")
    reasons: list[str] = []
    restated_num: Optional[float] = None
    restated_text: Optional[str] = None
    restated_payload: dict[str, Any] = {}

    corrections = _corrections_for(ds, report.metric, report.period, snapshot)
    corr_ids = [c.correction_id for c in corrections]
    for c in corrections:
        reasons.append(f"追溯修正 {c.correction_id}（{c.domain}）：{c.summary}")

    # ---------------- 按指标类别重算当前口径
    if report.metric == "members":
        engine = MemberEngine(ds)
        old_ver = snapshot.get("link_version") or engine.versions()[0] if engine.versions() else None
        new_ver = engine.latest_version()
        compare = report.compare_period or snapshot.get("compare_period")
        current = engine.growth(report.period, compare, new_ver)
        restated_num = current["growth_rate"]
        restated_text = None if restated_num is None else f"{restated_num:.1f}%"
        restated_payload = current
        if old_ver and new_ver and old_ver != new_ver:
            reasons.append(
                f"会员去重版本由 {old_ver} 追溯修订为 {new_ver}："
                f"去重人数 {current['base']['persons']}→{current['current']['persons']}（本期）")
    elif report.metric == "category-growth":
        cat = snapshot.get("category", "skincare")
        old_ver = snapshot.get("classification_version", "2")
        result = category_growth(reg, report.period, cat,
                                 report.compare_period or None,
                                 classification_version=None)
        old_view = category_growth(reg, report.period, cat,
                                   report.compare_period or None,
                                   classification_version=old_ver)
        restated_num = result.growth_rate
        restated_text = None if restated_num is None else f"{restated_num:.1f}%"
        restated_payload = result.to_dict()
        if old_view.growth_rate is not None and result.growth_rate is not None:
            reasons.append(
                f"品类分类追溯修订：{cat} 同比由 {old_view.growth_rate:.1f}% "
                f"变为 {result.growth_rate:.1f}%（{old_ver}→最新分类）")
    elif report.metric == "comparable-sales":
        b = bridge or revenue_bridge(reg, report.period,
                                     report.compare_period or None,
                                     metric="revenue")
        restated_num = b.comparable_rate
        restated_text = None if restated_num is None else f"{restated_num:.1f}%"
        restated_payload = {"comparable_base": b.comparable_base,
                            "comparable_current": b.comparable_current,
                            "entities": b.comparable_entities,
                            "gaps": [g.to_dict() for g in b.gaps],
                            "open_conflicts": [c.key_text for c in b.conflicts
                                               if c.status == "open"]}
        snap_entities = set(snapshot.get("scope_entities", []))
        now_entities = set(b.comparable_entities)
        if snap_entities and snap_entities != now_entities:
            added = sorted(e for e in now_entities - snap_entities)
            removed = sorted(e for e in snap_entities - now_entities)
            if added:
                reasons.append(f"可比范围新增匹配主体：{', '.join(added)}（迟到数据或谱系修正）")
            if removed:
                reasons.append(f"可比范围移出主体：{', '.join(removed)}")
        if b.gaps:
            reasons.append("当前仍存在覆盖缺口：" +
                           "、".join(f"{g.entity}({g.kind})" for g in b.gaps))
        comp_set = set(b.comparable_entities)
        relevant_conflicts = [
            c for c in b.conflicts if c.status == "open"
            and any(c.key[2] == ent or c.key[2] in ent.split("→")
                    for ent in comp_set)]
        if relevant_conflicts:
            reasons.append("可比范围内存在未裁决的指标事实冲突")
    else:  # revenue 及其它金额/比率指标
        b = bridge or revenue_bridge(reg, report.period,
                                     report.compare_period or None,
                                     metric=report.metric
                                     if any(d.metric == report.metric for d in ds.definitions)
                                     else "revenue")
        restated_num = b.growth_rate
        restated_text = None if restated_num is None else f"{restated_num:.1f}%"
        restated_payload = b.to_dict()
        if b.gaps:
            reasons.append("当前存在覆盖缺口，总计尚不能完整重述：" +
                           "、".join(f"{g.entity}({g.kind})" for g in b.gaps))
        if any(c.status == "open" for c in b.conflicts):
            reasons.append("存在未裁决的指标事实冲突")

    delta_pp = None
    if isinstance(original_num, (int, float)) and restated_num is not None:
        delta_pp = restated_num - float(original_num)

    material = delta_pp is not None and abs(delta_pp) >= MATERIAL_PP
    sign_flip = (isinstance(original_num, (int, float))
                 and restated_num is not None
                 and original_num * restated_num < 0)
    unquantifiable = bool(corrections) and delta_pp is None
    should_reopen = bool(material or sign_flip or unquantifiable)
    severity = "reopen" if should_reopen else ("watch" if reasons else "stable")

    return ReopenAssessment(
        report=report.report, metric=report.metric, period=report.period,
        should_reopen=should_reopen, severity=severity,
        headline_original=original_text,
        headline_restated=restated_text, delta_pp=delta_pp,
        reasons=reasons, correction_ids=corr_ids,
        actions=_action_records(reg, report.report),
        snapshot_preserved=bool(snapshot),
        restated=restated_payload)
