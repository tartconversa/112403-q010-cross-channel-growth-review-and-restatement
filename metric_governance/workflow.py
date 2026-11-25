"""可写工作流状态：角色确认、冲突裁决、重开个案与新增行动。

种子数据来自 CSV（只读）；CLI 产生的决定写入 JSON 覆盖层，
从而保证原始发布快照与行动完成记录不会被改写。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional


def _today() -> str:
    return date.today().isoformat()


@dataclass
class WorkflowState:
    path: Optional[str] = None
    confirmations: list[dict[str, Any]] = field(default_factory=list)
    resolutions: list[dict[str, Any]] = field(default_factory=list)
    reopen_cases: list[dict[str, Any]] = field(default_factory=list)
    extra_actions: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------ io
    @classmethod
    def load(cls, path: str | Path | None) -> "WorkflowState":
        if path is None:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls(path=str(p))
        data = json.loads(p.read_text(encoding="utf-8"))
        data.pop("path", None)  # path 以本次加载参数为准，不接受文件内覆盖
        return cls(path=str(p), **{k: v for k, v in data.items()
                                  if k in cls.__dataclass_fields__})

    def save(self) -> None:
        if not self.path:
            return
        p = Path(self.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                     encoding="utf-8")

    # ------------------------------------------------------------ commands
    def confirm(self, subject_type: str, subject_key: str, role: str,
                person: str, decision: str = "confirmed",
                note: str = "", on: str | None = None) -> dict[str, Any]:
        record = {
            "subject_type": subject_type, "subject_key": subject_key,
            "role": role, "person": person, "decision": decision,
            "on": on or _today(), "note": note,
        }
        # 同一对象的最新决定覆盖旧决定（保留历史在 history 中）
        history_key = "_history"
        prior = [c for c in self.confirmations
                 if c["subject_type"] == subject_type
                 and c["subject_key"] == subject_key]
        if prior:
            record[history_key] = prior[-1].get(history_key, []) + [
                {k: v for k, v in prior[-1].items() if k != history_key}]
            self.confirmations = [c for c in self.confirmations
                                  if not (c["subject_type"] == subject_type
                                          and c["subject_key"] == subject_key)]
        self.confirmations.append(record)
        self.save()
        return record

    def resolve_conflict(self, conflict_key: str, chosen_fact_id: str = "",
                         chosen_value: float | None = None, person: str = "",
                         note: str = "") -> dict[str, Any]:
        record = {
            "conflict_key": conflict_key, "chosen_fact_id": chosen_fact_id,
            "chosen_value": chosen_value, "person": person,
            "decided_on": _today(), "note": note,
        }
        self.resolutions = [r for r in self.resolutions
                            if r["conflict_key"] != conflict_key]
        self.resolutions.append(record)
        self.save()
        return record

    def open_reopen_case(self, report: str, reasons: list[str],
                         original: dict[str, Any], restated: dict[str, Any],
                         owner: str = "", create_action: bool = True) -> dict[str, Any]:
        existing = next((c for c in self.reopen_cases if c["report"] == report), None)
        if existing and existing.get("status") == "reopened":
            return existing
        case = {
            "report": report, "status": "reopened",
            "opened_on": _today(), "reasons": reasons,
            "original": original, "restated": restated, "owner": owner,
        }
        self.reopen_cases = [c for c in self.reopen_cases if c["report"] != report]
        self.reopen_cases.append(case)
        if create_action:
            action_id = f"A-REOPEN-{report}"
            if not any(a["action"] == action_id for a in self.extra_actions):
                self.extra_actions.append({
                    "action": action_id, "report": report,
                    "owner": owner or "analytics-governance",
                    "title": f"重述 {report} 并重新发布管理层结论",
                    "state": "issued", "created_on": _today(),
                    "due_on": "", "completed_on": "", "completion_note": "",
                    "kind": "reopen-followup",
                })
        self.save()
        return case

    def complete_action(self, action_id: str, person: str = "",
                        note: str = "") -> dict[str, Any] | None:
        for a in self.extra_actions:
            if a["action"] == action_id:
                a["state"] = "complete"
                a["completed_on"] = _today()
                a["completed_by"] = person
                a["completion_note"] = note
                self.save()
                return a
        return None
