"""真实数据源回退测试：门店打烊等「连得上但查不到菜单」的情况必须回退演示数据。

回归背景（2026-10-10 实测）：门店打烊时 `query-meals` 返回业务错误
（code=600057 门店可能已关闭或不在营业时间）。此前 `_open_source` 只兜住了
`start()` 阶段的异常，运行期错误会一路抛到引擎并中断抽卡——与文档承诺的
「任何真实接口异常都会自动回退演示数据并提示」不符。
"""

from __future__ import annotations

import pytest

from mcd_gacha.cli import _open_source
from mcd_gacha.datasource.mcp import McpQueryError
from mcd_gacha.datasource.mock import MockDataSource


@pytest.fixture
def real_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCD_GACHA_HOME", str(tmp_path))
    monkeypatch.setenv("MCD_MCP_TOKEN", "test-token")
    monkeypatch.setenv("MCD_STORE_CODE", "1421182")
    return tmp_path


async def test_falls_back_when_store_closed(real_env, monkeypatch):
    """start() 成功但 query-meals 抛业务错误（门店打烊）→ 回退演示数据。"""

    closed = False

    class _ClosedStoreSource:
        mode = "mcp"

        def __init__(self, token, store_code=None, city=None, url=None):
            self._store = None

        async def start(self) -> None:
            return None

        async def query_meals(self, store_code=None):
            raise McpQueryError("query-meals 返回错误：门店可能已关闭或不在营业时间（code=600057）")

        async def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr("mcd_gacha.datasource.mcp.McpDataSource", _ClosedStoreSource)

    source, note = await _open_source(use_real=True, use_mock=False)

    assert isinstance(source, MockDataSource), "门店打烊应回退演示数据而不是抛错中断"
    assert "回退" in note
    assert closed, "回退时应关闭已建立的会话，避免连接泄漏"


async def test_uses_real_source_when_healthy(real_env, monkeypatch):
    """门店正常（start + query_meals 均成功）→ 保留真实数据源。"""

    class _HealthySource:
        mode = "mcp"

        def __init__(self, token, store_code=None, city=None, url=None):
            self._store = type("S", (), {"name": "测试门店"})()

        async def start(self) -> None:
            return None

        async def query_meals(self, store_code=None):
            return []

        async def close(self) -> None:
            return None

    monkeypatch.setattr("mcd_gacha.datasource.mcp.McpDataSource", _HealthySource)

    source, note = await _open_source(use_real=True, use_mock=False)

    assert not isinstance(source, MockDataSource)
    assert "已连接" in note
