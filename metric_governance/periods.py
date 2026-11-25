"""期间解析、同比期间与季度/月份口径。

支持的规范期间键：
- 季度：``2026-Q2``
- 月份：``2026-06``
- 年度：``2026``

所有日期均为公历 date，应用只使用 Python 标准库。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Iterator

_QUARTER_RE = re.compile(r"^(\d{4})-[Qq]([1-4])$")
_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_YEAR_RE = re.compile(r"^(\d{4})$")


def _quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    end_month = start_month + 2
    if end_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, end_month + 1, 1)
        # 下月 1 号减一天
        from datetime import timedelta

        end = end - timedelta(days=1)
    return start, end


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    from datetime import timedelta

    return date(year, month + 1, 1) - timedelta(days=1)


@dataclass(frozen=True, order=True)
class Period:
    """一个报告期间。"""

    key: str
    year: int
    kind: str  # quarter | month | year
    index: int  # quarter 1-4 / month 1-12 / 0 for year
    start: date
    end: date

    @classmethod
    def parse(cls, value: str) -> "Period":
        text = (value or "").strip()
        if m := _QUARTER_RE.match(text):
            year, q = int(m.group(1)), int(m.group(2))
            start, end = _quarter_bounds(year, q)
            return cls(f"{year}-Q{q}", year, "quarter", q, start, end)
        if m := _MONTH_RE.match(text):
            year, month = int(m.group(1)), int(m.group(2))
            if not 1 <= month <= 12:
                raise ValueError(f"非法月份期间: {value!r}")
            return cls(f"{year}-{month:02d}", year, "month", month,
                       date(year, month, 1), _month_end(year, month))
        if m := _YEAR_RE.match(text):
            year = int(m.group(1))
            return cls(f"{year}", year, "year", 0, date(year, 1, 1), date(year, 12, 31))
        raise ValueError(f"无法识别的期间格式: {value!r}（支持 2026-Q2 / 2026-06 / 2026）")

    def prior_year(self) -> "Period":
        """同一口径的去年同期。"""
        if self.kind == "quarter":
            return Period.parse(f"{self.year - 1}-Q{self.index}")
        if self.kind == "month":
            return Period.parse(f"{self.year - 1}-{self.index:02d}")
        return Period.parse(f"{self.year - 1}")

    def months(self) -> list["Period"]:
        """期间覆盖的月份（季度返回 3 个月，月份返回自身）。"""
        if self.kind == "month":
            return [self]
        if self.kind == "quarter":
            start_month = (self.index - 1) * 3 + 1
            return [Period.parse(f"{self.year}-{m:02d}")
                    for m in range(start_month, start_month + 3)]
        return [Period.parse(f"{self.year}-{m:02d}") for m in range(1, 13)]

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def coverage_days(self) -> int:
        return (self.end - self.start).days + 1

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.key


def period_keys_between(start: str, end: str, kind: str = "month") -> Iterator[str]:
    """枚举两个期间键之间（含端点）的连续期间。"""
    a = Period.parse(start)
    b = Period.parse(end)
    if kind == "month" or a.kind == "month":
        y, m = a.year, a.index
        while (y, m) <= (b.year, b.index):
            yield f"{y}-{m:02d}"
            m += 1
            if m == 13:
                y, m = y + 1, 1
        return
    if a.kind == "quarter":
        y, q = a.year, a.index
        while (y, q) <= (b.year, b.index):
            yield f"{y}-Q{q}"
            q += 1
            if q == 5:
                y, q = y + 1, 1
        return
    yield from [a.key]
