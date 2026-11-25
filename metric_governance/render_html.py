"""自包含 HTML 仪表盘与指标档案页（无外部依赖、无 CDN）。

可视化遵循 dataviz 规范：蓝/红发散色表达变动方向，状态色仅用于
就绪/重开状态且始终“图标 + 文字”，每张图都附数据表。
"""
from __future__ import annotations

from html import escape
from typing import Any

from .dossier import MetricDossier
from .overview import Overview
from .render_text import num, pct_text

# 已用 dataviz validate_palette.js 校验通过的发散色对 #2a78d6 / #e34948
CSS = """
:root{
  color-scheme: light;
  --surface:#fcfcfb; --page:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --pos:#2a78d6; --neg:#e34948; --total:#52514e;
  --good:#0a7d0a; --warn:#9a6b00; --serious:#b5481f; --critical:#b3261e;
  --good-bg:#e8f5e8; --warn-bg:#fdf3d8; --critical-bg:#fbe6e4; --cond-bg:#e8f1fc;
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --surface:#1a1a19; --page:#0d0d0d; --ink:#f0efec; --ink2:#c3c2b7;
  --muted:#898781; --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.12);
  --pos:#3987e5; --neg:#e66767; --total:#c3c2b7;
  --good:#34b334; --warn:#e0a92e; --serious:#ec835a; --critical:#e66767;
  --good-bg:#143014; --warn-bg:#33280a; --critical-bg:#3a1715; --cond-bg:#12263f;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
 font:14px/1.6 system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;}
.wrap{max-width:1180px;margin:0 auto;padding:28px 24px 80px}
header.top{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;
 border-bottom:1px solid var(--grid);padding-bottom:16px;margin-bottom:22px;flex-wrap:wrap}
h1{font-size:22px;margin:0 0 4px} h2{font-size:17px;margin:34px 0 12px}
h3{font-size:15px;margin:18px 0 8px}
.sub{color:var(--ink2);font-size:13px}
nav.toc{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 0}
nav.toc a{font-size:12.5px;color:var(--pos);text-decoration:none;border:1px solid var(--border);
 padding:3px 10px;border-radius:999px;background:var(--surface)}
nav.toc a:hover{border-color:var(--pos)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px 16px}
.tile .k{color:var(--ink2);font-size:12.5px}.tile .v{font-size:26px;font-weight:650;margin-top:2px;
 font-variant-numeric:tabular-nums}
.tile .s{font-size:12px;color:var(--muted)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;
 padding:18px 20px;margin:14px 0}
.pub{border-left:4px solid var(--axis)}
.pub.reopen{border-left-color:var(--critical)}
.pub.stable{border-left-color:var(--good)}
.pub.watch{border-left-color:var(--warn)}
.row-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline;flex-wrap:wrap}
.title{font-weight:650;font-size:15.5px}
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:600;
 padding:3px 10px;border-radius:999px;white-space:nowrap}
.badge.blocked,.badge.reopen{color:var(--critical);background:var(--critical-bg)}
.badge.conditional,.badge.watch{color:var(--warn);background:var(--warn-bg)}
.badge.ready,.badge.stable{color:var(--good);background:var(--good-bg)}
.concl{margin:8px 0;color:var(--ink)}
.orig{color:var(--ink2);font-size:13px}
.why{margin:8px 0;padding-left:0;list-style:none}
.why li{padding:3px 0 3px 20px;position:relative}
.why li:before{content:"·";position:absolute;left:8px;color:var(--muted);font-weight:700}
.advice{border-radius:8px;padding:10px 14px;margin-top:10px;font-size:13.5px}
.advice.ready{background:var(--good-bg)} .advice.conditional{background:var(--cond-bg)}
.advice.blocked{background:var(--critical-bg)}
.advice .use{margin:6px 0 0}.tag{display:inline-block;font-size:11.5px;border-radius:5px;
 padding:1px 7px;margin-right:6px;font-weight:600}
.tag.yes{background:var(--good-bg);color:var(--good)} .tag.no{background:var(--critical-bg);color:var(--critical)}
table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--grid);vertical-align:top}
th{color:var(--ink2);font-weight:600;font-size:12.5px;background:transparent}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
.pill{font-size:11.5px;padding:1px 8px;border-radius:999px;border:1px solid var(--border);color:var(--ink2)}
/* diverging bar bridge */
.bars{margin:14px 0 6px}
.brow{display:grid;grid-template-columns:minmax(190px,280px) 1fr 96px;gap:12px;align-items:center;
 padding:5px 0}
.blabel{font-size:12.8px;color:var(--ink2)}
.track{position:relative;height:18px}
.track:before{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--axis)}
.bar{position:absolute;top:2px;height:14px;border-radius:3px;min-width:2px;cursor:default}
.bar.pos{left:50%;background:var(--pos)}
.bar.neg{right:50%;background:var(--neg)}
.bval{text-align:right;font-size:12.8px;font-variant-numeric:tabular-nums;font-weight:600}
.delta-pos{color:var(--pos)} .delta-neg{color:var(--neg)}
.note{font-size:12.5px;color:var(--ink2);margin:6px 0}
.gapbox{border:1px dashed var(--serious);border-radius:8px;padding:8px 12px;margin:8px 0;font-size:13px}
.foot{margin-top:40px;color:var(--muted);font-size:12px;border-top:1px solid var(--grid);padding-top:14px}
.btn{border:1px solid var(--border);background:var(--surface);color:var(--ink);border-radius:8px;
 padding:5px 12px;font-size:12.5px;cursor:pointer}
.btn:hover{border-color:var(--pos)}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);
 font-size:12px;padding:6px 9px;border-radius:6px;max-width:320px;display:none;z-index:9;
 box-shadow:0 4px 16px rgba(0,0,0,.25)}
@media (max-width:720px){.brow{grid-template-columns:130px 1fr 74px}.wrap{padding:18px 12px 60px}}
"""

