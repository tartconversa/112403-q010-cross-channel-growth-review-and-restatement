# 全域经营指标口径治理与管理层结论重述

管理层每月同时看线上、线下、会员与品类增长，但各团队收入确认日、会员去重方式、
商品归类口径不同；新门店/新平台和大促组合会抬高汇总同比，即使多数可比门店与品类
正在下滑。本应用把 **口径、覆盖范围、可比变动、范围/组合变动、追溯修正与结论重开**
做成可计算、可查询、可审计的一套 Python 工具。

- **零第三方依赖**：Python 3.10+ 标准库（`csv` / `dataclasses` / `argparse` / `http.server`）。
- **缺失绝不置零**：没有事实就是覆盖缺口，可比部分与范围变化分开呈现。
- **原发布不可变**：`data/snapshots/R*.json` 是 write-once 发布快照；行动完成记录不被重开抹掉。
- **修正以新版本叠加**：会员图谱 `L1→L2`、商品分类 `v2→v3`、门店谱系确认，均可新旧复算。

---

## 快速开始

```bash
# 1) 运行全部测试（含交付样例结构测试）
python3 -m unittest discover -s tests -v

# 2) 查看完整经营治理总览（文本）
python3 app.py overview            # 等价 python3 -m metric_governance

# 3) 查单项指标档案：口径 / 覆盖 / 变动来源 / 待处理动作
python3 app.py metric revenue
python3 app.py metric comparable-sales
python3 app.py metric members
python3 app.py metric category-growth

# 4) 生成 HTML 仪表盘与每个指标的档案页
python3 app.py html --metric-pages
#    浏览器打开 out/dashboard.html

# 5) 或启动可点击查询的本地 Web 界面
python3 app.py serve --port 8765   # http://127.0.0.1:8765/

# 一键：测试 + 重建合成数据 + 生成 HTML
bash run_demo.sh
```

也可以直接对最初交付的样例目录运行（只有登记表、没有事实也不会崩）：

```bash
python3 app.py --data samples overview
```

---

## 内置案例与关键结论（合成数据，全部勾稽）

| 发布 | 指标 | 原发布 | 当前口径重算 | 判定 |
|---|---|---:|---:|---|
| R1 | revenue 2026-Q2 | **+12.4%** | +12.4% | 数字无需重开，但结论是“范围/组合驱动”，只能有条件用于资源决策 |
| R2 | members 2026-Q2 | **+8.1%**（L1：37→40 人） | **+2.6%**（L2：38→39 人） | 🔴 应重开；A2 已完成记录保留 |
| R3 | comparable-sales 2026-Q3 | **+4.3%**（快报仅 S1+TM） | **−4.3%**（补京东 + 确认 S0→S2 搬迁） | 🔴 符号反转，应重开 |
| R4 | category-growth 2026-Q3 护肤 | **+14.8%**（分类 v2） | **−4.1%**（追溯分类 v3） | 🔴 应重开 |

**R1 的同比桥（2025-Q2 → 2026-Q2，单位万元，分量精确可加）：**

```
总同比 +124 (+12.4%)
├─ 可比业务变化（同门店/平台 × 续接商品）   -66
├─ 组合变化·新品/套装 P5                   +141
├─ 组合变化·退市品类 P4                     -93
└─ 经营范围扩大（新平台 DY）                +142
```

同范围实体整体同比只有 **−1.8%**——汇总 +12.4% 主要来自新平台与套装组合。
因此系统给出的资源决策建议是：总盘/库存计划可用；**不能**按汇总同比给可比门店、
传统品类追加预算或认定团队改善，只能对已验证的套装/新品做小规模追加实验。

**覆盖纪律的两个演示：**

- `JD` 的 2026-Q3 结算文件 2026-10-20 才到（R3 发布于 10-12）。发布时点视图
  （`as_of=2026-10-12`）如实复现 +4.3% / 范围 S1+TM / JD missing；当前视图纳入 JD。
- `XHS` 新平台 Q3 只报了 8 月（部分期间）：登记为 `partial`，该主体两侧同时移出桥接，
  已报的 18 万元只进“剔除备忘”，**不会被当成 9 月为 0**。

---

## 目录结构

