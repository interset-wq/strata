"""校验归档完整性并解压出源库。可重复执行，已解压则跳过。

仅在需要重新解压时运行（源库已存在则直接返回）：
    uv run --extra archive python analysis/prepare.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as C


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if C.SOURCE_DB.exists():
        print(f"源库已存在，跳过解压：{C.SOURCE_DB}")
        return 0

    if not C.ARCHIVE.exists():
        print(f"缺少归档 {C.ARCHIVE}")
        print(f"从 {C.SOURCE['repo']} 的 {C.SOURCE['tag']} 下载 {C.SOURCE['asset']} 放入 data/")
        return 1

    actual = sha256(C.ARCHIVE)
    if actual != C.SOURCE["sha256"]:
        print("归档哈希不匹配，拒绝解压")
        print(f"  期望 {C.SOURCE['sha256']}")
        print(f"  实际 {actual}")
        return 1
    print(f"归档校验通过 {actual[:12]}…")

    import py7zr

    C.EXTRACT_DIR.mkdir(parents=True, exist_ok=True)    with py7zr.SevenZipFile(C.ARCHIVE, mode="r") as zf:
        zf.extractall(path=C.EXTRACT_DIR)

    if not C.SOURCE_DB.exists():
        print(f"解压后未找到 {C.SOURCE_DB}")
        return 1

    print(f"已解压到 {C.EXTRACT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
