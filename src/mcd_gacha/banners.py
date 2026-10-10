"""卡池定义、加载与时段可用性判定。

卡池参数存储在 data/banners.json（单一真源，CLI 与网页演示页共用）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import yuan

DATA_DIR = Path(__file__).resolve().parent / "data"
BANNERS_FILE = DATA_DIR / "banners.json"


@dataclass(frozen=True)
class Banner:
    """单个卡池。"""

    key: str
    name: str
    name_en: str
    emoji: str
    budget_min_cents: int
    budget_max_cents: int
    default_budget_cents: int
    require_tags: tuple[str, ...]
    prefer_tags: tuple[str, ...]
    time_window: tuple[int, int] | None  # (start_hour, end_hour)，None 表示全天
    desc: str

    def is_available(self, now: datetime) -> bool:
        """判断卡池当前是否开放（深夜池 21:00-04:00 为跨午夜窗口）。"""
        if self.time_window is None:
            return True
        start, end = self.time_window
        hour = now.hour
        if start <= end:
            return start <= hour < end
        # 跨午夜：如 21 → 4
        return hour >= start or hour < end


@dataclass
class BannerConfig:
    """卡池配置总集。"""

    rarity_weights: dict[str, int]
    hard_pity: int
    pity_note: str
    banners: list[Banner]

    def get(self, key: str) -> Banner | None:
        for banner in self.banners:
            if banner.key == key:
                return banner
        return None

    def require(self, key: str) -> Banner:
        banner = self.get(key)
        if banner is None:
            known = ", ".join(b.key for b in self.banners)
            raise KeyError(f"未知卡池：{key}（可用：{known}）")
        return banner


def load_banner_config(path: Path | None = None) -> BannerConfig:
    """加载卡池配置。"""
    file_path = path or BANNERS_FILE
    with open(file_path, encoding="utf-8") as fh:
        raw = json.load(fh)

    banners: list[Banner] = []
    for item in raw.get("banners", []):
        window = item.get("time_window")
        time_window = (int(window[0]), int(window[1])) if window else None
        banners.append(
            Banner(
                key=item["key"],
                name=item["name"],
                name_en=item.get("name_en", item["name"]),
                emoji=item.get("emoji", "🍔"),
                budget_min_cents=yuan(item["budget_min"]),
                budget_max_cents=yuan(item["budget_max"]),
                default_budget_cents=yuan(item.get("default_budget", item["budget_max"])),
                require_tags=tuple(item.get("require_tags", [])),
                prefer_tags=tuple(item.get("prefer_tags", [])),
                time_window=time_window,
                desc=item.get("desc", ""),
            )
        )

    return BannerConfig(
        rarity_weights=raw.get("rarity_weights", {}),
        hard_pity=int(raw.get("hard_pity", 10)),
        pity_note=raw.get("pity_note", ""),
        banners=banners,
    )
