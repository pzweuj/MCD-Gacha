"""引擎流程测试：抽卡、时段校验、状态持久化。"""

from __future__ import annotations

from datetime import datetime

import pytest

from mcd_gacha.datasource import MockDataSource
from mcd_gacha.engine import GachaError, McdGacha
from mcd_gacha.rarity import Rarity
from mcd_gacha.state import load_state


async def test_roll_returns_result(engine):
    result = await engine.roll("poor_standard")
    assert result.rarity in tuple(Rarity)
    assert result.lines
    banner = engine.config.require("poor_standard")
    assert result.quote.paid_cents <= banner.default_budget_cents
    assert result.data_source == "mock"
    assert result.ts is not None


async def test_roll_with_custom_budget(engine):
    result = await engine.roll("worker_up", budget_yuan=30)
    assert result.quote.paid_cents <= 3000


async def test_budget_floor_clamped_to_banner_min(engine):
    """预算低于卡池下限时抬到下限（保证能生成合理组合）。"""
    result = await engine.roll("worker_up", budget_yuan=1)
    assert result.quote.paid_cents <= 4000


async def test_midnight_closed_during_day(engine):
    daytime = datetime(2026, 10, 10, 15, 0)
    with pytest.raises(GachaError, match="未开放"):
        await engine.roll("midnight", now=daytime)


@pytest.mark.parametrize("hour", [21, 23, 0, 3])
async def test_midnight_open_at_night(engine, hour):
    night = datetime(2026, 10, 10, hour, 30)
    result = await engine.roll("midnight", now=night)
    assert result.rarity in tuple(Rarity)
    assert result.quote.paid_cents <= engine.config.require("midnight").default_budget_cents


async def test_ten_pull_returns_ten(engine):
    results = await engine.ten_pull("poor_standard")
    assert [r.pull_index for r in results] == list(range(1, 11))


async def test_state_persisted_between_sessions(tmp_path):
    """两个引擎实例（模拟两次 CLI 调用）应共享同一状态文件。"""
    state_path = tmp_path / "state.json"

    engine1 = McdGacha(MockDataSource(), state_path=state_path)
    await engine1.roll("poor_standard")

    engine2 = McdGacha(MockDataSource(), state_path=state_path, state=load_state(state_path))
    await engine2.roll("poor_standard")

    state = load_state(state_path)
    assert state.stats.get("total") == 2


async def test_history_recorded(engine):
    await engine.roll("poor_standard")
    assert len(engine.state.history) == 1
    record = engine.state.history[0]
    assert record["banner"] == "poor_standard"
    assert "rarity" in record
    assert record["items"]


async def test_json_serializable(engine):
    result = await engine.roll("poor_standard")
    payload = result.to_dict()
    import json

    dumped = json.dumps(payload, ensure_ascii=False)
    assert '"rarity"' in dumped
