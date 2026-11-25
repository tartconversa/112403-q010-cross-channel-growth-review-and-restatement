"""CSV 导入：指标事实、期间口径、范围版本、谱系、会员、发布与行动。

设计原则：
- 空单元格 => None（来源未提供），任何聚合都不得当成 0；
- 单个文件缺失：跳过（对应领域记录为空），不报错；
- 行级解析错误登记为 ImportIssue，不中断整批导入；
- 只依赖标准库 csv/datetime。
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from .models import (
    ActionItem, Confirmation, Correction, CoverageRow, Dataset, Definition,
    Fact, ImportIssue, LineageEdge, MemberActivity, MemberLink, PeriodCaliber,
    Report,
)


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        # 容忍 2026/07/01 之类
        parts = text[:10].replace("/", "-").split("-")
        if len(parts) == 3:
            try:
                return date(int(parts[0]), int(parts[1]), int(parts[2]))
            except ValueError:
                return None
        return None


def _text(row: dict[str, str], key: str, default: str = "") -> str:
    value = row.get(key)
    return default if value is None else value.strip()


def _opt_float(row: dict[str, str], key: str) -> Optional[float]:
    text = _text(row, key)
    if text == "":
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _opt_int(row: dict[str, str], key: str) -> Optional[int]:
    value = _opt_float(row, key)
    return int(value) if value is not None else None


class CsvLoader:
    def __init__(self, root: Path):
        self.root = root
        self.dataset = Dataset(root=str(root))

    def read_dicts(self, path: Path) -> tuple[list[dict[str, str]], list[str]]:
        if not path.exists():
            return [], []
        try:
            with path.open(encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh, strict=True)
                headers = reader.fieldnames or []
                rows: list[dict[str, str]] = []
                for idx, row in enumerate(reader, start=2):
                    if None in row:
                        self.dataset.issues.append(ImportIssue(
                            "warning", "extra-columns",
                            f"{path.name}:{idx} 存在表头外字段，已忽略", path.name, idx))
                    rows.append({k: (v or "").strip() for k, v in row.items()
                                 if k is not None})
                return rows, list(headers)
        except csv.Error as exc:
            self.dataset.issues.append(ImportIssue(
                "error", "csv-parse", f"{path.name} 解析失败: {exc}", path.name))
            return [], []

    def load_file(self, name: str, mapper: Callable[[dict[str, str], "CsvLoader"], Any],
                  required: bool = False) -> "CsvLoader":
        path = self.root / name
        if not path.exists():
            if required:
                self.dataset.issues.append(ImportIssue(
                    "error", "missing-file", f"缺少必需文件 {name}", name))
            return self
        rows, _ = self.read_dicts(path)
        for row in rows:
            try:
                obj = mapper(row, self)
                if obj is not None:
                    self._append(name, obj)
            except (ValueError, KeyError) as exc:
                self.dataset.issues.append(ImportIssue(
                    "error", "row-parse", f"{name} 行解析失败: {exc}", name))
        return self

    def _append(self, name: str, obj: Any) -> None:
        d = self.dataset
        if name == "definitions.csv":
            d.definitions.append(obj)
        elif name == "period_calibers.csv":
            d.calibers.append(obj)
        elif name == "coverage.csv":
            d.coverage.append(obj)
        elif name == "lineage.csv":
            d.lineage.append(obj)
        elif name == "member_links.csv":
            d.member_links.append(obj)
        elif name == "member_activity.csv":
            d.member_activity.append(obj)
        elif name == "reports.csv":
            d.reports.append(obj)
        elif name == "actions.csv":
            d.actions.append(obj)
        elif name == "confirmations.csv":
            d.confirmations.append(obj)
        elif name == "corrections.csv":
            d.corrections.append(obj)
        elif name == "resolutions.csv":
            d.resolutions.append(obj)
        elif name == "periods.csv":
            d.periods_extra.append(obj)  # type: ignore[arg-type]
        elif name == "entities.csv":
            d.entities.append(obj)  # type: ignore[arg-type]

    # ---------------------------------------------------------- mappers

    @staticmethod
    def map_definition(r: dict[str, str], ld: "CsvLoader") -> Definition:
        return Definition(
            metric=_text(r, "metric"), version=_text(r, "version") or "v1",
            formula=_text(r, "formula"), effective_from=parse_date(r.get("from")),
            owner=_text(r, "owner"), unit=_text(r, "unit"),
            description=_text(r, "description"))

    @staticmethod
    def map_caliber(r: dict[str, str], ld: "CsvLoader") -> PeriodCaliber:
        return PeriodCaliber(
            team=_text(r, "team"), basis=_text(r, "basis"),
            date_field=_text(r, "date_field"), boundary=_text(r, "boundary"),
            recognition_lag_days=_opt_int(r, "recognition_lag_days"),
            fiscal_calendar=_text(r, "fiscal_calendar") or "calendar",
            note=_text(r, "note"))

    @staticmethod
    def map_coverage(r: dict[str, str], ld: "CsvLoader") -> CoverageRow:
        return CoverageRow(
            entity=_text(r, "entity"), kind=_text(r, "kind"),
            group=_text(r, "group"), state=_text(r, "state"),
            effective_from=parse_date(r.get("from")),
            effective_to=parse_date(r.get("to")),
            version=_text(r, "version") or "1")

    @staticmethod
    def map_lineage(r: dict[str, str], ld: "CsvLoader") -> LineageEdge:
        confirmed_raw = _text(r, "confirmed").lower()
        return LineageEdge(
            entity=_text(r, "entity"), kind=_text(r, "kind"),
            relation=_text(r, "relation"), related=_text(r, "related"),
            effective_from=parse_date(r.get("from")),
            confirmed=confirmed_raw in {"1", "true", "yes", "y", "confirmed"},
            note=_text(r, "note"))

    @staticmethod
    def map_member_link(r: dict[str, str], ld: "CsvLoader") -> MemberLink:
        return MemberLink(
            link_version=_text(r, "link_version") or _text(r, "version") or "L1",
            alias_id=_text(r, "alias_id"), person_id=_text(r, "person_id"),
            platform=_text(r, "platform"),
            effective_from=parse_date(r.get("from")),
            status=_text(r, "status") or "active")

    @staticmethod
    def map_member_activity(r: dict[str, str], ld: "CsvLoader") -> MemberActivity:
        active_text = _text(r, "active").lower()
        return MemberActivity(
            period=_text(r, "period"), alias_id=_text(r, "alias_id"),
            active=active_text not in {"0", "false", "no", "inactive"},
            events=_opt_int(r, "events") or 0)

    @staticmethod
    def map_report(r: dict[str, str], ld: "CsvLoader") -> Report:
        return Report(
            report=_text(r, "report"), metric=_text(r, "metric"),
            period=_text(r, "period"), value_text=_text(r, "value"),
            definition=_text(r, "definition"), action=_text(r, "action"),
            state=_text(r, "state"),
            compare_period=_text(r, "compare_period"),
            published_on=parse_date(r.get("published_on")),
            owner=_text(r, "owner"), conclusion=_text(r, "conclusion"),
            snapshot=_text(r, "snapshot"))

    @staticmethod
    def map_action(r: dict[str, str], ld: "CsvLoader") -> ActionItem:
        return ActionItem(
            action=_text(r, "action"), report=_text(r, "report"),
            owner=_text(r, "owner"), title=_text(r, "title"),
            state=_text(r, "state"),
            created_on=parse_date(r.get("created_on")),
            due_on=parse_date(r.get("due_on")),
            completed_on=parse_date(r.get("completed_on")),
            completion_note=_text(r, "completion_note"))

    @staticmethod
    def map_confirmation(r: dict[str, str], ld: "CsvLoader") -> Confirmation:
        return Confirmation(
            subject_type=_text(r, "subject_type"),
            subject_key=_text(r, "subject_key"),
            role=_text(r, "role"), person=_text(r, "person"),
            decision=_text(r, "decision") or "confirmed",
            on=parse_date(r.get("on") or r.get("date")),
            note=_text(r, "note"))

    @staticmethod
    def map_correction(r: dict[str, str], ld: "CsvLoader") -> Correction:
        return Correction(
            correction_id=_text(r, "correction_id"),
            domain=_text(r, "domain"), target=_text(r, "target"),
            summary=_text(r, "summary"),
            detected_on=parse_date(r.get("detected_on")),
            effective_from=parse_date(r.get("effective_from")),
            new_version=_text(r, "new_version"),
            status=_text(r, "status") or "applied",
            owner=_text(r, "owner"))

    @staticmethod
    def map_resolution(r: dict[str, str], ld: "CsvLoader") -> dict[str, str]:
        return dict(r)

    @staticmethod
    def map_period_extra(r: dict[str, str], ld: "CsvLoader") -> dict[str, str]:
        return dict(r)

    @staticmethod
    def map_entity(r: dict[str, str], ld: "CsvLoader") -> dict[str, str]:
        return dict(r)

    # ---------------------------------------------------------- facts

    def load_facts(self) -> "CsvLoader":
        """加载 facts.csv 以及 submissions/*.csv 各团队分批提交。"""
        candidates: list[Path] = []
        facts_file = self.root / "facts.csv"
        if facts_file.exists():
            candidates.append(facts_file)
        inbox = self.root / "submissions"
        if inbox.is_dir():
            candidates.extend(sorted(inbox.glob("*.csv")))
        seen_ids: set[str] = set()
        for path in candidates:
            rows, _ = self.read_dicts(path)
            default_batch = path.stem
            for i, r in enumerate(rows, start=2):
                fid = _text(r, "fact_id") or f"{path.stem}:{i}"
                if fid in seen_ids:
                    # 同一 fact_id 重复导入视为同一来源的重发，跳过
                    continue
                seen_ids.add(fid)
                value = _opt_float(r, "value")
                if _text(r, "value") != "" and value is None:
                    self.dataset.issues.append(ImportIssue(
                        "error", "bad-number",
                        f"{path.name}:{i} 数值无法解析: {_text(r, 'value')!r}",
                        path.name, i))
                fact = Fact(
                    fact_id=fid, team=_text(r, "team") or path.stem.split("_")[0],
                    metric=_text(r, "metric") or "revenue",
                    period=_text(r, "period"), entity=_text(r, "entity"),
                    sku=_text(r, "sku"), value=value,
                    batch=_text(r, "batch") or default_batch,
                    submitted_on=parse_date(r.get("submitted_on")),
                    received_on=parse_date(r.get("received_on")),
                    basis=_text(r, "basis"), note=_text(r, "note"),
                    source_file=path.name)
                if not fact.period:
                    self.dataset.issues.append(ImportIssue(
                        "error", "missing-period", f"{path.name}:{i} 缺少 period",
                        path.name, i))
                    continue
                self.dataset.facts.append(fact)
        return self


FILE_MAP = [
    ("definitions.csv", CsvLoader.map_definition),
    ("period_calibers.csv", CsvLoader.map_caliber),
    ("coverage.csv", CsvLoader.map_coverage),
    ("lineage.csv", CsvLoader.map_lineage),
    ("member_links.csv", CsvLoader.map_member_link),
    ("member_activity.csv", CsvLoader.map_member_activity),
    ("reports.csv", CsvLoader.map_report),
    ("actions.csv", CsvLoader.map_action),
    ("confirmations.csv", CsvLoader.map_confirmation),
    ("corrections.csv", CsvLoader.map_correction),
    ("resolutions.csv", CsvLoader.map_resolution),
    ("periods.csv", CsvLoader.map_period_extra),
    ("entities.csv", CsvLoader.map_entity),
]


def load_dataset(root: str | Path) -> Dataset:
    """从目录导入全部可用登记表。目录可以是 data/ 或 samples/。"""
    path = Path(root)
    loader = CsvLoader(path)
    for name, mapper in FILE_MAP:
        loader.load_file(name, mapper)
    loader.load_facts()
    snap = path / "snapshots"
    if snap.is_dir():
        loader.dataset.snapshots_dir = str(snap)
    return loader.dataset
