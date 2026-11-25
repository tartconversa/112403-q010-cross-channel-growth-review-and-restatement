"""会员关联版本与去重活跃会员计算。

不同版本的身份图谱会把同一平台账号合并/拆分。本模块保证：
- 每个关联版本独立计算，不混用映射；
- 追溯修正以新版本叠加，旧版本结果仍可复算（原发布版本保留）。
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Dataset
from .analytics import pct


@dataclass
class MemberCount:
    link_version: str
    period: str
    active_aliases: int
    persons: int
    unmapped_aliases: int

    def to_dict(self) -> dict:
        return {"link_version": self.link_version, "period": self.period,
                "active_aliases": self.active_aliases, "persons": self.persons,
                "unmapped_aliases": self.unmapped_aliases}


class MemberEngine:
    def __init__(self, ds: Dataset):
        self.ds = ds

    def versions(self) -> list[str]:
        seen: list[str] = []
        for link in self.ds.member_links:
            if link.link_version not in seen:
                seen.append(link.link_version)
        return seen

    def latest_version(self) -> str | None:
        return self.versions()[-1] if self.versions() else None

    def count(self, period: str, link_version: str | None = None) -> MemberCount:
        version = link_version or self.latest_version()
        mapping = {l.alias_id: l.person_id
                   for l in self.ds.member_links
                   if l.link_version == version and l.status == "active"}
        active_aliases = {a.alias_id for a in self.ds.member_activity
                          if a.period == period and a.active}
        persons: set[str] = set()
        unmapped = 0
        for alias in active_aliases:
            person = mapping.get(alias)
            if person is None:
                unmapped += 1
                persons.add(f"__unmapped__:{alias}")
            else:
                persons.add(person)
        return MemberCount(version or "", period, len(active_aliases),
                           len(persons), unmapped)

    def growth(self, period: str, compare_period: str,
               link_version: str | None = None) -> dict:
        cur = self.count(period, link_version)
        base = self.count(compare_period, link_version)
        return {"period": period, "compare_period": compare_period,
                "link_version": link_version or self.latest_version(),
                "base": base.to_dict(), "current": cur.to_dict(),
                "growth_rate": pct(cur.persons, base.persons)}

    def version_diff(self, period: str, compare_period: str,
                    old_version: str, new_version: str) -> dict:
        old = self.growth(period, compare_period, old_version)
        new = self.growth(period, compare_period, new_version)
        return {"old": old, "new": new,
                "growth_delta_pp": (
                    None if old["growth_rate"] is None or new["growth_rate"] is None
                    else new["growth_rate"] - old["growth_rate"]),
                "persons_delta_current": (
                    new["current"]["persons"] - old["current"]["persons"])}
