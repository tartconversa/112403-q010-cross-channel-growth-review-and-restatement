#!/usr/bin/env python3
"""项目根启动器：等价于 python3 -m metric_governance。

示例：
    python3 app.py overview
    python3 app.py metric revenue
    python3 app.py html --metric-pages
    python3 app.py serve
"""
from metric_governance.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
