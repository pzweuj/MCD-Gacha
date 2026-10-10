"""共享测试夹具。"""

from __future__ import annotations

import random

import pytest

from mcd_gacha.banners import load_banner_config
from mcd_gacha.datasource import MockDataSource
from mcd_gacha.engine import McdGacha


@pytest.fixture
def source() -> MockDataSource:
    return MockDataSource()


@pytest.fixture
def meals(source):
    return source.meals


@pytest.fixture
def coupons(source):
    return source.coupons


@pytest.fixture
def config():
    return load_banner_config()


@pytest.fixture
def rng() -> random.Random:
    return random.Random(42)


@pytest.fixture
def engine(tmp_path):
    """隔离状态文件的引擎（不触碰用户本地配置）。"""
    return McdGacha(
        MockDataSource(),
        config=load_banner_config(),
        rng=random.Random(7),
        state_path=tmp_path / "state.json",
    )
