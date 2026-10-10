"""蒙特卡洛统计测试：验证概率引擎的长期行为。"""

from __future__ import annotations

SIM_TIMES = 50_000


def test_simulate_rates_in_expected_range(engine):
    """基础概率 + 硬保底后的长期出率落在合理区间。"""
    stats = engine.simulate(SIM_TIMES, seed=123)
    rates = stats["rates"]
    # SSR 有效出率约 12.5%（基础 5% + 10 发硬保底的拉升）
    assert 0.115 <= rates["SSR"] <= 0.135, f"SSR 出率异常：{rates['SSR']}"
    # SR/R/N 因保底截断略低于基础值（25/60/10）
    assert 0.21 <= rates["SR"] <= 0.25
    assert 0.52 <= rates["R"] <= 0.58
    assert 0.08 <= rates["N"] <= 0.10


def test_simulate_pity_boundary(engine):
    """保底保证：任意两次 SSR 间隔不超过 hard_pity。"""
    stats = engine.simulate(SIM_TIMES, seed=456)
    assert stats["ssr_max_gap"] <= stats["hard_pity"] <= 10
    assert stats["ssr_avg_gap"] < 9


def test_simulate_reproducible_with_seed(engine):
    """相同种子结果完全一致（可复现）。"""
    first = engine.simulate(2_000, seed=42)
    second = engine.simulate(2_000, seed=42)
    assert first["counts"] == second["counts"]


def test_simulate_does_not_touch_state(engine):
    """simulate 是纯概率模拟，不应污染持久化状态。"""
    before = dict(engine.state.stats)
    engine.simulate(1_000, seed=1)
    assert engine.state.stats == before
