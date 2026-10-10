"""像素风 SVG 分享卡生成。

抽卡结果 → 可直接转发/截图晒群的 SVG 卡片。
零依赖（纯字符串拼装）；PNG 导出需可选依赖 cairosvg（pip install "mcd-gacha[png]"）。

设计约束（合规）：
- 纯自绘像素风格（不使用任何官方 logo/商标素材）；
- 卡片底部固定水印：「非官方开源玩具 · 理性消费」。
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from .models import PullResult, format_price
from .rarity import RARITY_LABELS, Rarity

CARD_WIDTH = 720

# 各稀有度的卡片配色（深底 + 强调色）
THEMES: dict[Rarity, dict[str, str]] = {
    Rarity.SSR: {
        "bg": "#2b1d0a",
        "panel": "#3d2a10",
        "accent": "#F5A623",
        "accent_soft": "#f5a62333",
        "text": "#ffe9c4",
        "muted": "#c9a86a",
    },
    Rarity.SR: {
        "bg": "#231a2e",
        "panel": "#32254150",
        "accent": "#A569BD",
        "accent_soft": "#a569bd33",
        "text": "#efe2f7",
        "muted": "#b89cc9",
    },
    Rarity.R: {
        "bg": "#122230",
        "panel": "#1b3247",
        "accent": "#4A9EDB",
        "accent_soft": "#4a9edb33",
        "text": "#d9ecfa",
        "muted": "#8fb8d4",
    },
    Rarity.N: {
        "bg": "#20262b",
        "panel": "#2d353c",
        "accent": "#8FA3AF",
        "accent_soft": "#8fa3af33",
        "text": "#e3eaef",
        "muted": "#9fb0ba",
    },
}

CATEGORY_EMOJI = {
    "burger": "🍔",
    "snack": "🍟",
    "drink": "🥤",
    "coffee": "☕",
    "deal": "🍱",
}


def _emoji(category: str, tags: tuple[str, ...]) -> str:
    if "dessert" in tags:
        return "🍦"
    return CATEGORY_EMOJI.get(category, "🍽️")


def _esc(text: str) -> str:
    return html.escape(text, quote=True)


def render_card(result: PullResult) -> str:
    """渲染单张分享卡（SVG 文本）。"""
    rarity = result.rarity
    theme = THEMES[rarity]
    accent = theme["accent"]

    # ---- 动态尺寸 ----
    line_h = 54
    items_h = len(result.lines) * line_h + 30
    height = 170 + 140 + items_h + 290 + 100

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{height}" '
        f'viewBox="0 0 {CARD_WIDTH} {height}" '
        f'font-family="ui-monospace, \'Cascadia Mono\', Consolas, Menlo, monospace">'
    )
    # 背景
    parts.append(f'<rect width="{CARD_WIDTH}" height="{height}" rx="24" fill="{theme["bg"]}"/>')
    # 外边框（稀有度色）
    parts.append(
        f'<rect x="10" y="10" width="{CARD_WIDTH - 20}" height="{height - 20}" rx="18" '
        f'fill="none" stroke="{accent}" stroke-width="3" opacity="0.9"/>'
    )
    # 内虚线框（像素风装饰角）
    for (x, y) in ((26, 26), (CARD_WIDTH - 26, 26), (26, height - 26), (CARD_WIDTH - 26, height - 26)):
        parts.append(f'<rect x="{x - 6}" y="{y - 6}" width="12" height="12" fill="{accent}"/>')

    # ---- 头部 ----
    y = 78
    parts.append(
        f'<text x="48" y="{y}" font-size="30" font-weight="bold" fill="{theme["text"]}">'
        f'🎰 麦门抽卡</text>'
    )
    parts.append(
        f'<text x="{CARD_WIDTH - 48}" y="{y}" font-size="20" fill="{theme["muted"]}" '
        f'text-anchor="end">第 {result.pull_index} 抽</text>'
    )
    y += 44
    parts.append(
        f'<text x="48" y="{y}" font-size="18" fill="{theme["muted"]}">'
        f'{_esc(result.banner_name)}</text>'
    )

    # ---- 稀有度横幅 ----
    y += 28
    band_h = 108
    parts.append(
        f'<rect x="40" y="{y}" width="{CARD_WIDTH - 80}" height="{band_h}" rx="14" '
        f'fill="{theme["accent_soft"]}" stroke="{accent}" stroke-width="2"/>'
    )
    spark = "✨ " if rarity is Rarity.SSR else ""
    parts.append(
        f'<text x="{CARD_WIDTH / 2}" y="{y + 50}" font-size="44" font-weight="bold" '
        f'fill="{accent}" text-anchor="middle">{spark}{rarity.value}{spark}</text>'
    )
    parts.append(
        f'<text x="{CARD_WIDTH / 2}" y="{y + 88}" font-size="22" fill="{theme["text"]}" '
        f'text-anchor="middle">{_esc(RARITY_LABELS[rarity])}</text>'
    )

    # ---- 餐品列表 ----
    y += band_h + 46
    for line in result.lines:
        emoji = _emoji(line.meal.category, line.meal.tags)
        name = line.meal.name + (f" ×{line.qty}" if line.qty > 1 else "")
        parts.append(
            f'<text x="56" y="{y}" font-size="26" fill="{theme["text"]}">'
            f'{emoji} {_esc(name)}</text>'
        )
        parts.append(
            f'<text x="{CARD_WIDTH - 56}" y="{y}" font-size="26" fill="{theme["muted"]}" '
            f'text-anchor="end">¥{line.meal.price_yuan}</text>'
        )
        y += line_h
    y += 10

    # 分隔线
    parts.append(
        f'<line x1="48" y1="{y}" x2="{CARD_WIDTH - 48}" y2="{y}" stroke="{accent}" '
        f'stroke-width="2" opacity="0.5" stroke-dasharray="8 6"/>'
    )
    y += 56

    # ---- 价格区 ----
    quote = result.quote
    if quote.discount_cents > 0:
        parts.append(
            f'<text x="56" y="{y}" font-size="22" fill="{theme["muted"]}">原价 '
            f'¥{format_price(quote.original_cents)}  →  券后</text>'
        )
        y += 54
        parts.append(
            f'<text x="56" y="{y}" font-size="46" font-weight="bold" fill="{accent}">'
            f'¥{format_price(quote.paid_cents)}</text>'
        )
        parts.append(
            f'<text x="{CARD_WIDTH - 56}" y="{y}" font-size="24" fill="{theme["text"]}" '
            f'text-anchor="end">省 ¥{format_price(quote.discount_cents)}'
            f'{f"（{_esc(quote.coupon_name)}）" if quote.coupon_name else ""}</text>'
        )
    else:
        parts.append(
            f'<text x="56" y="{y}" font-size="22" fill="{theme["muted"]}">实付</text>'
        )
        y += 54
        parts.append(
            f'<text x="56" y="{y}" font-size="46" font-weight="bold" fill="{theme["text"]}">'
            f'¥{format_price(quote.paid_cents)}</text>'
        )
    y += 64

    # 热量与来源
    meta_bits: list[str] = []
    if result.total_calories is not None:
        meta_bits.append(f"🔥 {result.total_calories} kcal")
    meta_bits.append("🛰 真实核价" if result.data_source == "mcp" else "📦 演示快照")
    parts.append(
        f'<text x="56" y="{y}" font-size="20" fill="{theme["muted"]}">'
        f'{_esc("  ·  ".join(meta_bits))}</text>'
    )

    # ---- 文案 ----
    y += 52
    if result.flavor:
        parts.append(
            f'<text x="{CARD_WIDTH / 2}" y="{y}" font-size="21" fill="{theme["text"]}" '
            f'text-anchor="middle" font-style="italic">「{_esc(result.flavor)}」</text>'
        )

    # ---- 底部水印 ----
    ts = (result.ts or datetime.now()).strftime("%Y-%m-%d %H:%M")
    footer_y = height - 44
    parts.append(
        f'<text x="48" y="{footer_y}" font-size="15" fill="{theme["muted"]}" opacity="0.85">'
        f'{ts} · Mcd-Gacha · 非官方开源玩具 · 理性消费</text>'
    )
    parts.append(
        f'<text x="{CARD_WIDTH - 48}" y="{footer_y}" font-size="15" fill="{theme["muted"]}" '
        f'text-anchor="end" opacity="0.85">github/mcd-gacha</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts)


def save_card(result: PullResult, path: str | Path) -> Path:
    """保存分享卡为 SVG 文件。"""
    target = Path(path)
    if target.suffix.lower() != ".svg":
        target = target.with_suffix(".svg")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_card(result), encoding="utf-8")
    return target


def try_export_png(svg_text: str, path: str | Path) -> Path | None:
    """尝试导出 PNG（需要 cairosvg；未安装时返回 None）。"""
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        return None
    target = Path(path).with_suffix(".png")
    target.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), write_to=str(target), scale=2)
    return target
