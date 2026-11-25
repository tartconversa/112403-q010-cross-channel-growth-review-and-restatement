#!/usr/bin/env bash
# 一键自检 + 重建合成数据产物 + 生成 HTML 仪表盘
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/3 运行测试 =="
python3 -m unittest discover -s tests -v

echo "== 2/3 （可选）重新生成合成数据 =="
python3 scripts/generate_demo_data.py

echo "== 3/3 生成 HTML 仪表盘与指标档案 =="
python3 -m metric_governance html --metric-pages

echo
echo "完成：用浏览器打开 out/dashboard.html，或运行 python3 app.py serve"
