"""共享库：路径、字段语义、定年与图表设施。

- `paths`  路径的唯一真源（脚本位置与数据位置解耦）
- `config` 枚举域、清洗规则、列定义
- `eras`   nid 定年（log 分段线性插值 + 锚点）
- `charts` 报告图表的公共风格设施
"""

from __future__ import annotations

__all__ = ["paths", "config", "eras", "charts"]
