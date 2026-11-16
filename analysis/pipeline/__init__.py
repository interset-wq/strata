"""数据管线：归档校验 → CSV 构建 → 产出校验。

- `prepare`   校验归档 SHA-256 并解压出 jsonl
- `build_csv` jsonl → 唯一规范化 CSV（去重、重命名、清洗、剔除）
- `validate`  CSV 格式层与取值层校验（build_csv 自动调用，也可单独跑）
"""

from __future__ import annotations

__all__ = ["prepare", "build_csv", "validate"]
