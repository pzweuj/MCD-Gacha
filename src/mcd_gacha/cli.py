"""Mcd-Gacha 命令行入口。

命令一览：
  pull      单抽（默认 auto 卡池，按时段自动选择）
  ten       十连（共享保底计数器）
  reroll    重铸（替换组合中的某一件）
  order     下单（提交最近一次真实组合；安全闸门：默认只试运行）
  banners   卡池一览与开放状态
  status    保底进度与生涯统计
  simulate  概率自证（蒙特卡洛模拟）
  config    本地配置（MCP Token 等）
"""

from __future__ import annotations

import asyncio
import contextlib
import json as jsonlib
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .banners import load_banner_config
from .config import (
    get_config_file,
    get_state_file,
    get_store_settings,
    get_token,
    get_token_with_source,
    mask_token,
    save_store_settings,
    save_token,
)
from .datasource import MockDataSource
from .datasource.base import MenuDataSource
from .engine import GachaError, McdGacha
from .models import LineItem, Store, format_price
from .rarity import RARITY_RICH_STYLE, Rarity
from .reveal import pity_bar, play_reveal, render_pull, render_ten
from .state import load_state

app = typer.Typer(
    name="mcd-gacha",
    help="麦门抽卡模拟器：用二游抽卡机制决定「中午吃什么」。非官方第三方开源玩具。",
    no_args_is_help=True,
    add_completion=False,
)
config_app = typer.Typer(help="本地配置（MCP Token 等）", no_args_is_help=True)
app.add_typer(config_app, name="config")

console = Console()

# 卡池代号简写
BANNER_ALIASES = {
    "poor": "poor_standard",
    "worker": "worker_up",
    "up": "worker_up",
    "midnight": "midnight",
    "night": "midnight",
}


def _resolve_banner(banner: str, now: datetime) -> str:
    """解析卡池代号；auto 按时段选择（深夜->宵夜池，其余->常驻池）。"""
    key = banner.strip().lower()
    if key == "auto":
        return "midnight" if (now.hour >= 21 or now.hour < 4) else "poor_standard"
    return BANNER_ALIASES.get(key, key)


async def _open_source(use_real: bool, use_mock: bool) -> tuple[MenuDataSource, str]:
    """创建数据源，返回 (数据源, 状态提示文案)。"""
    if use_real and use_mock:
        raise typer.BadParameter("--real 与 --mock 不能同时使用")

    if use_mock:
        return MockDataSource(), "[dim]📦 内置演示数据（菜单快照）[/dim]"

    token = get_token()
    if token is None:
        if use_real:
            return (
                MockDataSource(),
                "[yellow]⚠️ 未找到 MCP Token，本次使用内置演示数据"
                "（可运行 mcd-gacha config set-token <TOKEN> 配置）[/yellow]",
            )
        return MockDataSource(), "[dim]📦 内置演示数据（菜单快照）[/dim]"

    source = None
    try:
        from .datasource.mcp import McpDataSource

        store_code, city = get_store_settings()
        source = McpDataSource(token=token, store_code=store_code, city=city)
        await source.start()
        # 连通性 + 可售性探测：连接成功不代表能取到菜单（例如门店已打烊会返回
        # code=600057）。若只在 start() 层面兜底，这类运行期错误会一路抛到引擎、
        # 直接中断抽卡，与「真实接口异常自动回退演示数据」的承诺不符。
        # 探测结果会被数据源缓存，引擎后续调用不会产生额外请求。
        await source.query_meals()
        store_note = ""
        if getattr(source, "_store", None) and source._store.name:
            store_note = f" · 门店：{source._store.name}"
        return source, f"[green]🔗 麦当劳 MCP 已连接（真实在线核价{store_note}）[/green]"
    except Exception as exc:  # noqa: BLE001 —— 网络/鉴权/依赖缺失统一回退 mock
        if source is not None:
            with contextlib.suppress(Exception):  # 关闭失败不影响回退
                await source.close()
        return (
            MockDataSource(),
            f"[yellow]⚠️ 真实 MCP 暂不可用（{exc}），已回退内置演示数据[/yellow]",
        )


# ---------------------------------------------------------------------------
# 命令
# ---------------------------------------------------------------------------


