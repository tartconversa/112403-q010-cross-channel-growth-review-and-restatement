#!/usr/bin/env python3
"""生成一套内部勾稽的合成经营数据（全部标识与数值均为虚构）。

运行：python3 scripts/generate_demo_data.py [data_dir]

设计的案例主线：
- 2026-Q2 总同比 +12.4%，但同范围实体同比 -1.8%，增长来自抖音新平台(+142)
  与套装新品(+141)，并伴随退市品类(-93)、可比商品线下滑(-66)；
- 2026-Q3 发布的可比销售 +4.3% 只覆盖 S1+TM（京东迟到）；
  京东数据 + S0→S2 搬迁谱系确认后，可比同比重述为 -4.3%；
- 会员 L1 去重 37→40（+8.1%），追溯图谱 L2 为 38→39（+2.6%）；
- P1 在 v2 被归入 skincare，v3 追溯改为 sets，品类增速大幅变动。
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data"

# ------------------------------------------------------------- 季度 SKU 矩阵
# 每个实体: {sku: 季度金额}；基期/本期分别定义
Q2_BASE = {
    "S1": {"P1": 40, "P2": 150, "P3": 80, "P4": 50},
    "S0": {"P1": 25, "P2": 105, "P3": 50, "P4": 20},
    "TM": {"P1": 35, "P2": 135, "P3": 95, "P4": 15},
    "JD": {"P1": 20, "P2": 90, "P3": 82, "P4": 8},
}
Q2_CUR = {
    "S1": {"P1": 34, "P2": 140, "P3": 79, "P5": 51},
    "S0": {"P1": 22, "P2": 98, "P3": 40},
    "TM": {"P1": 38, "P2": 122, "P3": 88, "P5": 60},
    "JD": {"P1": 19, "P2": 86, "P3": 75, "P5": 30},
    "DY": {"P1": 20, "P2": 70, "P3": 40, "P5": 12},
}
Q3_BASE = {
    "S1": {"P1": 40, "P2": 150, "P3": 80, "P4": 50},
    "TM": {"P1": 35, "P2": 135, "P3": 95, "P4": 15},
    "JD": {"P1": 20, "P2": 90, "P3": 82, "P4": 8},
    "S0": {"P1": 26, "P2": 110, "P3": 52, "P4": 22},
}
Q3_CUR = {
    "S1": {"P1": 36, "P2": 130, "P3": 84, "P5": 50},
    "TM": {"P1": 40, "P2": 125, "P3": 101, "P5": 60},
    "JD": {"P1": 16, "P2": 76, "P3": 64, "P5": 30},
    "S2": {"P1": 20, "P2": 80, "P3": 35, "P5": 20},
    "DY": {"P1": 24, "P2": 80, "P3": 44, "P5": 12},
}

MONTHS = {
    "2025-Q2": ["2025-04", "2025-05", "2025-06"],
    "2026-Q2": ["2026-04", "2026-05", "2026-06"],
    "2025-Q3": ["2025-07", "2025-08", "2025-09"],
    "2026-Q3": ["2026-07", "2026-08", "2026-09"],
}
W_DEFAULT = [0.30, 0.31, 0.39]
W_Q2 = [0.24, 0.29, 0.47]          # 618 大促落在 6 月
W_SET_Q2 = [0.10, 0.20, 0.70]      # 套装高度集中在大促月
W_Q3 = [0.32, 0.33, 0.35]


def split_months(total: float, quarter: str, sku: str) -> list[int]:
    if quarter.endswith("Q2"):
        w = W_SET_Q2 if sku == "P5" else W_Q2
    else:
        w = W_Q3
    m1 = round(total * w[0])
    m2 = round(total * w[1])
    m3 = total - m1 - m2
    return [int(m1), int(m2), int(m3)]


def received_on(quarter: str, entity: str) -> str:
    year, q = quarter.split("-")
    if year == "2025":
        return "2025-07-08" if q == "Q2" else "2025-10-09"
    if q == "Q2":
        return "2026-07-06"
    # 2026-Q3：京东渠道文件迟到（10-20），其余 10-05
    if entity == "JD":
        return "2026-10-20"
    return "2026-10-05"


def write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_fact_rows() -> list[dict]:
    rows: list[dict] = []
    fid = 0
    for quarter, matrices in [("2025-Q2", Q2_BASE), ("2026-Q2", Q2_CUR),
                              ("2025-Q3", Q3_BASE), ("2026-Q3", Q3_CUR)]:
        for entity, skus in matrices.items():
            team = "offline" if entity.startswith("S") else "online"
            for sku, total in skus.items():
                for month, val in zip(MONTHS[quarter], split_months(total, quarter, sku)):
                    fid += 1
                    rows.append({
                        "fact_id": f"F{fid:04d}", "team": team,
                        "metric": "revenue", "period": month,
                        "entity": entity, "sku": sku, "value": val,
                        "basis": "settled-sales",
                        "submitted_on": received_on(quarter, entity),
                        "received_on": received_on(quarter, entity),
                        "batch": f"{team}-{quarter}",
                        "note": "",
                    })
    return rows


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "submissions").mkdir(exist_ok=True)

    facts = build_fact_rows()

    # 按团队拆分提交文件
    offline = [r for r in facts if r["team"] == "offline"]
    online = [r for r in facts if r["team"] == "online"]
    fact_header = ["fact_id", "team", "metric", "period", "entity", "sku",
                   "value", "basis", "submitted_on", "received_on", "batch", "note"]
    write_csv(DATA / "submissions" / "offline_pos.csv", fact_header, offline)
    write_csv(DATA / "submissions" / "online_platform.csv", fact_header, online)

    # 冲突 1（已裁决）：TM 2026-06 P2，重报批次给出 62，原批次为勾稽值
    orig = next(r for r in online if r["entity"] == "TM"
                and r["period"] == "2026-06" and r["sku"] == "P2")
    conflict_resolved = dict(orig)
    conflict_resolved.update({
        "fact_id": "F-CONF-Q2", "value": 62,
        "batch": "online-tm-resubmit", "team": "online",
        "submitted_on": "2026-07-08", "received_on": "2026-07-08",
        "note": "重报文件与结算口径不一致",
    })
    write_csv(DATA / "submissions" / "conflict_tm_resubmit.csv",
              fact_header, [conflict_resolved])

    # 冲突 2（未裁决）：DY 2026-08 P2，两个批次 27(勾稽) vs 39
    dy = next(r for r in online if r["entity"] == "DY"
              and r["period"] == "2026-08" and r["sku"] == "P2")
    conflict_open = dict(dy)
    conflict_open.update({
        "fact_id": "F-CONF-DY", "value": 39,
        "batch": "online-dy-flash", "submitted_on": "2026-10-06",
        "received_on": "2026-10-06", "note": "直播闪购净额/总额口径争议",
    })
    write_csv(DATA / "submissions" / "conflict_dy_open.csv",
              fact_header, [conflict_open])

    # 部分期间覆盖：XHS 新平台 8 月上线，Q3 只报送了 8 月，9 月缺失
    xhs_rows = [{
        "fact_id": "F-XHS-202608-P2", "team": "online", "metric": "revenue",
        "period": "2026-08", "entity": "XHS", "sku": "P2", "value": 18,
        "basis": "settled-sales", "submitted_on": "2026-10-05",
        "received_on": "2026-10-05", "batch": "online-xhs-partial",
        "note": "季度文件仅覆盖至 8 月",
    }]
    write_csv(DATA / "submissions" / "online_xhs_partial.csv",
              fact_header, xhs_rows)

    # 已裁决冲突的治理记录（引用原始批次 fact_id）
    write_csv(DATA / "resolutions.csv",
              ["conflict_key", "chosen_fact_id", "chosen_value", "person",
               "decided_on", "note"],
              [{"conflict_key": "revenue|2026-06|TM|P2",
                "chosen_fact_id": orig["fact_id"], "chosen_value": orig["value"],
                "person": "孙敏（指标治理）", "decided_on": "2026-07-15",
                "note": "按 v1 settled-sales 口径采纳结算批次，剔除直播下单口径差异"}])

    # --------------------------------------------------------- 会员数据
    links_header = ["link_version", "alias_id", "person_id", "platform", "from", "status"]
    links: list[dict] = []
    activity: list[dict] = []
    platforms = ["tm", "jd", "wx", "pos"]

    def add_alias(alias: str, l1_person: str, l2_person: str,
                  active_25q2: bool, active_26q2: bool, pf: str) -> None:
        links.append({"link_version": "L1", "alias_id": alias,
                      "person_id": l1_person, "platform": pf,
                      "from": "2025-01-01", "status": "active"})
        links.append({"link_version": "L2", "alias_id": alias,
                      "person_id": l2_person, "platform": pf,
                      "from": "2026-10-16", "status": "active"})
        for period, on in [("2025-Q2", active_25q2), ("2026-Q2", active_26q2)]:
            if on:
                activity.append({"period": period, "alias_id": alias,
                                 "active": "1", "events": 12})

    for i in range(1, 36):
        add_alias(f"u{i:02d}", f"G{i:02d}", f"G{i:02d}", True, True,
                  platforms[i % len(platforms)])
    # 漏合并 1：a 两期活跃，b 仅本期 -> L1(1,2) L2(1,1)
    add_alias("mm1a", "MM1_A", "MM1", True, True, "tm")
    add_alias("mm1b", "MM1_B", "MM1", False, True, "wx")
    # 漏合并 2：两个别名都仅本期活跃 -> L1(0,2) L2(0,1)
    add_alias("mm2a", "MM2_A", "MM2", False, True, "jd")
    add_alias("mm2b", "MM2_B", "MM2", False, True, "dy")
    # 错误合并：两人被并成一人，两期都活跃 -> L1(1,1) L2(2,2)
    add_alias("wm1a", "WM1", "WM1_A", True, True, "pos")
    add_alias("wm1b", "WM1", "WM1_B", True, True, "wx")

    write_csv(DATA / "member_links.csv", links_header, links)
    write_csv(DATA / "member_activity.csv",
              ["period", "alias_id", "active", "events"], activity)

    print(f"generated {len(facts)} fact rows, {len(links)} link rows, "
          f"{len(activity)} activity rows under {DATA}")


if __name__ == "__main__":
    main()
