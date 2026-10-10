"""同步数据到网页演示目录（单一真源：src/mcd_gacha/data/）。

用法：python scripts/build_demo_data.py
约定：demo/data/*.json 必须与 src 侧完全一致（CI 用 test_data_sync.py 断言）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "mcd_gacha" / "data"
DST = ROOT / "demo" / "data"

FILES = ("banners.json", "mock_menu.json", "mock_prices.json")


def main() -> int:
    DST.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src_file = SRC / name
        if not src_file.exists():
            print(f"❌ 源文件不存在: {src_file}")
            return 1
        shutil.copy2(src_file, DST / name)
        print(f"✓ {name}")
    print(f"已同步 {len(FILES)} 个数据文件到 {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