```
metric_governance/        应用包（仅标准库）
  periods.py              期间（月/季/年）、去年同期、期间包含关系
  models.py               全部 dataclass 领域模型
  io_csv.py               CSV/submissions 目录导入，空值=>None，问题登记
  workflow.py             JSON 覆盖层：角色确认、冲突裁决、重开个案、新行动
  registry.py             口径版本、覆盖区间、SKU 分类版本、门店/商品谱系、as_of
  quality.py              自然键冲突检测/裁决、覆盖缺口（missing/partial）
  analytics.py            精确可加的同比桥、可比口径、品类版本重述
  members.py              会员关联版本 L1/L2 去重
  reopen.py               快照读取、重要性判定、哪些结论应重开
  dossier.py              单项指标档案 + 决策建议 + 待办聚合
  overview.py             总览视图模型（文本/HTML/Web/JSON 共用）
  render_text.py          中文命令行报告
  render_html.py          自包含 HTML（发散条 + 数据表双视图、明暗主题）
  webapp.py               http.server 只读查询服务 + JSON API
  cli.py / __main__.py     argparse 命令行
data/                     富合成数据集（应用默认数据目录）
  definitions.csv         指标定义/版本/公式/责任人
  period_calibers.csv     各团队收入确认日与期间归属口径
  periods.csv             季度边界与去年同期
  entities.csv            门店/平台名册与中文名
  coverage.csv            门店/平台范围状态区间 + SKU 分类版本区间
  lineage.csv             门店搬迁、商品续接/新品线/组合关系
  member_links.csv        L1/L2 会员别名→自然人映射
  member_activity.csv     别名季度活跃
  reports.csv             管理层发布记录（兼容样例 7 列 + 扩展列）
  actions.csv             责任人、后续动作与完成记录
  confirmations.csv       三角色确认记录
  corrections.csv         三类追溯修正事件
  resolutions.csv         已裁决的事实冲突
  snapshots/R1..R4.json   不可变原始发布快照
  submissions/*.csv       各团队分批提交（含迟到文件与两个冲突批次）
samples/                  交付时的最小表结构样例（测试守护，勿改表头）
scripts/generate_demo_data.py  重新生成事实/会员等大体量合成数据
tests/                    unittest 测试（27 个）
app.py                    根启动器
```

---

## 数据契约（CSV，UTF-8；空单元格 = 来源未提供，绝不是 0）

| 文件 | 关键列 |
|---|---|
| `definitions.csv` | `metric,version,formula,from,owner[,unit,description]` |
| `period_calibers.csv` | `team,basis,date_field,boundary,recognition_lag_days,...`（如 finance=`settled-sales/settlement_date`，online=`order-date-gmv/order_date`） |
| `coverage.csv` | `entity,kind(store/platform/sku),group,state,from,to,version`；同一实体多行区间即版本历史，追溯修正用**更高 version 的新区间叠加**，不改旧行 |
| `lineage.csv` | `entity,kind(store/product),relation,related,from,confirmed,note`；relation：`relocated-from / successor-of / new-line / bundle-of` 等 |
| `member_links.csv` | `link_version,alias_id,person_id,platform,from,status` |
| `member_activity.csv` | `period,alias_id,active,events` |
| `reports.csv` | 前 7 列与样例一致：`report,metric,period,value,definition,action,state`；扩展 `compare_period,published_on,owner,conclusion,snapshot` |
| `actions.csv` | `action,report,owner,title,state,created_on,due_on,completed_on,completion_note` |
| `confirmations.csv` | `subject_type,subject_key,role(governance/channel-owner/product-owner),person,decision,on,note` |
| `corrections.csv` | `correction_id,domain(member_identity/store_status/product_classification/fact),target,summary,detected_on,effective_from,new_version,status,owner` |
| 事实 `submissions/*.csv` 或 `facts.csv` | `fact_id,team,metric,period(YYYY-MM),entity,sku,value,basis,received_on,batch,...` |

导入器会读取 `submissions/*.csv` 作为各团队分批提交；同自然键
`(metric, period, entity, sku)` 出现不同值即登记为冲突。同值重发不重复计量。

---

## 核心计算规则

### 1. 缺失 ≠ 0

`quality.coverage_gaps()` 对照 `coverage.csv` 的制度名册与区间，计算每个实体在期间内
**应报月份**与**实有月份**：

- `missing`：范围内但没有任何已生效事实；
- `partial`：只覆盖部分月份（如 XHS 只有 8 月）。

任一缺口实体在基期/本期**两侧同时移出桥接周边界**，其可见金额只进入
`excluded_base / excluded_current` 调节备忘。系统不存在对缺失渠道 `fillna(0)` 的路径。

### 2. 冲突不猜数

未裁决冲突的单元格不进入任何合计，只在冲突清单与 `open_conflicts` 中呈现候选值。
治理人员裁决后（`resolutions.csv` 或 CLI 写入工作流覆盖层）才计入。

### 3. 同比桥精确可加

`analytics.revenue_bridge()` 先做“实体配对”（已确认的门店搬迁谱系优先于同 ID），
再做“商品配对”（已确认的 `successor-of` 优先），把每个实际单元格归入：

- `comparable`：同范围实体 × 匹配/续接商品的变化；
- `portfolio_new` / `portfolio_discontinued`：持续经营实体内的新品/套装与退市品；
- `scope_new` / `scope_closed`：新门店/新平台、关闭/迁出主体。

