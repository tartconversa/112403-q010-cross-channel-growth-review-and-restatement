"""经营分析：把总体同比变动拆成 可比业务、商品组合、经营范围、口径修正。

核心纪律：
1. 桥接各分量之和必须严格等于“已采用单元格”的总差值（精确可加）；
2. 覆盖缺口（缺渠道/缺期间）两侧同时剔除出桥，只作备忘，绝不把缺失当 0；
3. 未裁决冲突单元格不进入合计；
4. 范围扩大（新店/新平台）与可比经营分开列示。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .models import Fact
from .periods import Period
from .quality import (
    Conflict, CoverageGap, coverage_gaps, select_facts,
)
from .registry import EntityMatch, Registry


@dataclass
class BridgeComponent:
    code: str
    label: str
    amount: float
    base_amount: float = 0.0
    current_amount: float = 0.0
    detail: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"code": self.code, "label": self.label,
                "amount": round(self.amount, 6),
                "base_amount": round(self.base_amount, 6),
                "current_amount": round(self.current_amount, 6),
                "detail": self.detail}


@dataclass
class BridgeResult:
    metric: str
    current_period: str
    base_period: str
    unit: str
    base_total: float
    current_total: float
    delta: float
    growth_rate: Optional[float]          # 百分数数值，12.4 表示 12.4%
    components: list[BridgeComponent]
    gaps: list[CoverageGap]
    conflicts: list[Conflict]
    comparable_entities: list[str]
    scope_new_entities: list[str]
    scope_closed_entities: list[str]
    comparable_base: float
    comparable_current: float
    comparable_rate: Optional[float]
    covered: bool
    notes: list[str] = field(default_factory=list)
    reported_base_total: float = 0.0
    reported_current_total: float = 0.0
    excluded_base: float = 0.0
    excluded_current: float = 0.0

    def component(self, code: str) -> BridgeComponent | None:
        return next((c for c in self.components if c.code == code), None)

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "current_period": self.current_period,
            "base_period": self.base_period, "unit": self.unit,
            "base_total": self.base_total,
            "current_total": self.current_total, "delta": self.delta,
            "growth_rate": None if self.growth_rate is None
            else round(self.growth_rate, 4),
            "components": [c.to_dict() for c in self.components],
            "gaps": [g.to_dict() for g in self.gaps],
            "open_conflicts": [c.key_text for c in self.conflicts
                               if c.status == "open"],
            "comparable_entities": self.comparable_entities,
            "scope_new_entities": self.scope_new_entities,
            "scope_closed_entities": self.scope_closed_entities,
            "comparable_base": self.comparable_base,
            "comparable_current": self.comparable_current,
            "comparable_rate": None if self.comparable_rate is None
            else round(self.comparable_rate, 4),
            "covered": self.covered, "notes": self.notes,
            "reported_base_total": self.reported_base_total,
            "reported_current_total": self.reported_current_total,
            "excluded_base": self.excluded_base,
            "excluded_current": self.excluded_current,
        }


def pct(cur: float, base: float) -> Optional[float]:
    if base == 0:
        return None
    return (cur - base) / base * 100.0


def _period_cells(cells: dict[tuple, Fact], metric: str,
                  period: Period) -> dict[tuple[str, str], float]:
    """把期间内（月度或季度）事实汇总为 (entity, sku) -> value。"""
    out: dict[tuple[str, str], float] = {}
    months = {m.key for m in period.months()} if period.kind != "year" else None
    for (m, pkey, ent, sku), fact in cells.items():
        if m != metric or fact.value is None:
            continue
        p = Period.parse(pkey)
        inside = False
        if pkey == period.key:
            inside = True
        elif p.kind == "month" and months is not None and pkey in months:
            inside = True
        elif p.kind in {"quarter", "year"} and period.start <= p.start and p.end <= period.end:
            inside = True
        if inside:
            out[(ent, sku or "")] = out.get((ent, sku or ""), 0.0) + fact.value
    return out


def _product_pairs(base_map: dict[str, float], cur_map: dict[str, float],
                   reg: Registry) -> list[tuple[Optional[str], Optional[str], str]]:
    """返回 (base_sku|None, cur_sku|None, method) 配对，覆盖全部 SKU。"""
    base_skus = set(base_map)
    cur_skus = set(cur_map)
    pairs: list[tuple[Optional[str], Optional[str], str]] = []
    used_b: set[str] = set()
    used_c: set[str] = set()

    # 已确认的商品续接关系（successor-of: entity=新品, related=旧品）
    for edge in reg.ds.lineage:
        if edge.kind != "product" or edge.relation not in {
                "successor-of", "supersedes", "renamed-from"}:
            continue
        if not reg._edge_effectively_confirmed(edge):
            continue
        old, new = edge.related, edge.entity
        if old in base_skus and new in cur_skus:
            pairs.append((old, new, f"lineage:{edge.relation}"))
            used_b.add(old)
            used_c.add(new)

    for sku in sorted(base_skus & cur_skus):
        if sku not in used_b and sku not in used_c:
            pairs.append((sku, sku, "same-id"))
            used_b.add(sku)
            used_c.add(sku)
    for sku in sorted(base_skus - used_b):
        pairs.append((sku, None, "base-only"))
    for sku in sorted(cur_skus - used_c):
        pairs.append((None, sku, "current-only"))
    return pairs


def revenue_bridge(reg: Registry, current_period: str | Period,
                   base_period: str | Period | None = None,
                   as_of: date | None = None,
                   metric: str = "revenue") -> BridgeResult:
    cp = current_period if isinstance(current_period, Period) else Period.parse(current_period)
    bp = (base_period if isinstance(base_period, Period)
          else Period.parse(base_period) if base_period else cp.prior_year())

    if as_of is not None:
        reg.as_of = as_of
    effective_as_of = as_of or getattr(reg, "as_of", None)
    cells, all_conflicts = select_facts(reg.ds.facts, reg, as_of=effective_as_of)

    def _within(pkey: str, period: Period) -> bool:
        if pkey == period.key:
            return True
        try:
            pk = Period.parse(pkey)
        except ValueError:
            return False
        if pk.kind == "month":
            return pk.key in {m.key for m in period.months()}
        return period.start <= pk.start and pk.end <= period.end

    conflicts = [c for c in all_conflicts
                 if c.key[0] == metric
                 and (_within(c.key[1], bp) or _within(c.key[1], cp))]

    base_all = _period_cells(cells, metric, bp)
    cur_all = _period_cells(cells, metric, cp)
    reported_base = sum(base_all.values())
    reported_cur = sum(cur_all.values())

    base_gaps = coverage_gaps(reg, metric, bp, cells)
    cur_gaps = coverage_gaps(reg, metric, cp, cells)
    gaps = base_gaps + cur_gaps
    # 缺失或仅部分覆盖的实体：两侧同时移出桥接周边界。
    # 部分期间数据不能与完整期间直接相减，更不能把缺失月份当 0。
    gap_entities = {g.entity for g in gaps}

    matches = reg.match_entities(bp, cp)
    used_b: set[str] = set()
    used_c: set[str] = set()
    pair_records: list[dict] = []

    comp = {code: BridgeComponent(code, label, 0.0) for code, label in [
        ("comparable", "可比业务变化（同范围门店/平台与续接商品）"),
        ("portfolio_new", "组合变化·新品/新规格贡献"),
        ("portfolio_discontinued", "组合变化·退市/收缩商品"),
        ("scope_new", "经营范围扩大（新门店/新平台）"),
        ("scope_closed", "经营范围收缩（关闭/迁出主体）"),
    ]}

    comparable_entities: list[str] = []
    scope_new_entities: list[str] = []
    scope_closed_entities: list[str] = []
    covered_b = covered_c = 0.0
    comp_base = comp_cur = 0.0

    def excluded(entity: str) -> bool:
        return entity in gap_entities

    # 先放谱系配对，再放同 ID（match_entities 已排好序）
    for m in matches:
        b_ent, c_ent = m.base_entity, m.current_entity
        if b_ent in used_b or c_ent in used_c:
            continue
        used_b.add(b_ent)
        used_c.add(c_ent)
        b_map = {sku: v for (ent, sku), v in base_all.items() if ent == b_ent}
        c_map = {sku: v for (ent, sku), v in cur_all.items() if ent == c_ent}
        b_sum, c_sum = sum(b_map.values()), sum(c_map.values())
        if excluded(b_ent) or excluded(c_ent):
            continue

        cur_state = reg.state_in_period(c_ent, cp)
        base_state = reg.state_in_period(b_ent, bp)
        lineage_pair = m.method.startswith("lineage")

        # 纯范围新增：本期主体被登记为 new，且基期无事实
        is_scope_new = (not lineage_pair and cur_state == "new"
                        and b_ent == c_ent and not b_map)
        # 范围收缩：同一主体本期已关闭/剥离且无本期事实
        is_scope_closed = (not lineage_pair and b_ent == c_ent
                           and bool(b_map) and not c_map
                           and cur_state in {"closed", "divested"})

        covered_b += b_sum
        covered_c += c_sum

        if is_scope_new:
            scope_new_entities.append(c_ent)
            comp["scope_new"].amount += c_sum
            comp["scope_new"].current_amount += c_sum
            comp["scope_new"].detail.append(
                {"entity": c_ent, "base": 0.0, "current": round(c_sum, 4),
                 "method": m.method})
            continue
        if is_scope_closed:
            scope_closed_entities.append(b_ent)
            comp["scope_closed"].amount += -b_sum
            comp["scope_closed"].base_amount += b_sum
            comp["scope_closed"].detail.append(
                {"entity": b_ent, "base": round(b_sum, 4), "current": 0.0,
                 "method": m.method})
            continue

        # 持续经营 / 搬迁续体 => 可比实体，分解商品组合
        label_ent = c_ent if c_ent == b_ent else f"{b_ent}→{c_ent}"
        comparable_entities.append(label_ent)
        comp_base += b_sum
        comp_cur += c_sum
        for b_sku, c_sku, method in _product_pairs(b_map, c_map, reg):
            bv = b_map.get(b_sku, 0.0) if b_sku else 0.0
            cv = c_map.get(c_sku, 0.0) if c_sku else 0.0
            if b_sku and c_sku:
                d = cv - bv
                comp["comparable"].amount += d
                comp["comparable"].base_amount += bv
                comp["comparable"].current_amount += cv
                comp["comparable"].detail.append({
                    "entity": label_ent, "sku": c_sku, "base": round(bv, 4),
                    "current": round(cv, 4), "delta": round(d, 4),
                    "method": method})
            elif c_sku:
                comp["portfolio_new"].amount += cv
                comp["portfolio_new"].current_amount += cv
                comp["portfolio_new"].detail.append({
                    "entity": label_ent, "sku": c_sku, "current": round(cv, 4)})
            elif b_sku:
                comp["portfolio_discontinued"].amount += -bv
                comp["portfolio_discontinued"].base_amount += bv
                comp["portfolio_discontinued"].detail.append({
                    "entity": label_ent, "sku": b_sku, "base": round(bv, 4)})

    # 未被任何匹配覆盖的残余实体（例如有事实但无范围登记）
    for (ent, sku), v in base_all.items():
        if ent not in used_b and not excluded(ent):
            covered_b += v
            comp["scope_closed"].amount += -v
            comp["scope_closed"].base_amount += v
            scope_closed_entities.append(ent)
            used_b.add(ent)
    for (ent, sku), v in cur_all.items():
        if ent not in used_c and not excluded(ent):
            covered_c += v
            comp["scope_new"].amount += v
            comp["scope_new"].current_amount += v
            scope_new_entities.append(ent)
            used_c.add(ent)

    # 缺口实体金额（备忘/调节，不进桥）
    excluded_base = sum(v for (ent, _), v in base_all.items() if ent in gap_entities)
    excluded_cur = sum(v for (ent, _), v in cur_all.items() if ent in gap_entities)

    components = [c for c in comp.values() if abs(c.amount) > 1e-9 or c.detail]
    delta = covered_c - covered_b
    growth = pct(covered_c, covered_b)
    comp_rate = pct(comp_cur, comp_base)

    open_conflicts = [c for c in conflicts if c.status == "open"]
    notes: list[str] = []
    if gaps:
        notes.append("存在覆盖缺口：缺口实体已从桥接周边界两侧剔除，其金额不视为零。")
    if open_conflicts:
        notes.append("存在未裁决冲突：冲突单元格未计入合计，待治理裁决。")

    definition = reg.definition(metric)
    unit = definition.unit if definition else ""

    return BridgeResult(
        metric=metric, current_period=cp.key, base_period=bp.key, unit=unit,
        base_total=round(covered_b, 6), current_total=round(covered_c, 6),
        delta=round(delta, 6), growth_rate=growth,
        components=components, gaps=gaps, conflicts=conflicts,
        comparable_entities=sorted(set(comparable_entities)),
        scope_new_entities=sorted(set(scope_new_entities)),
        scope_closed_entities=sorted(set(scope_closed_entities)),
        comparable_base=round(comp_base, 6),
        comparable_current=round(comp_cur, 6),
        comparable_rate=comp_rate,
        covered=not gaps and not open_conflicts,
        notes=notes,
        reported_base_total=round(reported_base, 6),
        reported_current_total=round(reported_cur, 6),
        excluded_base=round(excluded_base, 6),
        excluded_current=round(excluded_cur, 6))


# ---------------------------------------------------------------- 月度趋势

def monthly_trend(reg: Registry, months: list[str] | None = None,
                  metric: str = "revenue") -> list[dict]:
    """按月汇总已生效事实（用于管理层月度视角）。

    每月单独做覆盖检查：存在 missing/partial 主体时在 ``coverage_flags``
    中标出，金额仍是“实际已报且裁决有效”的合计，绝不把缺口补零。
    """
    if months is None:
        months = [f"2026-{m:02d}" for m in range(4, 10)]
    cells, conflicts = select_facts(reg.ds.facts, reg)
    rows: list[dict] = []
    for mk in months:
        cur_p = Period.parse(mk)
        base_p = cur_p.prior_year()

        def month_sum(p: Period) -> float:
            total = 0.0
            for (m, pkey, ent, sku), fact in cells.items():
                if m == metric and pkey == p.key and fact.value is not None:
                    total += fact.value
            return total

        cur = month_sum(cur_p)
        base = month_sum(base_p)
        cur_gaps = coverage_gaps(reg, metric, cur_p, cells)
        base_gaps = coverage_gaps(reg, metric, base_p, cells)
        ckeys = [c.key_text for c in conflicts
                 if c.status == "open" and c.key[0] == metric
                 and c.key[1] in {mk, base_p.key}]
        rows.append({
            "month": mk, "prior_month": base_p.key,
            "base": round(base, 4), "current": round(cur, 4),
            "yoy": pct(cur, base),
            "coverage_flags": [f"{g.entity}:{g.kind}" for g in cur_gaps],
            "base_coverage_flags": [f"{g.entity}:{g.kind}" for g in base_gaps],
            "open_conflicts": ckeys,
        })
    return rows


# ---------------------------------------------------------------- 品类分析

@dataclass
class CategoryResult:
    metric: str
    category: str
    current_period: str
    base_period: str
    base_amount: float
    current_amount: float
    growth_rate: Optional[float]
    classification_version: str
    by_category: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"metric": self.metric, "category": self.category,
                "current_period": self.current_period,
                "base_period": self.base_period,
                "base_amount": self.base_amount,
                "current_amount": self.current_amount,
                "growth_rate": self.growth_rate,
                "classification_version": self.classification_version,
                "by_category": self.by_category}


def category_growth(reg: Registry, current_period: str | Period,
                    category: str | None = None,
                    base_period: str | Period | None = None,
                    classification_version: str | int | None = None,
                    as_of: date | None = None,
                    metric: str = "revenue") -> CategoryResult:
    """按指定分类版本把 SKU 事实归集到品类并计算同比。

    月度事实按各月末日适用的分类映射，因此追溯修正版本会同时重述比较期。
    """
    cp = current_period if isinstance(current_period, Period) else Period.parse(current_period)
    bp = (base_period if isinstance(base_period, Period)
          else Period.parse(base_period) if base_period else cp.prior_year())
    cells, _ = select_facts(reg.ds.facts, reg, as_of=as_of)

    # 与收入桥同一纪律：缺失/部分覆盖主体不进入品类同比
    gap_entities = {g.entity for g in coverage_gaps(reg, metric, cp, cells)}
    gap_entities |= {g.entity for g in coverage_gaps(reg, metric, bp, cells)}

    totals: dict[str, dict[str, float]] = {"base": {}, "current": {}}
    version_label = str(classification_version or "latest")
    for (m, pkey, ent, sku), fact in cells.items():
        if m != metric or fact.value is None or not sku:
            continue
        if ent in gap_entities:
            continue
        p = Period.parse(pkey)
        side: str | None = None
        day = p.end
        if pkey == bp.key or (p.kind == "month" and pkey in {x.key for x in bp.months()}):
            side, day = "base", p.end
        elif pkey == cp.key or (p.kind == "month" and pkey in {x.key for x in cp.months()}):
            side, day = "current", p.end
        if side is None:
            continue
        cat = reg.classification(sku, day, classification_version) or "未分类"
        totals[side][cat] = totals[side].get(cat, 0.0) + fact.value

    cats = sorted(set(totals["base"]) | set(totals["current"]))
    by_cat = []
    for cat in cats:
        b = totals["base"].get(cat, 0.0)
        c = totals["current"].get(cat, 0.0)
        by_cat.append({"category": cat, "base": round(b, 4),
                       "current": round(c, 4),
                       "growth_rate": pct(c, b)})
    target = category or "skincare"
    b = totals["base"].get(target, 0.0)
    c = totals["current"].get(target, 0.0)
    return CategoryResult(
        metric=metric, category=target, current_period=cp.key,
        base_period=bp.key, base_amount=b, current_amount=c,
        growth_rate=pct(c, b), classification_version=version_label,
        by_category=by_cat)
