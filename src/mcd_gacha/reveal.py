"""开箱结果渲染（rich）。

- play_reveal：开箱动画（光柱连接 → 命运蓄力 → 稀有度检定）+ 结果面板；
- render_pull / render_ten：静态结果渲染。

动画在以下环境自动降级为直出结果：
--no-anim、NO_COLOR、TERM=dumb、非 TTY（管道/CI）、--json。
"""

from __future__ import annotations

import os
import time

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .models import LineItem, PullResult, format_price
from .rarity import RARITY_HEX, RARITY_LABELS, RARITY_RICH_STYLE, Rarity

CATEGORY_EMOJI = {
    "burger": "🍔",
    "snack": "🍟",
    "drink": "🥤",
    "coffee": "☕",
    "deal": "🍱",
}


def _emoji(line: LineItem) -> str:
    if "dessert" in line.meal.tags:
        return "🍦"
    return CATEGORY_EMOJI.get(line.meal.category, "🍽️")


def pity_bar(current: int, limit: int = 10) -> str:
    """保底进度条：current 为连续未出金计数。"""
    filled = min(current, limit)
    return "█" * filled + "░" * (limit - filled) + f" {current}/{limit}"


# ---------------------------------------------------------------------------
# 开箱动画
# ---------------------------------------------------------------------------


def _should_animate(console: Console, animate: bool) -> bool:
    """环境判断：不支持动画时降级为直出结果。"""
    if not animate:
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return bool(console.is_terminal)


def play_reveal(result: PullResult, console: Console, *, animate: bool = True) -> None:
    """播放开箱动画后渲染结果面板（动画不支持的场景自动降级）。"""
    if _should_animate(console, animate):
        _run_reveal_animation(result, console)
    render_pull(result, console)


def _run_reveal_animation(result: PullResult, console: Console) -> None:
    """开箱动画：光柱连接 → 命运蓄力 → 稀有度检定（SSR 强化）。"""
    rarity = result.rarity
    style = RARITY_RICH_STYLE[rarity]
    border = RARITY_HEX[rarity]
    is_ssr = rarity is Rarity.SSR

    def frame(text: Text, border_style: str = "dim") -> Panel:
        return Panel(text, border_style=border_style, padding=(0, 4), expand=False)

    with Live(console=console, refresh_per_second=30, transient=True) as live:
        # 1) 光柱连接（点号流动）
        for dots in ("", "·", "··", "···"):
            live.update(
                frame(Text(f"🔌 连接金拱门量子服务器{dots}", style="dim", justify="center"))
            )
            time.sleep(0.07)

        # 2) 命运蓄力（进度条；SSR 时更慢更郑重）
        percentages = (12, 28, 45, 62, 78, 90, 100) if is_ssr else (25, 55, 85, 100)
        for pct in percentages:
            filled = round(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)
            live.update(
                frame(Text(f"⚡ 命运蓄力中 {bar} {pct}%", justify="center"))
            )
            time.sleep(0.05 if not is_ssr else 0.07)

        # 3) 稀有度检定（颜色闪烁）
        sparks = "✦ ✦ ✦"
        flashes = 6 if is_ssr else 4
        for i in range(flashes):
            flicker_style = style if i % 2 == 0 else "dim"
            live.update(frame(Text(sparks, style=flicker_style, justify="center"), border))
            time.sleep(0.1)

        # 4) 出金强化（仅 SSR：金色传说演出）
        if is_ssr:
            for text, text_style in (
                ("✨ ✨ ✨", "bold yellow"),
                ("💫 💫 💫", "bold goldenrod1"),
                ("🌟 金色传说 🌟", "bold yellow"),
            ):
                live.update(frame(Text(text, style=text_style, justify="center"), border))
                time.sleep(0.14)

    console.print(f"  [{style}]━ 稀有度检定：{rarity.value} ━[/{style}]", justify="center")


