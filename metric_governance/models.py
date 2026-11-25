"""领域模型：指标定义、事实、范围版本、谱系、会员、发布与行动。

全部为标准库 dataclass。空字符串在导入层表示“来源未提供值”，
业务判定时与显式的零严格区分。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


# ---------------------------------------------------------------- 基础记录

@dataclass(frozen=True)
class Definition:
    metric: str
    version: str
    formula: str
    effective_from: Optional[date]
    owner: str
    unit: str = ""
    description: str = ""


@dataclass(frozen=True)
class PeriodCaliber:
    """团队的收入/指标确认期间口径。"""
    team: str
    basis: str                 # settled-sales / order-date / shipment ...
    date_field: str            # settlement_date / order_date ...
    boundary: str              # 期间归属规则
    recognition_lag_days: Optional[int] = None
    fiscal_calendar: str = "calendar"
    note: str = ""


@dataclass(frozen=True)
class Fact:
    fact_id: str
    team: str
    metric: str
    period: str
    entity: str
    sku: str
    value: Optional[float]      # None 表示来源为空，绝不可解释为 0
    batch: str
    submitted_on: Optional[date] = None
    received_on: Optional[date] = None
    basis: str = ""
    note: str = ""
    source_file: str = ""


@dataclass(frozen=True)
class CoverageRow:
    """实体（门店/平台/SKU）在某版本区间内的范围或分类状态。"""
    entity: str
    kind: str                  # store | platform | sku | channel
    group: str
    state: str                 # comparable | new | closed | relocated | reclassified ...
    effective_from: Optional[date]
    effective_to: Optional[date]
    version: str


@dataclass(frozen=True)
class LineageEdge:
    """门店/商品谱系关系。

    relation 例如：
    - relocated-from : 新店是旧店的搬迁续体（可比）
    - successor-of / supersedes : 商品升级续接
    - new-line       : 全新商品线，无前期对应
    - migrates-to    : 品类迁移
    - bundle-of      : 组合装由哪些商品构成
    """
    entity: str
    kind: str                  # store | product
    relation: str
    related: str
    effective_from: Optional[date] = None
    confirmed: bool = False
    note: str = ""


@dataclass(frozen=True)
class MemberLink:
    link_version: str
    alias_id: str
    person_id: str
    platform: str = ""
    effective_from: Optional[date] = None
    status: str = "active"


@dataclass(frozen=True)
class MemberActivity:
    period: str
    alias_id: str
    active: bool = True
    events: int = 0


@dataclass(frozen=True)
class Report:
    report: str
    metric: str
    period: str
    value_text: str
    definition: str
    action: str
    state: str                 # 行动状态：issued | complete | review ...
    # 扩展列（缺失时为空）
    compare_period: str = ""
    published_on: Optional[date] = None
    owner: str = ""
    conclusion: str = ""
    snapshot: str = ""


@dataclass(frozen=True)
class ActionItem:
    action: str
    report: str
    owner: str
    title: str
    state: str
    created_on: Optional[date] = None
    due_on: Optional[date] = None
    completed_on: Optional[date] = None
    completion_note: str = ""


@dataclass(frozen=True)
class Confirmation:
    subject_type: str          # definition | scope | store | platform | category | product ...
    subject_key: str
    role: str                  # governance | channel-owner | product-owner
    person: str
    decision: str              # confirmed | changes-requested | rejected
    on: Optional[date]
    note: str = ""


@dataclass(frozen=True)
class Correction:
    """追溯修正事件。原始记录不删除，修正以新版本/新关联叠加。"""
    correction_id: str
    domain: str                # member_identity | store_status | product_classification | fact | scope
    target: str                # 受影响对象（report / S2 / P1 / link-v2 ...）
    summary: str
    detected_on: Optional[date]
    effective_from: Optional[date] = None
    new_version: str = ""
    status: str = "applied"    # proposed | applied | confirmed
    owner: str = ""


@dataclass
class ImportIssue:
    level: str                 # error | warning
    code: str
    message: str
    source_file: str = ""
    line: Optional[int] = None


@dataclass
class Dataset:
    """一次导入的全部输入。"""
    root: str = ""
    definitions: list[Definition] = field(default_factory=list)
    calibers: list[PeriodCaliber] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    coverage: list[CoverageRow] = field(default_factory=list)
    lineage: list[LineageEdge] = field(default_factory=list)
    member_links: list[MemberLink] = field(default_factory=list)
    member_activity: list[MemberActivity] = field(default_factory=list)
    reports: list[Report] = field(default_factory=list)
    actions: list[ActionItem] = field(default_factory=list)
    confirmations: list[Confirmation] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)
    resolutions: list[dict[str, str]] = field(default_factory=list)
    periods_extra: list[dict[str, str]] = field(default_factory=list)
    entities: list[dict[str, str]] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    snapshots_dir: str = ""

    def issues_of(self, level: str) -> list[ImportIssue]:
        return [i for i in self.issues if i.level == level]
