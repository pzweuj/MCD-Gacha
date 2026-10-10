"""网页数据同步一致性测试：demo/data 必须与 src 数据完全一致。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "mcd_gacha" / "data"
DST = ROOT / "demo" / "data"
FILES = ("banners.json", "mock_menu.json", "mock_prices.json")


def test_demo_data_matches_source():
    for name in FILES:
        src_file = SRC / name
        dst_file = DST / name
        assert dst_file.exists(), f"缺少 {dst_file}（请运行 scripts/build_demo_data.py）"
        src_data = json.loads(src_file.read_text(encoding="utf-8"))
        dst_data = json.loads(dst_file.read_text(encoding="utf-8"))
        assert src_data == dst_data, f"{name} 与源数据不一致（请运行 scripts/build_demo_data.py）"