def render_pull(result: PullResult, console: Console) -> None:
    """渲染单抽结果面板。"""
    rarity = result.rarity
    style = RARITY_RICH_STYLE[rarity]
    border = RARITY_HEX[rarity]

    body = Text()
    for line in result.lines:
        body.append(f"{_emoji(line)} {line.meal.name}", style="bold")
        if line.qty > 1:
            body.append(f" ×{line.qty}", style="bold")
        body.append(f"   ¥{line.meal.price_yuan}\n", style="dim")

    body.append("\n")
    quote = result.quote
    if quote.discount_cents > 0:
        body.append("原价 ", style="dim")
        body.append(f"¥{format_price(quote.original_cents)}", style="dim strike")
        body.append("  →  ")
        body.append(f"券后 ¥{format_price(quote.paid_cents)}", style="bold green")
        body.append(
            f"（{quote.coupon_name} · 省 ¥{format_price(quote.discount_cents)}）\n", style="green"
        )
    else:
        body.append(f"实付 ¥{format_price(quote.paid_cents)}", style="bold")
        body.append("（本单无可用券）\n", style="dim")

    if result.total_calories is not None:
        body.append(f"总热量 {result.total_calories} kcal\n", style="dim")

    sparkle = "✨ " if rarity is Rarity.SSR else ""
    title = f"{sparkle}{rarity.value} · {RARITY_LABELS[rarity]}{' ✨' if rarity is Rarity.SSR else ''}"

    console.print()
    console.print(
        f"[{style}]{'━' * 3} 开 箱 {'━' * 3}[/{style}]",
        justify="center",
    )
    from rich.panel import Panel

    console.print(Panel(body, title=title, border_style=border, padding=(1, 2), expand=False))

    if result.flavor:
        console.print(f"  [italic dim]{result.flavor}[/italic dim]")
    console.print(
        f"  [dim]保底进度 {pity_bar(result.pity_after)}（再抽 "
        f"{max(10 - result.pity_after, 1)} 发内必出金）[/dim]"
    )
    console.print(
        "  [dim]💡 不满意某一件？[bold]mcd-gacha reroll --slot <件位>[/bold] 可重铸（不耗保底）[/dim]"
    )
    console.print()


def render_ten(results: list[PullResult], console: Console) -> None:
    """渲染十连结果：明细表 + 汇总。"""
    if not results:
        console.print("[yellow]没有可展示的结果。[/yellow]")
        return

    table = Table(
        title=f"🎰 十连 · {results[0].banner_name}",
        title_style="bold",
        border_style="dim",
        header_style="bold",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("稀有度", width=6)
    table.add_column("组合", min_width=30)
    table.add_column("原价", justify="right", width=8)
    table.add_column("实付", justify="right", width=8)
    table.add_column("省", justify="right", width=7)

    ssr_count = 0
    best_discount = 0
    for result in results:
        style = RARITY_RICH_STYLE[result.rarity]
        combo_desc = " + ".join(
            f"{line.meal.name}" + (f"×{line.qty}" if line.qty > 1 else "")
            for line in result.lines
        )
        if result.rarity is Rarity.SSR:
            ssr_count += 1
        best_discount = max(best_discount, result.quote.discount_cents)
        table.add_row(
            str(result.pull_index),
            Text(result.rarity.value, style=style),
            combo_desc,
            f"¥{format_price(result.quote.original_cents)}",
            f"¥{format_price(result.quote.paid_cents)}",
            f"¥{format_price(result.quote.discount_cents)}" if result.quote.discount_cents else "-",
        )

    console.print()
    console.print(table)

    total_paid = sum(r.quote.paid_cents for r in results)
    total_original = sum(r.quote.original_cents for r in results)
    total_saved = sum(r.quote.discount_cents for r in results)
    sr_count = sum(1 for r in results if r.rarity is Rarity.SR)
    n_count = sum(1 for r in results if r.rarity is Rarity.N)

    console.print(
        f"  📊 十连战报：[bold]出金 {ssr_count} 次[/bold]、紫光 {sr_count} 次、隐藏款 {n_count} 次；"
        f"原价合计 ¥{format_price(total_original)} → [bold green]实付 ¥{format_price(total_paid)}[/bold green]"
        f"（省 ¥{format_price(total_saved)}）"
    )
    if ssr_count > 0:
        console.print("  🎉 [bold yellow]金光护体！建议立即截图晒卡。[/bold yellow]")
    last = results[-1]
    console.print(f"  [dim]保底进度 {pity_bar(last.pity_after)}[/dim]")
    console.print()
