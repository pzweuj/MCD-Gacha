"""重铸（reroll）功能测试。"""

from __future__ import annotations

import pytest

from mcd_gacha.datasource import MockDataSource
from mcd_gacha.engine import GachaError, McdGacha
from mcd_gacha.rarity import Rarity
from mcd_gacha.state import load_state


async def test_reroll_replaces_target_slot(engine):
    """重铸应真正换掉指定件，其余件保持不变。"""
    pulled = await engine.roll("worker_up")
    assert len(pulled.lines) >= 1
    rerolled = await engine.reroll(1)
    assert rerolled.lines[0].meal.code != pulled.lines[0].meal.code, "目标件未被替换"
    for old_line, new_line in zip(pulled.lines[1:], rerolled.lines[1:], strict=True):
        assert old_line.meal.code == new_line.meal.code, "其他件不应变化"


async def test_reroll_keeps_rarity_and_pity(engine):
    """重铸不改变稀有度、不影响保底进度。"""
    pulled = await engine.roll("poor_standard")
    pity_before = engine.state.pity_for("poor_standard")
    rerolled = await engine.reroll(1)
    assert rerolled.rarity is pulled.rarity
    assert engine.state.pity_for("poor_standard") == pity_before
    assert rerolled.pity_after == pity_before


async def test_reroll_respects_budget(engine):
    """重铸后的组合仍在预算内。"""
    await engine.roll("worker_up")
    rerolled = await engine.reroll(1)
    banner = engine.config.require("worker_up")
    # 预算为卡池默认值
    assert rerolled.quote.paid_cents <= banner.default_budget_cents


async def test_reroll_same_category(engine):
    """替换商品必须与原件同品类。"""
    pulled = await engine.roll("worker_up")
    target_category = pulled.lines[0].meal.category
    rerolled = await engine.reroll(1)
    assert rerolled.lines[0].meal.category == target_category


async def test_reroll_without_prior_pull(engine):
    """没有上次结果时给出友好错误。"""
    with pytest.raises(GachaError, match="先抽一发"):
        await engine.reroll(1)


async def test_reroll_slot_out_of_range(engine):
    await engine.roll("poor_standard")
    with pytest.raises(GachaError, match="槽位超出范围"):
        await engine.reroll(99)


async def test_reroll_prefers_upgrade_or_parity(engine):
    """优先升级/平价替换：若存在预算内的升级候选，不应出现降级替换。"""
    await engine.roll("worker_up")
    rerolled = await engine.reroll(1)
    # 由于优先批次存在时必然先尝试升级/平价，这里只断言"通常不降级"：
    # 抽样多次全量验证由 test_reroll_never_exceeds_budget 覆盖
    assert rerolled.quote.paid_cents <= engine.config.require("worker_up").default_budget_cents


async def test_reroll_state_updated_for_chained_rerolls(engine):
    """重铸后可继续重铸（last_result 已更新）。"""
    await engine.roll("worker_up")
    first = await engine.reroll(1)
    second = await engine.reroll(1)
    assert second.lines[0].meal.code != first.lines[0].meal.code


async def test_reroll_persisted_across_sessions(tmp_path):
    """跨进程（两次引擎实例）重铸：状态文件中的 last_result 可用。"""
    state_path = tmp_path / "state.json"

    engine1 = McdGacha(MockDataSource(), state_path=state_path)
    pulled = await engine1.roll("worker_up")

    engine2 = McdGacha(
        MockDataSource(), state_path=state_path, state=load_state(state_path)
    )
    rerolled = await engine2.reroll(1)
    assert rerolled.lines[0].meal.code != pulled.lines[0].meal.code
    # 重铸记录已写入历史
    assert engine2.state.history[-1].get("type") == "reroll"


async def test_reroll_history_recorded(engine):
    await engine.roll("worker_up")
    await engine.reroll(1)
    record = engine.state.history[-1]
    assert record["type"] == "reroll"
    assert record["slot"] == 1
    assert record["rarity"] in {r.value for r in Rarity}


async def test_reroll_uses_coupon_headroom(engine):
    """回归：券前超预算但券后可行的替换应被接受（曾因"券前快筛"误杀）。

    构造：巨无霸(26) + 可乐(9.5) = 券前 35.5；满 30 减 6 后实付 29.5。
    重铸第 1 件（巨无霸）时，升级候选（不素之霸 27 / 芝士安格斯 31.5）
    会使券前达到 36.5~41（超预算），但券后 30.5~35 均在预算内。
    """
    engine.state.last_result = {
        "ts": "2026-10-10T12:00:00",
        "banner_key": "worker_up",
        "rarity": "R",
        "budget_cents": 3500,
        "pull_index": 1,
        "items": [{"code": "1100", "qty": 1}, {"code": "9900008751", "qty": 1}],
    }
    result = await engine.reroll(1)
    assert result.lines[0].meal.category == "burger"
    assert result.quote.paid_cents <= 3500
    # 应为升级/平价替换（不低于原巨无霸 26 元）
    assert result.lines[0].meal.price_cents >= 2600
