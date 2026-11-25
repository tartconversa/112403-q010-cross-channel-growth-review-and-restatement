"""全域经营指标口径治理与管理层结论重述应用（仅依赖 Python 标准库）。"""
from .io_csv import load_dataset
from .registry import Registry
from .workflow import WorkflowState
from .analytics import revenue_bridge, category_growth
from .members import MemberEngine
from .reopen import assess_report

__version__ = "1.0.0"
__all__ = [
    "load_dataset", "Registry", "WorkflowState",
    "revenue_bridge", "category_growth", "MemberEngine", "assess_report",
]
