"""分享卡渲染测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from mcd_gacha.models import LineItem, Meal, PriceQuote, PullResult
from mcd_gacha.rarity import Rarity
from mcd_gacha.share_card import render_card, save_card


def _result(rarity: Rarity = Rarity.SSR, discount: int = 800) -> PullResult:
    lines = [
        LineItem(Meal("A1", "巨无霸", "burger", 2600, ("staple", "premium"), 550), 1),
        LineItem(Meal("B1", "可乐", "drink", 950, ("drink",), 150), 1),
    ]
    quote = PriceQuote(
        original_cents=3550,
        discount_cents=discount,
        paid_cents=3550 - discount,
        coupon_id="C1" if discount else None,
        coupon_name="满 30 减 8" if discount else None,
        source="mock",
    )
    return PullResult(
        rarity=rarity,
        banner_key="worker_up",
        banner_name="打工人回血 · 限定 UP 池",
        lines=lines,
        quote=quote,
        flavor="测试文案：欧皇时刻。",
        ts=datetime(2026, 10, 10, 12, 0),
        pity_after=1,
        pull_index=1,
        data_source="mock",
    )


def test_render_contains_key_elements():
    svg = render_card(_result())
    assert svg.startswith("<svg")
    for token in ("SSR", "巨无霸", "可乐", "¥26", "满 30 减 8", "省 ¥8", "非官方开源玩具"):
        assert token in svg, f"缺少关键元素: {token}"


def test_render_no_discount_branch():
    svg = render_card(_result(discount=0))
    assert "实付" in svg
    assert "省 ¥" not in svg


@pytest.mark.parametrize("rarity", list(Rarity))
def test_render_all_rarities(rarity):
    svg = render_card(_result(rarity=rarity))
    assert rarity.value in svg
    assert "<svg" in svg


def test_render_night_banner_and_mcp_source():
    result = _result(rarity=Rarity.N, discount=0)
    result.data_source = "mcp"
    svg = render_card(result)
    assert "真实核价" in svg


def test_xml_wellformed():
    import xml.dom.minidom as minidom

    doc = minidom.parseString(render_card(_result()))
    assert doc.documentElement.tagName == "svg"


def test_save_card(tmp_path):
    path = save_card(_result(), tmp_path / "my-card")
    assert path.exists()
    assert path.suffix == ".svg"
    assert "<svg" in path.read_text(encoding="utf-8")
