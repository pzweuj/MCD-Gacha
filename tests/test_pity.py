"""保底机制不变量测试。"""

from __future__ import annotations

import random

from mcd_gacha.rarity import Rarity


async def test_hard_pity_forces_ssr(engine):
    """第 10 发（连续 9 发未出金）必出 SSR。"""
    key = "poor_standard"
    engine.state.pity[key] = 9
    result = await engine.roll(key)
    assert result.rarity is Rarity.SSR
    assert result.pity_after == 0


async def test_ssr_resets_pity(engine):
    """出 SSR 后保底计数清零。"""
    key = "poor_standard"
    engine.rng = random.Random(0)
    # 抽到出金为止
    for _ in range(20):
        result = await engine.roll(key)
        if result.rarity is Rarity.SSR:
            assert result.pity_after == 0
            break
    else:
        raise AssertionError("20 发内未出金（保底失效）")


async def test_pity_increments_on_non_ssr(engine):
    """非 SSR 时保底计数 +1。"""
    key = "poor_standard"
    engine.rng = random.Random(1)
    before = engine.state.pity_for(key)
    result = await engine.roll(key)
    if result.rarity is Rarity.SSR:
        assert result.pity_after == 0
    else:
        assert result.pity_after == before + 1


async def test_any_ten_consecutive_pulls_contain_ssr(engine):
    """任意连续 10 抽内必有 SSR（硬保底的全局不变量）。"""
    key = "worker_up"
    engine.rng = random.Random(99)
    rarities = []
    for _ in range(80):
        result = await engine.roll(key)
        rarities.append(result.rarity)
    for start in range(0, len(rarities) - 9):
        window = rarities[start : start + 10]
        assert Rarity.SSR in window, f"窗口 [{start}, {start + 9}] 内无 SSR"


async def test_ten_pull_shares_pity_counter(engine):
    """十连共享保底：前 9 发无金时，第 10 发必金。"""
    key = "poor_standard"
    engine.state.pity[key] = 9  # 下一发（十连第 1 发）即触发保底
    results = await engine.ten_pull(key)
    assert len(results) == 10
    assert results[0].rarity is Rarity.SSR


async def test_pity_independent_per_banner(engine):
    """不同卡池的保底计数互相独立。"""
    engine.state.pity["poor_standard"] = 5
    result = await engine.roll("worker_up")
    assert result.pity_after in (0, 1)  # worker 池从 0 起步
    assert engine.state.pity_for("poor_standard") == 5  # 不受影响