JS = """
const tip=document.getElementById('tip');
document.addEventListener('mousemove',e=>{
  const t=e.target.closest('[data-tip]');
  if(t){tip.style.display='block';tip.textContent=t.getAttribute('data-tip');
    tip.style.left=Math.min(e.clientX+14,innerWidth-340)+'px';
    tip.style.top=(e.clientY+14)+'px';}
  else tip.style.display='none';
});
function toggleTheme(){
  const r=document.documentElement;
  r.setAttribute('data-theme', r.getAttribute('data-theme')==='dark'?'light':'dark');
}
"""


def _e(v: Any) -> str:
    return escape("" if v is None else str(v))


def _status_badge(level: str, text: str | None = None) -> str:
    icons = {"blocked": "⛔", "reopen": "🔴", "conditional": "⚠️",
             "watch": "🟠", "ready": "✅", "stable": "🟢"}
    label = text or level
    return f'<span class="badge {_e(level)}">{icons.get(level, "•")} {_e(label)}</span>'


def _rate_class(x: float | None) -> str:
    if x is None:
        return ""
    return "delta-pos" if x >= 0 else "delta-neg"


def bridge_html(b: dict[str, Any], heading: str | None = None) -> str:
    max_amt = max((abs(c["amount"]) for c in b.get("components", [])), default=1.0)
    max_amt = max(max_amt, abs(b.get("delta", 0) or 0), 1.0)
    rows = ['<div class="bars" role="img" aria-label="同比变动发散条形图">']
    for c in b["components"]:
        amt = c["amount"]
        width = min(abs(amt) / max_amt * 50, 50)
        cls = "pos" if amt >= 0 else "neg"
        tip = (f"{c['label']}：{amt:+.1f}（基 {c.get('base_amount', 0):.1f} / "
               f"本 {c.get('current_amount', 0):.1f}），明细 {len(c.get('detail', []))} 行")
        rows.append(
            f'<div class="brow"><div class="blabel">{_e(c["label"])}</div>'
            f'<div class="track"><div class="bar {cls}" style="width:{width:.2f}%" '
            f'data-tip="{_e(tip)}"></div></div>'
            f'<div class="bval {_rate_class(amt)}">{amt:+.1f}</div></div>')
    rows.append("</div>")

    tiles = f"""
    <div class="cards">
      <div class="tile"><div class="k">基期 {_e(b['base_period'])}</div>
        <div class="v">{num(b['base_total'])}</div><div class="s">周边界内合计</div></div>
      <div class="tile"><div class="k">总变动</div>
        <div class="v {_rate_class(b['growth_rate'])}">{pct_text(b['growth_rate'])}</div>
        <div class="s">Δ {num(b['delta'])}</div></div>
      <div class="tile"><div class="k">本期 {_e(b['current_period'])}</div>
        <div class="v">{num(b['current_total'])}</div><div class="s">周边界内合计</div></div>
      <div class="tile"><div class="k">可比实体同比</div>
        <div class="v {_rate_class(b['comparable_rate'])}">{pct_text(b['comparable_rate'], signed=False)}</div>
        <div class="s">{_e('、'.join(b['comparable_entities']) or '无')}</div></div>
    </div>"""

    gaps = "".join(
        f'<div class="gapbox">🧩 <b>覆盖{g["kind"] == "partial" and "部分期间" or "缺失"}：'
        f'{_e(g["entity"])}</b> — 应报 {len(g["expected_months"])} 个月 '
        f'{_e(g["expected_months"])}，实有 {_e(g["observed_months"])}。'
        f'{_e(g["reason"])}。该主体两侧均移出桥接，<b>绝不按 0 处理</b>。</div>'
        for g in b.get("gaps", []))
    conflicts = "".join(
        f'<div class="gapbox">⚡ 未裁决冲突：<code>{_e(ck)}</code>，冲突单元格未计入。</div>'
        for ck in b.get("open_conflicts", []))

    comp_rows = "".join(
        f"<tr><td>{_e(c['label'])}</td>"
        f'<td class="num">{num(c.get("base_amount", 0))}</td>'
        f'<td class="num">{num(c.get("current_amount", 0))}</td>'
        f'<td class="num {_rate_class(c["amount"])}">{c["amount"]:+.1f}</td></tr>'
        for c in b["components"])
    table = f"""
    <details><summary class="note" style="cursor:pointer">查看桥接数据表（精确可加）</summary>
    <table><thead><tr><th>变动来源</th><th class="num">基期</th>
    <th class="num">本期</th><th class="num">对 Δ 贡献</th></tr></thead>
    <tbody>{comp_rows}
    <tr><td><b>合计 Δ</b></td><td class="num">{num(b['base_total'])}</td>
    <td class="num">{num(b['current_total'])}</td>
    <td class="num"><b>{b['delta']:+.1f}</b></td></tr></tbody></table></details>"""

    adjust = ""
    if b.get("excluded_base") or b.get("excluded_current"):
        adjust = (f'<p class="note">调节备忘：缺口/部分覆盖主体基期可见金额 '
                  f'{num(b["excluded_base"])}、本期可见金额 {num(b["excluded_current"])} '
                  "已移出桥接；它们是真实存在但不完整的报送，不是零。</p>")
    h = f"<h3>{_e(heading)}</h3>" if heading else ""
    return f'<div class="card">{h}{tiles}{"".join(rows)}{table}{adjust}{gaps}{conflicts}</div>'


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<header class="top"><div><h1>{_e(title)}</h1>
<div class="sub">合成数据 · 仅使用 Python 标准库 · 数字单位以指标登记为准（示例为万元 / 人 / %）</div>
</div><button class="btn" onclick="toggleTheme()">🌓 切换明暗</button></header>
{body}
<div class="foot">治理原则：可比部分与范围/组合变化分开呈现；缺失渠道不默认为零；
原始发布快照与行动完成记录只读保留；追溯修正通过新版本叠加并触发重开判定。</div>
</div><div id="tip"></div><script>{JS}</script></body></html>"""


def render_dashboard(ov: Overview) -> str:
    o = ov.to_dict() if hasattr(ov, "to_dict") else ov
    pubs_html: list[str] = []
    for p in o["publications"]:
        a, adv = p["assessment"], p["advice"]
        actions = "".join(
            f'<span class="pill">{_e(x["action"])} · {_e(x["state"])}'
            + (f' · 完成于 {_e(x["completed_on"])}（记录保留）' if x.get("completed_on") else "")
            + "</span>" for x in a["actions"])
        reasons = "".join(f"<li>{_e(r)}</li>" for r in a["reasons"]) or \
            "<li>未发现越过重要性阈值的追溯影响。</li>"
        use_yes = "".join(f"<li>{_e(x)}</li>" for x in adv.get("usable_for", []))
        use_no = "".join(f"<li>{_e(x)}</li>" for x in adv.get("not_usable_for", []))
        pubs_html.append(f"""
        <section class="card pub {_e(a['severity'])}" id="{_e(p['report'])}">
          <div class="row-head">
            <div class="title">{_e(p['report'])} · {_e(p['metric'])} · {_e(p['period'])}</div>
            {_status_badge('reopen' if a['should_reopen'] else a['severity'],
                           '应重开' if a['should_reopen'] else
                           ('需关注' if a['severity']=='watch' else '无需重开'))}
          </div>
          <p class="concl">{_e(p['conclusion'])}</p>
          <p class="orig">发布值 <b>{_e(a['headline_original'])}</b>
             （定义 {_e(p['definition'])}，{_e(p['published_on'])}，责任人 {_e(p['owner'])}）
             ｜当前口径重算：<b class="{_rate_class(a['delta_pp'])}">{_e(a['headline_restated'] or '无法重述')}</b>
             {f"｜差异 {a['delta_pp']:+.1f}pp" if a['delta_pp'] is not None else ""}</p>
          <ul class="why">{reasons}</ul>
          <div class="advice {_e(adv['level'])}">
            {_status_badge(adv['level'], adv['title'])}
            <div class="use">{('<span class="tag yes">可用于</span><ul>'+use_yes+'</ul>') if use_yes else ''}
                 {('<span class="tag no">不可用于</span><ul>'+use_no+'</ul>') if use_no else ''}</div>
          </div>
          <p class="note">关联行动：{actions or '无'}</p>
        </section>""")

    nav = ('<nav class="toc"><a href="#publications">发布结论</a>'
           '<a href="#bridges">同比桥接</a><a href="#members">会员</a>'
           '<a href="#category">品类</a><a href="#pending">待处理</a>'
           '<a href="metrics/revenue.html">revenue 档案</a>'
           '<a href="metrics/members.html">members 档案</a>'
           '<a href="metrics/comparable-sales.html">comparable-sales 档案</a>'
           '<a href="metrics/category-growth.html">category-growth 档案</a></nav>')

    tiles = "".join(
        f'<div class="tile"><div class="k">{_e(k)}</div><div class="v">{v}</div></div>'
        for k, v in [("导入事实行", o["counts"]["facts"]),
                     ("发布结论", o["counts"]["reports"]),
                     ("应重开", o["counts"]["reopen"]),
                     ("待处理事项", o["counts"]["pending"]),
                     ("追溯修正", o["counts"]["corrections"])])

    bridges_html = "".join(bridge_html(o["bridges"][k], t) for k, t in [
        ("2026-Q2", "2026-Q2 vs 2025-Q2 · R1 发布期（覆盖完整、冲突已裁决）"),
        ("2026-Q3-current", "2026-Q3 vs 2025-Q3 · 当前全部数据（含迟到 JD 与搬迁确认）"),
        ("2026-Q3-publish-view", "2026-Q3 · 发布时点视图（as-of 2026-10-12，JD 未到）")])

    monthly_rows = "".join(
        f"<tr><td>{_e(m['month'])}</td><td>{_e(m['prior_month'])}</td>"
        f"<td class='num'>{num(m['base'])}</td>"
        f"<td class='num'>{num(m['current'])}</td>"
        f"<td class='num {_rate_class(m['yoy'])}'>{pct_text(m['yoy'])}</td>"
        f"<td class='sub'>{_e('，'.join(m['coverage_flags'] + m['open_conflicts']))}</td></tr>"
        for m in o.get("monthly", []))
    monthly_card = f"""
    <div class="card"><h3>月度收入与覆盖标记</h3>
    <table><thead><tr><th>月份</th><th>去年同月</th><th class="num">基期</th>
    <th class="num">本期</th><th class="num">同比</th><th>覆盖/冲突</th></tr></thead>
    <tbody>{monthly_rows}</tbody></table>
    <p class="note">月度金额只合计实际收到且冲突已生效的单元格；带 partial/missing
    标记的月份不能直接用于月度排名，缺口从未按零补齐。</p></div>""" if monthly_rows else ""

    mv = o["member_views"]
    member_rows = "".join(
        f"<tr><td>{ver}</td><td class='num'>{mv[ver]['base']['persons']}</td>"
        f"<td class='num'>{mv[ver]['current']['persons']}</td>"
        f"<td class='num {_rate_class(mv[ver]['growth_rate'])}'>"
        f"{pct_text(mv[ver]['growth_rate'])}</td></tr>" for ver in ("L1", "L2"))

    cv2, cv3 = o["category_views"]["published_v2"], o["category_views"]["restated_v3"]
    cat_rows = "".join(
        f"<tr><td>{_e(r['category'])}</td><td class='num'>{num(r['base'])}</td>"
        f"<td class='num'>{num(r['current'])}</td>"
        f"<td class='num {_rate_class(r['growth_rate'])}'>{pct_text(r['growth_rate'], signed=False)}</td></tr>"
        for r in cv3["by_category"])

    pending_rows = "".join(
        f"<tr><td>{_e(p['kind'])}</td><td><code>{_e(p['ref'])}</code></td>"
        f"<td>{_e(p['title'])}</td><td>{_e(p['owner'])}</td>"
        f"<td><span class='pill'>{_e(p['state'])}</span></td>"
        f"<td class='sub'>{_e(p.get('detail',''))}</td></tr>"
        for p in o["pending"])

    issues = "".join(f"<li>[{_e(i['level'])}] {_e(i['message'])}</li>"
                     for i in o["issues"])

    body = f"""
    {nav}
    <div class="cards">{tiles}</div>
    {f'<div class="card"><h3>导入问题</h3><ul class="why">{issues}</ul></div>' if issues else ''}
    <h2 id="publications">一、已发布结论 · 重开判定 · 下月资源决策可用性</h2>
    {''.join(pubs_html)}
    <h2 id="bridges">二、总体同比 = 可比业务 + 范围/组合变化</h2>
    {bridges_html}
    {monthly_card}
    <h2 id="members">三、会员身份追溯修正（R2）</h2>
    <div class="card"><table><thead><tr><th>关联版本</th>
      <th class="num">2025-Q2 去重人数</th><th class="num">2026-Q2 去重人数</th>
      <th class="num">同比</th></tr></thead><tbody>{member_rows}</tbody></table>
      <p class="note">L1 为 R2 原发布口径；L2 为追溯修正后的身份图谱。旧版本仍可随时复算。</p></div>
    <h2 id="category">四、商品分类追溯修正（R4 · skincare）</h2>
    <div class="card"><p class="orig">发布 v2：{num(cv2['base_amount'])} →
      {num(cv2['current_amount'])}（{pct_text(cv2['growth_rate'], signed=False)}）；
      当前 v3：{num(cv3['base_amount'])} → {num(cv3['current_amount'])}
      （{pct_text(cv3['growth_rate'], signed=False)}）。</p>
      <table><thead><tr><th>品类(v3)</th><th class="num">基期</th>
      <th class="num">本期</th><th class="num">同比</th></tr></thead>
      <tbody>{cat_rows}</tbody></table></div>
    <h2 id="pending">五、当前待处理动作（{len(o['pending'])}）</h2>
    <div class="card"><table><thead><tr><th>类型</th><th>对象</th><th>事项</th>
      <th>责任人</th><th>状态</th><th>说明</th></tr></thead>
      <tbody>{pending_rows or '<tr><td colspan=6>无待处理事项</td></tr>'}</tbody></table></div>
    """
    return _page("全域经营指标治理仪表盘", body)


def render_metric_page(d: MetricDossier) -> str:
    o = d.to_dict()
    defs = "".join(
        f"<tr><td>{_e(x['version'])}</td><td><code>{_e(x['formula'])}</code></td>"
        f"<td>{_e(x['from'])}</td><td>{_e(x['owner'])}</td>"
        f"<td>{_e(x['unit'])}</td><td>{_e(x['description'])}</td></tr>"
        for x in o["definitions"]) or "<tr><td colspan=6>无定义</td></tr>"
    calibers = "".join(
        f"<li><b>{_e(c['team'])}</b>：{_e(c['basis'])} / {_e(c['date_field'])} / {_e(c['boundary'])}</li>"
        for c in o["calibers"])
    assessments = "".join(
        f'<div class="card pub {_e(a["severity"])}">'
        f'<div class="row-head"><b>{_e(a["report"])} {_e(a["period"])}：'
        f'{_e(a["headline_original"])} → {_e(a["headline_restated"] or "—")}</b>'
        f'{_status_badge("reopen" if a["should_reopen"] else a["severity"], "应重开" if a["should_reopen"] else a["severity"])}'
        f'</div><ul class="why">{"".join("<li>"+_e(r)+"</li>" for r in a["reasons"])}</ul></div>'
        for a in o["assessments"])
    advice = "".join(
        f'<div class="advice {_e(x["level"])}">{_status_badge(x["level"], x["title"])}</div>'
        for x in o["advice"])
    bridge = bridge_html(o["bridge"], "同比桥接与覆盖") if o["bridge"] else ""
    member = ""
    if o["members"]:
        m = o["members"]
        member = (f'<div class="card"><h3>会员去重（{_e(m["link_version"])}）</h3>'
                  f'<p>{m["base"]["persons"]} → {m["current"]["persons"]}，'
                  f'同比 {pct_text(m["growth_rate"])}</p></div>')
    category = ""
    if o["category"]:
        rows = "".join(
            f"<tr><td>{_e(r['category'])}</td><td class='num'>{num(r['base'])}</td>"
            f"<td class='num'>{num(r['current'])}</td>"
            f"<td class='num'>{pct_text(r['growth_rate'], signed=False)}</td></tr>"
            for r in o["category"]["by_category"])
        category = (f'<div class="card"><h3>品类归集（{_e(o["category"]["classification_version"])}）</h3>'
                    f'<table><tbody>{rows}</tbody></table></div>')
    coverage_rows = "".join(
        f"<tr><td>{_e(c['entity'])}</td><td>{_e(c['kind'])}</td>"
        f"<td>{_e(c['group'])}</td><td>{_e(c['state'])}</td>"
        f"<td>{_e(c['effective_from'] or '?')} ~ {_e(c['effective_to'] or '至今')}</td>"
        f"<td>v{_e(c['version'])}</td></tr>" for c in o["coverage"])
    corr = "".join(f"<li><code>{_e(c['correction_id'])}</code> [{_e(c['domain'])}] "
                   f"{_e(c['summary'])}</li>" for c in o["corrections"]) or "<li>无</li>"
    pending = "".join(
        f"<tr><td>{_e(p['kind'])}</td><td>{_e(p['ref'])}</td><td>{_e(p['title'])}</td>"
        f"<td>{_e(p['owner'])}</td><td>{_e(p['state'])}</td></tr>"
        for p in o["pending"]) or "<tr><td colspan=5>无</td></tr>"

    body = f"""
    <nav class="toc"><a href="../dashboard.html">← 返回总览</a></nav>
    <h2>口径定义</h2>
    <div class="card"><table><thead><tr><th>版本</th><th>公式</th><th>生效日</th>
      <th>责任人</th><th>单位</th><th>说明</th></tr></thead><tbody>{defs}</tbody></table>
      {f'<h3>团队期间确认口径</h3><ul class="why">{calibers}</ul>' if calibers else ''}</div>
    <h2>发布与重开判定</h2>{assessments or '<div class="card">无关联发布。</div>'}{advice}
    {bridge}{member}{category}
    <h2>范围 / 分类登记</h2>
    <div class="card"><table><thead><tr><th>实体</th><th>类型</th><th>归属</th>
      <th>状态</th><th>区间</th><th>版本</th></tr></thead><tbody>{coverage_rows}</tbody></table></div>
    <h2>追溯修正</h2><div class="card"><ul class="why">{corr}</ul></div>
    <h2>当前待处理</h2><div class="card"><table><thead><tr><th>类型</th><th>对象</th>
      <th>事项</th><th>责任人</th><th>状态</th></tr></thead><tbody>{pending}</tbody></table></div>
    """
    return _page(f"指标档案 · {o['metric']}", body)