恒等式（测试守护）：

```
base_total + Σ components.amount = current_total
```

`comparable_rate` 另按可比实体整体口径计算（含其实体内组合变化），对应
`comparable-sales v2 same-store-net`。

### 4. 会员与品类的版本化重述

- 会员：`MemberEngine.count(period, link_version)` 用指定图谱把活跃别名映射为自然人后去重。
- 品类：`category_growth(..., classification_version=...)` 按月末适用的分类版本归集；
  追溯新版本会同时重述去年比较期。

### 5. 重开判定与不可变发布

`reopen.assess_report()` 读取 `snapshots/<report>.json` 原始发布值，与当前最新口径重算值
比较。增长率差异 ≥ **0.5pp**、同比符号反转，或存在无法量化的相关追溯修正，即判定
`should_reopen=True`。判定理由包括：修正事件、可比范围变化、迟到数据、覆盖缺口与未裁决冲突。

快照由 `write_snapshot()` 以 write-once 方式写入，已存在即 `FileExistsError`；重开动作只
追加到 `out/workflow_state.json`，**不修改**快照与 `actions.csv`。例如 R2 重开后，
A2 仍是 `complete / 2026-07-28`，另生成新的 `A-REOPEN-R2` 跟进动作。

### 6. 三角色确认与 CLI 工作流

```bash
# 指标治理：确认定义/可比范围
python3 app.py confirm --subject-type scope --subject-key 2026-Q4-comparable \
  --role governance --person 孙敏 --decision confirmed

# 渠道负责人：确认门店/平台状态或搬迁谱系
python3 app.py confirm --subject-type lineage \
  --subject-key "S2:relocated-from:S0" \
  --role channel-owner --person 赵磊

# 商品负责人：确认新品关系/品类迁移
python3 app.py confirm --subject-type lineage \
  --subject-key "P5:new-line:" --role product-owner --person 钱芳

# 冲突裁决（写入 out/workflow_state.json，可跨进程保留）
python3 app.py resolve-conflict --key "revenue|2026-08|DY|P2" --value 26 --person 孙敏

# 重开判定；--apply 登记重开个案并生成跟进动作
python3 app.py reopen --apply
python3 app.py actions --pending
python3 app.py complete-action --action A-REOPEN-R3 --person 陈澈 --note "已重述并二次发布"
```

---

## CLI 与 HTTP API 速查

| 命令 | 作用 |
|---|---|
| `overview`（默认）/ `demo` | 完整中文总览 |
| `metrics` | 列出指标定义与责任人 |
| `metric <name>` | 单项指标档案 |
| `reopen [--apply]` | 重开判定 / 登记重开 |
| `actions [--pending]` | 行动台账 / 当前待处理 |
| `conflicts` | 冲突与裁决状态 |
| `confirmations` | 查看治理/渠道/商品三角色确认记录 |
| `coverage [--period 2026-Q3]` | 覆盖缺口检查 |
| `confirm / resolve-conflict / complete-action` | 工作流写入 |
| `check` | 仅导入校验，有 error 时退出码 1 |
| `html --out ... [--metric-pages]` | 生成静态仪表盘 |
| `serve --host --port` | Web 查询 + JSON API |

HTTP API：`GET /api/overview`、`/api/metric/<name>`、`/api/pending`、`/healthz`；
页面：`/`（仪表盘）、`/metric/<name>`（指标档案）。

## Python API

```python
from metric_governance import (
    load_dataset, Registry, WorkflowState,
    revenue_bridge, MemberEngine, category_growth, assess_report,
)

ds = load_dataset("data")
reg = Registry(ds, WorkflowState())
bridge = revenue_bridge(reg, "2026-Q2")
print(bridge.growth_rate, [(c.code, c.amount) for c in bridge.components])

for report in ds.reports:
    a = assess_report(reg, report)
    print(report.report, a.should_reopen, a.headline_original, a.headline_restated)
```

## 接入真实数据

1. 按上表导出各团队 CSV 到一个新目录（事实可拆成 `submissions/*.csv`）。
2. 维护 `coverage.csv` 区间版本与 `lineage.csv` 谱系；追溯修正只追加新版本行与
   `corrections.csv` 事件，不覆盖历史。
3. 发布结论时调用 `reopen.write_snapshot()` 固化当时数字、范围与口径版本。
4. 用 `python3 app.py --data <目录> check` 先看导入问题，再 `overview` / `html`。

## 测试

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：期间运算、样例表结构与引用、缺失渠道不置零、空单元格、Q2/Q3 桥接精确可加、
发布时点 as-of 复算、会员版本、品类版本、R1–R4 重开判定、完成行动保留、快照 write-once、
工作流跨进程持久化、CLI 与 HTML 产出。
