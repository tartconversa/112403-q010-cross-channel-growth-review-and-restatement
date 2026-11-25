"""来源冲突与覆盖完整性。

关键不变量：**没有事实就是没有事实**。覆盖缺口显式登记，
聚合层只能基于实际存在且已生效的单元格，绝不把缺失渠道补成 0。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .models import Fact
from .periods import Period
from .registry import Registry
from .workflow import WorkflowState


def natural_key(f: Fact | None = None, *, metric: str = "", period: str = "",
                entity: str = "", sku: str = "") -> tuple[str, str, str, str]:
    if f is not None:
        return (f.metric, f.period, f.entity, f.sku or "")
    return (metric, period, entity, sku)


def conflict_key(key: tuple[str, str, str, str]) -> str:
    return "|".join(key)


@dataclass
class Conflict:
    key: tuple[str, str, str, str]
    candidates: list[Fact] = field(default_factory=list)
    resolution: Optional[dict] = None

    @property
    def key_text(self) -> str:
        return conflict_key(self.key)

    @property
    def distinct_values(self) -> list[float]:
        return sorted({f.value for f in self.candidates if f.value is not None})

    @property
    def status(self) -> str:
        return "resolved" if self.resolution else "open"

    def chosen_value(self) -> Optional[float]:
        if not self.resolution:
            return None
        if self.resolution.get("chosen_value") not in (None, ""):
            try:
                return float(self.resolution["chosen_value"])
            except (TypeError, ValueError):
                pass
        fid = self.resolution.get("chosen_fact_id")
        for f in self.candidates:
            if f.fact_id == fid:
                return f.value
        return None


def _all_resolutions(reg: Registry) -> dict[str, dict]:
    merged: dict[str, dict] = {}
    for r in reg.ds.resolutions:
        if r.get("conflict_key"):
            merged[r["conflict_key"]] = r
    for r in reg.state.resolutions:
        merged[r["conflict_key"]] = r
    return merged


def select_facts(facts: list[Fact], reg: Registry | None = None,
                 as_of: date | None = None
                 ) -> tuple[dict[tuple, Fact], list[Conflict]]:
    """按自然键去重并应用冲突裁决。

    返回 ``cells``：自然键 -> 生效 Fact（每键恰好一个值），
    以及冲突清单。未裁决的冲突不进入 cells（不猜测、不平均）。
    """
    resolutions = _all_resolutions(reg) if reg is not None else {
        r["conflict_key"]: r for r in WorkflowState().resolutions}

    groups: dict[tuple, list[Fact]] = {}
    for f in facts:
        if f.value is None:
            continue
        if as_of and f.received_on and f.received_on > as_of:
            continue
        groups.setdefault(natural_key(f), []).append(f)

    cells: dict[tuple, Fact] = {}
    conflicts: list[Conflict] = []
    for key, rows in groups.items():
        values = {f.value for f in rows}
        if len(values) == 1:
            # 同值重发：保留最新接收的一条作为代表，不重复计量
            cells[key] = sorted(rows, key=lambda f: f.received_on or date.min)[-1]
            continue
        ck = conflict_key(key)
        resolution = resolutions.get(ck)
        conflict = Conflict(key=key, candidates=sorted(
            rows, key=lambda f: (f.received_on or date.min, f.fact_id)),
            resolution=resolution)
        conflicts.append(conflict)
        if resolution:
            value = conflict.chosen_value()
            chosen = None
            fid = resolution.get("chosen_fact_id") if resolution else ""
            if fid:
                chosen = next((f for f in rows if f.fact_id == fid), None)
            if chosen is None and value is not None:
                chosen = next((f for f in rows if f.value == value), None)
            if chosen is not None:
                cells[key] = chosen
    return cells, sorted(conflicts, key=lambda c: c.key_text)


@dataclass
class CoverageGap:
    metric: str
    period: str
    entity: str
    kind: str                  # missing | partial
    expected_months: list[str]
    observed_months: list[str]
    reason: str = ""

    def to_dict(self) -> dict:
        return {"metric": self.metric, "period": self.period,
                "entity": self.entity, "kind": self.kind,
                "expected_months": self.expected_months,
                "observed_months": self.observed_months, "reason": self.reason}


def expected_months_for_entity(reg: Registry, entity: str,
                               period: Period) -> list[str]:
    """根据覆盖区间计算实体在该期间内应报送的月份。"""
    months = [m.key for m in period.months()]
    has_any_row = bool(reg.coverage_for(entity))
    result = []
    for mk in months:
        mp = Period.parse(mk)
        row = reg._row_on(entity, mp.end)
        if row is None:
            # 完全没有范围登记时保守要求全期；
            # 有登记但该月不落在任何有效区间 => 当时尚未开业/已退出，不要求
            if not has_any_row:
                result.append(mk)
            continue
        if row.effective_from and row.effective_from > mp.end:
            continue
        if row.effective_to and row.effective_to < mp.start:
            continue
        if row.state in {"closed", "inactive", "divested"}:
            continue
        result.append(mk)
    return result


def coverage_gaps(reg: Registry, metric: str, period: Period | str,
                  cells: dict[tuple, Fact]) -> list[CoverageGap]:
    """对照范围名册与已生效事实，找出缺失/部分覆盖的渠道或门店。"""
    p = period if isinstance(period, Period) else Period.parse(period)
    gaps: list[CoverageGap] = []
    for entity in reg.expected_reporting_entities(p, metric):
        expected = expected_months_for_entity(reg, entity, p)
        observed = sorted({k[1] for k in cells
                           if k[0] == metric and k[2] == entity
                           and Period.parse(k[1]).kind == "month"
                           and k[1] in expected})
        if not observed:
            gaps.append(CoverageGap(
                metric, p.key, entity, "missing", expected, [],
                "范围内但没有任何已生效事实；不得按 0 处理"))
        elif expected and len(set(expected) - set(observed)) > 0:
            gaps.append(CoverageGap(
                metric, p.key, entity, "partial", expected, observed,
                f"仅覆盖 {len(observed)}/{len(expected)} 个应报月份"))
    return gaps
