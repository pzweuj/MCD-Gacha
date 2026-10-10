"""本地状态持久化：保底计数、抽卡历史与统计。

默认路径：<配置目录>/state.json（MCD_GACHA_HOME 可覆盖）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SCHEMA_VERSION = 1
MAX_HISTORY = 100


@dataclass
class GachaState:
    """抽卡状态。pity 按卡池独立计数。"""

    pity: dict[str, int] = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)
    last_pull_date: str | None = None  # 最近一次抽卡日期（ISO，用于「今日首抽」提示）
    daily_count: int = 0  # 今日已抽次数（惰性重置）
    stats: dict[str, int] = field(default_factory=dict)
    # 最近一次抽卡结果（用于「重铸」：替换组合中的某一件）
    last_result: dict | None = None

    def pity_for(self, banner_key: str) -> int:
        return int(self.pity.get(banner_key, 0))

    def bump_daily(self, today: str) -> int:
        """返回今日第几抽（1 起），并维护计数。"""
        if self.last_pull_date != today:
            self.last_pull_date = today
            self.daily_count = 0
        self.daily_count += 1
        return self.daily_count

    def record_stats(self, rarity_value: str) -> None:
        self.stats["total"] = self.stats.get("total", 0) + 1
        self.stats[rarity_value] = self.stats.get(rarity_value, 0) + 1

    def golden_rate(self) -> float:
        total = self.stats.get("total", 0)
        if total <= 0:
            return 0.0
        return self.stats.get("SSR", 0) / total


def load_state(path: Path | None = None) -> GachaState:
    """加载本地状态；文件不存在或损坏时返回全新状态。"""
    from .config import get_state_file

    file_path = path or get_state_file()
    if not file_path.exists():
        return GachaState()
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return GachaState()
    return GachaState(
        pity=dict(raw.get("pity", {})),
        history=list(raw.get("history", [])),
        last_pull_date=raw.get("last_pull_date"),
        daily_count=int(raw.get("daily_count", 0)),
        stats=dict(raw.get("stats", {})),
        last_result=raw.get("last_result"),
    )


def save_state(state: GachaState, path: Path | None = None) -> Path:
    """保存本地状态（历史裁剪至最近 100 条）。"""
    from .config import get_state_file

    file_path = path or get_state_file()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pity": state.pity,
        "history": state.history[-MAX_HISTORY:],
        "last_pull_date": state.last_pull_date,
        "daily_count": state.daily_count,
        "stats": state.stats,
        "last_result": state.last_result,
    }
    file_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return file_path


def mark_first_pull_of_day(state: GachaState, today: date) -> bool:
    """判断今天是否还没抽过（用于「今日首抽」展示）。"""
    return state.last_pull_date != today.isoformat()
