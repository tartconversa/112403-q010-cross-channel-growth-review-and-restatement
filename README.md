# 全域经营指标口径登记与管理层结论重述

合成管理指标口径、门店与商品范围版本、汇总数据和发布行动记录。

All example identifiers and values are synthetic. CSV files use UTF-8. The first row contains column names, and an empty cell means the source supplied no value.

## Sample files

- `definitions.csv` contains 管理指标定义、生效版本和责任人。 Columns are `metric`, `version`, `formula`, `from`, `owner`.
- `coverage.csv` contains 渠道和商品期间的范围状态及分类修订。 Columns are `entity`, `kind`, `group`, `state`, `from`, `to`, `version`.
- `reports.csv` contains 发布指标值、覆盖范围及后续行动状态。 Columns are `report`, `metric`, `period`, `value`, `definition`, `action`, `state`.

Python 3 standard library is sufficient to inspect these inputs. Run `python3 -m unittest discover -s tests -v` to check the delivered file structures and example references.
