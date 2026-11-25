"""治理注册表：口径版本、范围区间、商品分类版本、谱系与确认状态查询。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from .models import Confirmation, Dataset
from .periods import Period
from .workflow import WorkflowState


@dataclass
class EntityMatch:
    """基期实体与本期实体的匹配关系。"""
    base_entity: str
    current_entity: str
    method: str               # same-id | lineage:<relation>
    confirmed: bool


class Registry:
    def __init__(self, dataset: Dataset, state: WorkflowState | None = None,
                 as_of: date | None = None):
        self.ds = dataset
        self.state = state or WorkflowState()
        self.as_of = as_of
        self._names = {e.get("id", ""): e.get("name", "")
                       for e in dataset.entities if e.get("id")}

    def display_name(self, entity: str) -> str:
        return self._names.get(entity, "") or entity

    # ---------------------------------------------------------- definitions
    def definition(self, metric: str, version: str | None = None):
        rows = [d for d in self.ds.definitions if d.metric == metric]
        if version:
            pinned = [d for d in rows if d.version == version]
            if pinned:
                return pinned[0]
        if not rows:
            return None
        return sorted(rows, key=lambda d: d.version)[-1]

    def metrics(self) -> list[str]:
        seen: list[str] = []
        for d in self.ds.definitions:
            if d.metric not in seen:
                seen.append(d.metric)
        return seen

    def caliber_for_team(self, team: str):
        for c in self.ds.calibers:
            if c.team == team:
                return c
        return None

    # ---------------------------------------------------------- confirmations
    def effective_confirmation(self, subject_type: str,
                               subject_key: str) -> Optional[dict]:
        """种子确认 + JSON 覆盖层中该对象的最新有效决定。

        设置 ``as_of`` 时，只采用该日期之前已经作出的确认，
        以忠实还原发布时点的治理状态。
        """
        def visible(on_text: str) -> bool:
            if self.as_of is None or not on_text:
                return True
            try:
                return date.fromisoformat(on_text[:10]) <= self.as_of
            except ValueError:
                return True

        overlay = [c for c in self.state.confirmations
                   if c["subject_type"] == subject_type
                   and c["subject_key"] == subject_key
                   and visible(str(c.get("on", "")))]
        if overlay:
            return overlay[-1]
        rows = [c for c in self.ds.confirmations
                if c.subject_type == subject_type and c.subject_key == subject_key
                and (self.as_of is None or c.on is None or c.on <= self.as_of)]
        if rows:
            latest = sorted(rows, key=lambda c: c.on or date.min)[-1]
            return {"subject_type": latest.subject_type,
                    "subject_key": latest.subject_key, "role": latest.role,
                    "person": latest.person, "decision": latest.decision,
                    "on": latest.on.isoformat() if latest.on else "",
                    "note": latest.note}
        return None

    def is_confirmed(self, subject_type: str, subject_key: str) -> bool:
        c = self.effective_confirmation(subject_type, subject_key)
        return bool(c and c.get("decision") == "confirmed")

    # ---------------------------------------------------------- coverage
    def coverage_for(self, entity: str) -> list:
        return [c for c in self.ds.coverage if c.entity == entity]

    def state_on(self, entity: str, day: date,
                 max_version: str | int | None = None) -> Optional[str]:
        row = self._row_on(entity, day, max_version)
        return row.state if row else None

    def _row_on(self, entity: str, day: date,
                max_version: str | int | None = None):
        candidates = []
        for row in self.ds.coverage:
            if row.entity != entity:
                continue
            if row.effective_from and day < row.effective_from:
                continue
            if row.effective_to and day > row.effective_to:
                continue
            if max_version is not None:
                try:
                    if int(float(row.version)) > int(float(max_version)):
                        continue
                except ValueError:
                    pass
            candidates.append(row)
        if not candidates:
            return None
        # 版本号优先（追溯修正以新版本叠加），其次取生效日最新
        return sorted(candidates,
                      key=lambda r: (self._version_num(r.version),
                                     r.effective_from or date.min))[-1]

    @staticmethod
    def _version_num(v: str) -> float:
        try:
            return float(str(v).lstrip("vV"))
        except ValueError:
            return 0.0

    def state_in_period(self, entity: str, period: Period | str,
                        max_version: str | int | None = None) -> Optional[str]:
        p = period if isinstance(period, Period) else Period.parse(period)
        return self.state_on(entity, p.end, max_version)

    def classification(self, sku: str, day: date,
                       max_version: str | int | None = None) -> Optional[str]:
        """返回 SKU 在某日适用版本下的品类（coverage.group）。"""
        row = self._row_on(sku, day, max_version)
        return row.group if row and row.kind == "sku" else None

    # ---------------------------------------------------------- lineage
    def lineage_for(self, entity: str) -> list:
        return [e for e in self.ds.lineage if e.entity == entity]

    def _edge_effectively_confirmed(self, edge) -> bool:
        if edge.confirmed:
            return True
        return self.is_confirmed("lineage", f"{edge.entity}:{edge.relation}:{edge.related}")

    def match_entities(self, base_period: Period | str,
                       current_period: Period | str,
                       max_coverage_version: str | int | None = None
                       ) -> list[EntityMatch]:
        """建立基期→本期实体匹配。

        顺序即优先级：已确认的门店搬迁/续接谱系最先，其次同 ID。
        桥接层用 used 集合保证每个实体只被配对一次，因此谱系关系
        不会被同 ID 的“新店/闭店”记录抢占。
        """
        bp = base_period if isinstance(base_period, Period) else Period.parse(base_period)
        cp = current_period if isinstance(current_period, Period) else Period.parse(current_period)

        known = {c.entity for c in self.ds.coverage if c.kind in
                 {"store", "platform", "channel"}}
        matches: list[EntityMatch] = []
        matched_base: set[str] = set()
        matched_current: set[str] = set()

        # 1) 已确认的门店谱系：本期实体 -> 基期实体（搬迁/续体）
        for edge in self.ds.lineage:
            if edge.kind != "store":
                continue
            if edge.relation not in {"relocated-from", "successor-of",
                                     "renamed-from", "continues"}:
                continue
            # 谱系关系必须在本期结束前已经生效，否则不得用于该期配对
            if edge.effective_from and edge.effective_from > cp.end:
                continue
            if not self._edge_effectively_confirmed(edge):
                continue
            cur_ent, base_ent = edge.entity, edge.related
            matches.append(EntityMatch(
                base_ent, cur_ent, f"lineage:{edge.relation}", True))
            matched_base.add(base_ent)
            matched_current.add(cur_ent)

        # 2) 同 ID（含仅在一侧登记范围状态的实体，交由桥接判定范围增减）
        for ent in sorted(known):
            in_base = self._row_on(ent, bp.end, max_coverage_version) is not None
            in_cur = self._row_on(ent, cp.end, max_coverage_version) is not None
            if not (in_base or in_cur):
                continue
            if ent in matched_base or ent in matched_current:
                continue
            matches.append(EntityMatch(ent, ent, "same-id", True))
            if in_base:
                matched_base.add(ent)
            if in_cur:
                matched_current.add(ent)

        return matches

    def expected_reporting_entities(self, period: Period | str,
                                    metric: str = "revenue") -> list[str]:
        """该期间制度上应报送指标事实的实体（存续/新增的门店与平台）。"""
        p = period if isinstance(period, Period) else Period.parse(period)
        expected: list[str] = []
        active_states = {"comparable", "new", "active", "renovated",
                         "relocated", "operating"}
        for row in self.ds.coverage:
            if row.kind not in {"store", "platform", "channel"}:
                continue
            if row.state not in active_states:
                continue
            # 区间与期间相交且不是期间结束前已失效
            if row.effective_from and row.effective_from > p.end:
                continue
            if row.effective_to and row.effective_to < p.start:
                continue
            if row.entity not in expected:
                expected.append(row.entity)
        return sorted(expected)
