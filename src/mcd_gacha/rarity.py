"""稀有度定义、权重与视觉风格。

概率设计（基础值）：SSR 5% / SR 25% / R 60% / N 10%。
配合 10 发硬保底后，SSR 的有效出率约为 12.5%（平均约 8 抽见金），
详见 docs/design.md 与 `mcd-gacha simulate` 的蒙特卡洛自证。
"""

from __future__ import annotations

from enum import Enum


class Rarity(str, Enum):
    """抽卡稀有度。"""

    SSR = "SSR"
    SR = "SR"
    R = "R"
    N = "N"


# 基础权重（合计 100，单位为百分比）
RARITY_WEIGHTS: dict[Rarity, int] = {
    Rarity.SSR: 5,
    Rarity.SR: 25,
    Rarity.R: 60,
    Rarity.N: 10,
}

# 展示标签（文案已按合规要求柔化：不贬损、倡导理性消费）
RARITY_LABELS: dict[Rarity, str] = {
    Rarity.SSR: "金卡 · 欧皇时刻",
    Rarity.SR: "紫卡 · 稳稳的幸福",
    Rarity.R: "蓝卡 · 经典保底",
    Rarity.N: "隐藏灰卡 · 抽象艺术",
}

# 短标签（用于表格、分享卡徽章）
RARITY_SHORT: dict[Rarity, str] = {
    Rarity.SSR: "欧皇金光",
    Rarity.SR: "紫光小赚",
    Rarity.R: "蓝光普照",
    Rarity.N: "隐藏款",
}

# 分享卡 / 终端主题色（hex，暖色系为主）
RARITY_HEX: dict[Rarity, str] = {
    Rarity.SSR: "#F5A623",
    Rarity.SR: "#8E44AD",
    Rarity.R: "#2980B9",
    Rarity.N: "#7F8C8D",
}

# rich 样式名（终端动画与文本着色）
RARITY_RICH_STYLE: dict[Rarity, str] = {
    Rarity.SSR: "bold yellow",
    Rarity.SR: "bold magenta",
    Rarity.R: "bold blue",
    Rarity.N: "bold grey62",
}

# 星级图形（分享卡用）
RARITY_STARS: dict[Rarity, str] = {
    Rarity.SSR: "★★★★★",
    Rarity.SR: "★★★★",
    Rarity.R: "★★★",
    Rarity.N: "★★",
}