@app.command()
def pull(
    banner: str = typer.Option(
        "auto", "-b", "--banner", help="卡池：auto / poor / worker / midnight"
    ),
    budget: float | None = typer.Option(
        None, "--budget", help="预算上限（元），默认取卡池默认值"
    ),
    real: bool = typer.Option(False, "--real", help="使用真实麦当劳 MCP（需 Token）"),
    mock: bool = typer.Option(False, "--mock", help="强制使用内置演示数据"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 格式输出（脚本友好）"),
    no_anim: bool = typer.Option(False, "--no-anim", help="关闭开箱动画"),
    save_card_path: str | None = typer.Option(
        None, "--save-card", help="保存 SVG 分享卡到指定路径"
    ),
) -> None:
    """单抽：把今天的午饭交给命运。"""
    if budget is not None and budget <= 0:
        raise typer.BadParameter("--budget 必须大于 0")
    asyncio.run(_pull_impl(banner, budget, real, mock, as_json, save_card_path, no_anim))


async def _pull_impl(
    banner: str,
    budget: float | None,
    real: bool,
    mock: bool,
    as_json: bool,
    save_card_path: str | None = None,
    no_anim: bool = False,
) -> None:
    source, note = await _open_source(real, mock)
    engine = McdGacha(source, state=load_state())
    try:
        key = _resolve_banner(banner, await source.now_time())
        result = await engine.roll(key, budget)
    except (GachaError, KeyError) as exc:
        console.print(f"[red]❌ {exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        await engine.close()

    if as_json:
        typer.echo(jsonlib.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(note)
        play_reveal(result, console, animate=not no_anim)
        if save_card_path:
            _save_card(result, save_card_path)


@app.command()
def reroll(
    slot: int = typer.Option(..., "--slot", "-s", help="要重铸的件位（从 1 开始）"),
    real: bool = typer.Option(False, "--real", help="使用真实麦当劳 MCP（需 Token）"),
    mock: bool = typer.Option(False, "--mock", help="强制使用内置演示数据"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 格式输出"),
) -> None:
    """重铸：替换上次组合中的某一件（同品类，不影响保底进度）。"""
    asyncio.run(_reroll_impl(slot, real, mock, as_json))


async def _reroll_impl(slot: int, real: bool, mock: bool, as_json: bool) -> None:
    source, note = await _open_source(real, mock)
    engine = McdGacha(source, state=load_state())
    try:
        # 旧件名称（用于展示"旧 → 新"对比）
        last = engine.state.last_result or {}
        old_items = last.get("items") or []
        old_name: str | None = None
        if 1 <= slot <= len(old_items):
            meals = await source.query_meals()
            meal_by_code = {meal.code: meal for meal in meals}
            old_meal = meal_by_code.get(str(old_items[slot - 1].get("code")))
            old_name = old_meal.name if old_meal else None
        result = await engine.reroll(slot)
    except (GachaError, KeyError) as exc:
        console.print(f"[red]❌ {exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        await engine.close()

    if as_json:
        typer.echo(jsonlib.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(note)
        if old_name and slot <= len(result.lines):
            new_name = result.lines[slot - 1].meal.name
            console.print(
                f"  🔨 重铸第 {slot} 件：[dim strike]{old_name}[/dim strike]"
                f" → [bold]{new_name}[/bold]"
            )
        render_pull(result, console)


def _save_card(result, save_card_path: str) -> None:
    """保存分享卡（SVG + 可选 PNG）。"""
    from .share_card import render_card, save_card, try_export_png

    path = save_card(result, save_card_path)
    console.print(f"  🖼️ 分享卡已保存：{path}")
    png = try_export_png(render_card(result), path)
    if png:
        console.print(f"  🖼️ PNG 版本：{png}")
    else:
        console.print('  [dim]（提示：pip install "mcd-gacha\\[png]" 可导出 PNG）[/dim]')


@app.command()
def ten(
    banner: str = typer.Option(
        "auto", "-b", "--banner", help="卡池：auto / poor / worker / midnight"
    ),
    budget: float | None = typer.Option(
        None, "--budget", help="预算上限（元），默认取卡池默认值"
    ),
    real: bool = typer.Option(False, "--real", help="使用真实麦当劳 MCP（需 Token）"),
    mock: bool = typer.Option(False, "--mock", help="强制使用内置演示数据"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 格式输出（脚本友好）"),
    save_card_dir: str | None = typer.Option(
        None, "--save-card", help="保存十连分享卡到指定目录（十张 SVG）"
    ),
) -> None:
    """十连：共享保底计数器，第 10 发必出金（若前 9 发未出）。"""
    if budget is not None and budget <= 0:
        raise typer.BadParameter("--budget 必须大于 0")
    asyncio.run(_ten_impl(banner, budget, real, mock, as_json, save_card_dir))


async def _ten_impl(
    banner: str,
    budget: float | None,
    real: bool,
    mock: bool,
    as_json: bool,
    save_card_dir: str | None = None,
) -> None:
    source, note = await _open_source(real, mock)
    engine = McdGacha(source, state=load_state())
    try:
        key = _resolve_banner(banner, await source.now_time())
        results = await engine.ten_pull(key, budget)
    except (GachaError, KeyError) as exc:
        console.print(f"[red]❌ {exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        await engine.close()

    if as_json:
        payload = [r.to_dict() for r in results]
        typer.echo(jsonlib.dumps(payload, ensure_ascii=False, indent=2))
    else:
        console.print(note)
        render_ten(results, console)
        if save_card_dir:
            from pathlib import Path

            from .share_card import save_card

            out_dir = Path(save_card_dir)
            saved = []
            for item in results:
                path = save_card(item, out_dir / f"gacha_{item.pull_index:02d}_{item.rarity.value}.svg")
                saved.append(path)
            console.print(f"  🖼️ 已保存 {len(saved)} 张分享卡到：{out_dir.resolve()}")


@app.command()
def order(
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="确认下单（不加则仅试运行，不会产生真实订单）",
    ),
    be_type: int = typer.Option(1, "--be-type", help="1-到店自取（当前仅支持这一种）"),
    store_code: str | None = typer.Option(
        None,
        "--store-code",
        help="下单门店编号（用于换店/换地点；留空则用本地配置或自动最近门店）",
    ),
    city: str | None = typer.Option(
        None, "--city", help="搜索候选门店的城市（留空用本地配置的城市）"
    ),
    address_id: str | None = typer.Option(
        None, "--address-id", help="外送地址 ID（外送场景预留，暂未实现）"
    ),
    take_way_code: str | None = typer.Option(
        None,
        "--take-way-code",
        help="取餐方式 code（如 eat-in 堂食 / locker-in 取餐柜；留空用试运行给出的默认项）",
    ),
    remark: str | None = typer.Option(None, "--remark", help="订单备注（最多 50 字）"),
    as_json: bool = typer.Option(False, "--json", help="以 JSON 格式输出"),
) -> None:
    """下单：把最近一次抽到的组合提交给麦当劳 MCP（默认只试运行）。

    典型用法（先抽卡，下单时再确认地点与取餐方式）：

        mcd-gacha pull --real            # 1. 抽卡
        mcd-gacha order --json           # 2. 试运行：返回候选门店 + 取餐方式
        mcd-gacha order --confirm \\
            --store-code 1421182 --take-way-code eat-in   # 3. 确认后真实下单
    """
    asyncio.run(
        _order_impl(
            confirm,
            be_type,
            store_code,
            city,
            address_id,
            take_way_code,
            remark,
            as_json,
        )
    )


async def _order_impl(
    confirm: bool,
    be_type: int,
    store_code_opt: str | None,
    city_opt: str | None,
    address_id: str | None,
    take_way_code: str | None,
    remark: str | None,
    as_json: bool,
) -> None:
    last = load_state().last_result
    if not last or not last.get("items"):
        console.print("[red]❌ 还没有抽卡结果——先运行 mcd-gacha pull --real 抽一发。[/red]")
        raise typer.Exit(code=1)

    if be_type != 1:
        console.print(
            "[red]❌ 当前仅支持到店自取（--be-type 1）；"
            "外送 / 得来速 / 团餐下单尚未实现。[/red]"
        )
        raise typer.Exit(code=2)

    # 安全闸门之一：演示数据的编码不是真实 SKU，直接拒绝，避免产生无效订单
    if last.get("data_source") == "mock":
        console.print(
            "[red]❌ 最近一次抽卡用的是内置演示数据，商品编码不是真实 SKU，无法下单。[/red]"
        )
        console.print("   [dim]请先运行：mcd-gacha pull --real 抽到真实菜单组合。[/dim]")
        raise typer.Exit(code=1)

    token = get_token()
    if token is None:
        console.print(
            "[red]❌ 下单需要真实 MCP Token（mcd-gacha config set-token <TOKEN>）。[/red]"
        )
        raise typer.Exit(code=1)

    config_store_code, config_city = get_store_settings()
    # 下单时允许覆盖门店（地点确认）：命令行 > 本地配置 > 按城市自动选最近门店
    store_code = store_code_opt or config_store_code
    use_city = city_opt or config_city
    if not store_code and not use_city:
        console.print(
            "[red]❌ 未配置门店，请先 mcd-gacha config set-store --city <城市名>[/red]"
        )
        raise typer.Exit(code=1)

    from .datasource.mcp import McpDataSource

    source = McpDataSource(token=token, store_code=store_code, city=use_city)
    result = None
    try:
        await source.start()
        meals = await source.query_meals()
        meal_by_code = {meal.code: meal for meal in meals}
        lines: list[LineItem] = []
        for item in last["items"]:
            meal = meal_by_code.get(str(item.get("code")))
            if meal is None:
                console.print(
                    "[red]❌ 组合中有商品已不在当前菜单"
                    "（可能已下架或售罄），请重新抽卡。[/red]"
                )
                raise typer.Exit(code=1)
            lines.append(LineItem(meal=meal, qty=int(item.get("qty", 1))))

        # 下单前重新核价：价格与库存可能已变化，且核价返回到店下单必需的 takeWayList
        quote = await source.calculate_price(lines)

        # 取餐方式候选项（来自本次核价；下单必选其一）
        take_ways = list(getattr(source, "take_way_options", []) or [])
        default_take_way = getattr(source, "default_take_way", None) or (
            take_ways[0].code if take_ways else None
        )

        # 候选门店（同城），供用户抽完卡后再确认「去哪儿取」
        nearby: list[Store] = []
        if use_city:
            try:
                nearby = await source.nearby_stores()
            except Exception:  # noqa: BLE001 —— 门店列表失败不影响主流程
                nearby = []
        name_by_code = {s.code: s.name for s in nearby}
        store_obj = getattr(source, "_store", None)
        store_label = (
            name_by_code.get(source.store_code or "")
            or (store_obj.name if store_obj else "")
            or (store_code or use_city or "")
        )

        if not confirm:
            preview = {
                "mode": "dry_run",
                "store": {
                    "code": source.store_code,
                    "name": store_label,
                    "city": use_city or "",
                },
                "stores": [
                    {"code": s.code, "name": s.name, "address": s.address} for s in nearby
                ],
                "take_way": [tw.to_dict() for tw in take_ways],
                "take_way_default": default_take_way,
                "be_type": be_type,
                "items": [
                    {
                        "code": line.meal.code,
                        "name": line.meal.name,
                        "qty": line.qty,
                        "price": line.meal.price_yuan,
                    }
                    for line in lines
                ],
                "price": {
                    "original": format_price(quote.original_cents),
                    "discount": format_price(quote.discount_cents),
                    "paid": format_price(quote.paid_cents),
                },
                "need_confirm": True,
                "confirm_hint": _order_confirm_hint(source.store_code, default_take_way),
            }
            if as_json:
                typer.echo(jsonlib.dumps(preview, ensure_ascii=False, indent=2))
            else:
                _render_order_preview(
                    store_label,
                    source.store_code,
                    lines,
                    quote,
                    nearby,
                    take_ways,
                    default_take_way,
                )
            return

        chosen_take_way = take_way_code or default_take_way
        if not as_json:
            console.print(
                f"\n  [yellow]⚠️ 即将真实下单[/yellow]：{len(lines)} 件 · "
                f"门店 {store_label} · 预计实付 ¥{format_price(quote.paid_cents)}"
            )
        result = await source.create_order(
            lines,
            be_type=be_type,
            order_type=1,
            address_id=address_id,
            take_way_code=chosen_take_way,
            remark=remark,
        )
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 —— 网络/鉴权/业务错误统一提示
        console.print(f"[red]❌ 下单失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc
    finally:
        await source.close()

    if result is None:
        raise typer.Exit(code=1)
    if as_json:
        typer.echo(jsonlib.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        _render_order_result(result)


def _order_confirm_hint(store_code: str | None, take_way: str | None) -> str:
    """生成「确认下单」命令提示（含所选门店与取餐方式）。"""
    parts = ["mcd-gacha order --confirm"]
    if store_code:
        parts.append(f"--store-code {store_code}")
    if take_way:
        parts.append(f"--take-way-code {take_way}")
    return " ".join(parts)


def _render_order_preview(
    store_label: str,
    store_code: str | None,
    lines: list[LineItem],
    quote,
    stores: list,
    take_ways: list,
    default_take_way: str | None,
) -> None:
    """试运行预览：展示将要下单的组合、可选门店与取餐方式，不产生任何订单。"""
    console.print("\n[bold]🧾 下单预览（试运行）[/bold]")
    console.print(f"  🏪 当前门店：{store_label or '（未指定）'}")

    # 可选门店（地点确认）
    if stores:
        console.print("\n  [bold]📍 可选门店[/bold]（用 --store-code 指定，留空则用当前门店）")
        store_table = Table(border_style="dim", header_style="bold")
        store_table.add_column("#", justify="right")
        store_table.add_column("门店")
        store_table.add_column("门店编号", justify="right")
        store_table.add_column("地址", style="dim")
        for index, store in enumerate(stores, start=1):
            store_table.add_row(str(index), store.name, store.code, store.address or "—")
        console.print(store_table)

    # 取餐方式（下单必选）
    if take_ways:
        console.print("\n  [bold]🥡 取餐方式[/bold]（用 --take-way-code 指定，留空用默认）")
        take_table = Table(border_style="dim", header_style="bold")
        take_table.add_column("#", justify="right")
        take_table.add_column("取餐方式")
        take_table.add_column("code")
        take_table.add_column("", style="dim")
        for index, take_way in enumerate(take_ways, start=1):
            mark = "默认" if take_way.code == default_take_way else ""
            take_table.add_row(
                str(index), take_way.title or "—", take_way.code, mark
            )
        console.print(take_table)

    table = Table(title="🍔 本次组合", border_style="dim", header_style="bold")
    table.add_column("餐品")
    table.add_column("数量", justify="right")
    table.add_column("小计", justify="right")
    for line in lines:
        table.add_row(line.meal.name, f"×{line.qty}", f"¥{line.meal.price_yuan}")
    console.print(table)
    console.print(
        f"  原价 ¥{format_price(quote.original_cents)} → "
        f"券后实付 [bold]¥{format_price(quote.paid_cents)}[/bold]"
    )
    console.print(
        "\n  [yellow]⚠️ 以上为试运行，未产生任何订单。[/yellow]"
        "确认地点与取餐方式后，执行：\n"
        f"  [bold]{_order_confirm_hint(store_code, default_take_way)}[/bold]\n"
        "  [dim]（--store-code 换门店、--take-way-code 换取餐方式，均可自定义）[/dim]\n"
    )


def _render_order_result(result) -> None:
    """展示下单结果（订单号 / 支付链接 / 原始返回）。"""
    console.print("\n[bold]🧾 下单结果[/bold]")
    if result.order_id:
        console.print(f"  📦 订单号：{result.order_id}")
    if result.paid_cents is not None:
        console.print(f"  💰 应付：¥{format_price(result.paid_cents)}")
    if result.pay_url:
        console.print(f"  🔗 支付链接：[cyan]{result.pay_url}[/cyan]")
        console.print("  [dim]请在有效期内打开链接完成支付（本项目不代付）。[/dim]")
    if result.status:
        console.print(f"  📌 状态：{result.status}")
    if not result.order_id and not result.pay_url:
        console.print("  [yellow]未能识别订单号/支付链接，原始返回如下：[/yellow]")
        typer.echo(jsonlib.dumps(result.raw, ensure_ascii=False, indent=2))
    else:
        console.print(
            f"  [dim]原始返回：{jsonlib.dumps(result.raw, ensure_ascii=False)}[/dim]"
        )
    console.print()


@app.command()
def banners() -> None:
    """查看全部卡池与当前开放状态。"""
    config = load_banner_config()
    now = datetime.now().astimezone()

    table = Table(title="🎴 卡池一览", title_style="bold", border_style="dim")
    table.add_column("卡池", min_width=22)
    table.add_column("代号", style="cyan")
    table.add_column("预算", justify="right")
    table.add_column("状态", justify="center")
    table.add_column("说明", style="dim", max_width=42)

    for banner in config.banners:
        window = ""
        if banner.time_window:
            window = f"{banner.time_window[0]:02d}:00-{banner.time_window[1]:02d}:00"
        status = "[green]✅ 开放中[/green]" if banner.is_available(now) else "[yellow]⏰ 限时[/yellow]"
        table.add_row(
            f"{banner.emoji} {banner.name}",
            banner.key,
            f"¥{format_price(banner.budget_min_cents)}-{format_price(banner.budget_max_cents)}",
            status,
            (f"限时 {window} · " if window else "") + banner.desc,
        )

    console.print()
    console.print(table)
    console.print(f"\n  [dim]{config.pity_note}[/dim]\n")


@app.command()
def status() -> None:
    """查看保底进度与生涯统计。"""
    config = load_banner_config()
    state = load_state()

    console.print("\n[bold]🎯 各卡池保底进度[/bold]")
    for banner in config.banners:
        current = state.pity_for(banner.key)
        console.print(f"  {banner.emoji} {banner.name}：{pity_bar(current, config.hard_pity)}")

    console.print("\n[bold]📊 生涯统计[/bold]")
    total = state.stats.get("total", 0)
    if total <= 0:
        console.print("  [dim]还没有抽卡记录，运行 mcd-gacha pull 开始吧。[/dim]\n")
    else:
        ssr = state.stats.get("SSR", 0)
        rate = state.golden_rate() * 100
        console.print(
            f"  累计 {total} 抽 | 出金 {ssr} 次（{rate:.1f}%）"
            f" | 今日已抽 {state.daily_count} 发"
        )
        parts = [
            f"{name} {state.stats.get(name, 0)}"
            for name in ("SSR", "SR", "R", "N")
        ]
        console.print(f"  分布：{' | '.join(parts)}")
        recent = state.history[-5:]
        if recent:
            console.print("  最近记录：")
            for item in reversed(recent):
                style = RARITY_RICH_STYLE.get(item.get("rarity", "N"), "dim")
                ts = str(item.get("ts", ""))[:16].replace("T", " ")
                console.print(
                    f"    [dim]{ts}[/dim] {item.get('banner', '')} "
                    f"[{style}]{item.get('rarity', '')}[/{style}] "
                    f"实付 ¥{format_price(int(item.get('paid', 0)))}"
                )
        console.print()

    console.print(f"  [dim]状态文件：{get_state_file()}[/dim]\n")


@app.command()
def simulate(
    times: int = typer.Option(100_000, "--times", "-n", help="模拟次数"),
    seed: int | None = typer.Option(None, "--seed", help="随机种子（结果可复现）"),
) -> None:
    """概率自证：蒙特卡洛模拟四档出率与 10 发硬保底。"""
    if times <= 0:
        raise typer.BadParameter("--times 必须大于 0")

    engine = McdGacha(MockDataSource())
    stats = engine.simulate(times, seed=seed)
    weights = engine.config.rarity_weights

    table = Table(
        title=f"🎲 蒙特卡洛模拟（{times:,} 次{' seed=' + str(seed) if seed is not None else ''}）",
        title_style="bold",
        border_style="dim",
    )
    table.add_column("稀有度", width=6)
    table.add_column("基础概率", justify="right")
    table.add_column("实测频率", justify="right")
    table.add_column("次数", justify="right")

    for name in ("SSR", "SR", "R", "N"):
        style = RARITY_RICH_STYLE[Rarity(name)]
        table.add_row(
            f"[{style}]{name}[/{style}]",
            f"{weights.get(name, 0)}%",
            f"{stats['rates'][name] * 100:.2f}%",
            f"{stats['counts'][name]:,}",
        )

    console.print()
    console.print(table)
    console.print(
        f"\n  ⛳ SSR 平均间隔 [bold]{stats['ssr_avg_gap']:.2f}[/bold] 抽；"
        f"最大间隔 {stats['ssr_max_gap']} 抽；保底触发 {stats['pity_triggers']:,} 次"
    )
    console.print(
        f"  [dim]基础概率 {weights.get('SSR', 5)}% 叠加 {stats['hard_pity']} 发硬保底后，"
        f"SSR 有效出率 ≈ {stats['rates']['SSR'] * 100:.1f}%"
        f"（平均约 {stats['ssr_avg_gap']:.1f} 抽一金）。[/dim]\n"
    )


@app.command()
def stores(
    city: str | None = typer.Option(None, "--city", help="城市名（如：深圳市）"),
) -> None:
    """查询附近门店（真实 MCP），用于选择 storeCode 固定点餐门店。"""
    asyncio.run(_stores_impl(city))


async def _stores_impl(city: str | None) -> None:
    token = get_token()
    if token is None:
        console.print(
            "[red]❌ 未找到 MCP Token（设置环境变量 MCD_MCP_TOKEN "
            "或运行 mcd-gacha config set-token）[/red]"
        )
        raise typer.Exit(code=1)

    _, configured_city = get_store_settings()
    use_city = city or configured_city
    if not use_city:
        console.print("[red]❌ 请提供城市名：mcd-gacha stores --city 深圳市[/red]")
        raise typer.Exit(code=1)

    try:
        from .datasource.mcp import McpDataSource

        source = McpDataSource(token=token, city=use_city)
        await source.start()
        try:
            store_list = await source.nearby_stores()
        finally:
            await source.close()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]❌ 门店查询失败：{exc}[/red]")
        raise typer.Exit(code=1) from exc

    table = Table(title=f"🏪 {use_city} 附近门店（到店自取）", title_style="bold", border_style="dim")
    table.add_column("门店编号", style="cyan")
    table.add_column("门店名称")
    table.add_column("地址", style="dim", max_width=40)
    for store in store_list[:10]:
        table.add_row(store.code, store.name, store.address)
    console.print()
    console.print(table)
    console.print(
        "\n  [dim]提示：mcd-gacha config set-store --store-code <编号> 可固定门店；"
        "或 --city 保存城市后自动选择最近门店[/dim]\n"
    )


@app.command()
def doctor(
    as_json: bool = typer.Option(
        False, "--json", help="以 JSON 格式输出（供 AI / 脚本判定是否已接入 MCP）"
    ),
) -> None:
    """环境自检：Token 来源、门店设置、MCP 连通性（排障第一步）。"""
    asyncio.run(_doctor_impl(as_json))


async def _collect_doctor_report() -> dict:
    """收集环境自检的结构化结果（文本渲染与 --json 共用）。"""
    token, source = get_token_with_source()
    store_code, city = get_store_settings()
    report: dict = {
        "token_found": bool(token),
        "token_source": source,
        "token_masked": mask_token(token) if token else None,
        "store_code": store_code or None,
        "city": city or None,
        "config_file": str(get_config_file()),
        "state_file": str(get_state_file()),
        "mcp_connected": False,
        "mcp_tools": None,
        "meal_count": None,
        "store_label": None,
        "mcp_error": None,
        "mode": "mock",
    }
    if not token:
        return report

    mcp_source = None
    try:
        from .datasource.mcp import McpDataSource

        mcp_source = McpDataSource(token=token, store_code=store_code, city=city)
        await mcp_source.start()
        report["meal_count"] = len(await mcp_source.query_meals())
        report["mcp_tools"] = await mcp_source.tool_count()
        store_obj = getattr(mcp_source, "_store", None)
        report["store_label"] = (store_obj.name if store_obj else "") or (store_code or "") or None
        report["mcp_connected"] = True
        report["mode"] = "mcp"
    except Exception as exc:  # noqa: BLE001 —— 网络/鉴权/依赖缺失统一记为未连接
        report["mcp_error"] = str(exc)
    finally:
        # 无论成功失败都必须关闭连接：否则 MCP 的 async generator 会残留在
        # AsyncExitStack 里，被 GC 时在 event loop 关闭阶段抛
        # "Attempted to exit cancel scope in a different task"，污染 --json 输出。
        if mcp_source is not None:
            with contextlib.suppress(Exception):
                await mcp_source.close()
    return report


async def _doctor_impl(as_json: bool = False) -> None:
    report = await _collect_doctor_report()

    if as_json:
        typer.echo(jsonlib.dumps(report, ensure_ascii=False, indent=2))
        return

    console.print("\n[bold]🩺 Mcd-Gacha 环境自检[/bold]\n")

    # 1) Token 与来源
    if report["token_found"]:
        console.print(f"  🔑 MCP Token：{report['token_masked']}")
        console.print(f"     来源：{report['token_source']}")
    else:
        console.print("  🔑 MCP Token：[yellow]未找到[/yellow]（演示模式仍可完整使用）")
        console.print(
            "     配置方式：环境变量 MCD_MCP_TOKEN / 项目根 .env / "
            "[cyan]mcd-gacha config set-token <TOKEN>[/cyan]"
        )

    # 2) 门店设置
    if report["store_code"] or report["city"]:
        console.print(
            f"  🏪 门店设置：store_code={report['store_code'] or '（未配置）'}，"
            f"city={report['city'] or '（未配置）'}"
        )
    else:
        console.print(
            "  🏪 门店设置：[yellow]未配置[/yellow]（真实模式需要："
            "[cyan]mcd-gacha config set-store --city <城市名>[/cyan]）"
        )

    # 3) 路径
    console.print(f"  📄 配置文件：{report['config_file']}")
    console.print(f"  🎯 状态文件：{report['state_file']}")

    # 4) 连通性检测
    if report["token_found"]:
        if report["mcp_connected"]:
            console.print(
                f"  🛰 麦当劳 MCP：[green]✅ 已连接[/green]（{report['mcp_tools']} 个工具）"
            )
            console.print(
                f"     门店：{report['store_label'] or '（未指定）'} | "
                f"在售餐品：{report['meal_count']} 个"
            )
        else:
            console.print(f"  🛰 麦当劳 MCP：[yellow]⚠️ 连接失败（{report['mcp_error']}）[/yellow]")
            console.print(
                "     [dim]提示：若为网络代理问题，可尝试设置 NO_PROXY=mcp.mcd.cn；"
                "未配置门店请先运行 config set-store[/dim]"
            )
    else:
        console.print("\n  📦 当前模式：内置演示数据（mock）——无需任何配置即可完整体验")

    console.print("\n  [dim]自检完成。开抽：mcd-gacha pull / 卡池一览：mcd-gacha banners[/dim]\n")


@config_app.command("set-token")
def config_set_token(token: str = typer.Argument(..., help="麦当劳 MCP Token")) -> None:
    """保存 MCP Token 到本地配置（不会进入版本库）。"""
    path = save_token(token)
    console.print(f"✅ Token 已保存：{mask_token(token)}")
    console.print(f"   配置文件：{path}")


@config_app.command("set-store")
def config_set_store(
    store_code: str | None = typer.Option(None, "--store-code", help="门店编号（数字）"),
    city: str | None = typer.Option(None, "--city", help="城市名（如：深圳市）"),
) -> None:
    """保存门店设置（真实模式使用；编号可用 mcd-gacha stores 查询）。"""
    if not store_code and not city:
        console.print("[red]❌ 至少提供 --store-code 或 --city 之一[/red]")
        raise typer.Exit(code=1)
    path = save_store_settings(store_code, city)
    console.print(
        f"✅ 门店设置已保存：store_code={store_code or '（未变）'}，city={city or '（未变）'}"
    )
    console.print(f"   配置文件：{path}")


@config_app.command("show")
def config_show() -> None:
    """查看本地配置状态（Token 脱敏展示）。"""
    store_code, city = get_store_settings()
    console.print(f"\n🔑 MCP Token：{mask_token(get_token())}")
    console.print(f"🏪 门店设置：store_code={store_code or '（未配置）'}，city={city or '（未配置）'}")
    console.print(f"   配置文件：{get_config_file()}")
    console.print(f"   状态文件：{get_state_file()}\n")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"mcd-gacha v{__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="显示版本号",
    ),
) -> None:
    """麦门抽卡模拟器（非官方第三方开源玩具）。"""


def main() -> None:
    """命令行入口（pyproject [project.scripts] 指向本函数）。"""
    app()


if __name__ == "__main__":
    main()
