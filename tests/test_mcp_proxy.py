"""真实 MCP 数据源：代理绕过逻辑的单测。

对应 `mcd_gacha.datasource.mcp._bypass_proxy_for`：
当运行环境设置了 HTTP(S)_PROXY 时，需要把 MCP 主机追加进 NO_PROXY，
否则 httpx 会走系统代理导致真实链路失败并回退 mock。
"""

from __future__ import annotations

import os

from mcd_gacha.datasource.mcp import MCP_URL, _bypass_proxy_for


def _clear_proxy_env(monkeypatch) -> None:
    for key in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(key, raising=False)


def test_adds_host_when_no_proxy_empty(monkeypatch):
    _clear_proxy_env(monkeypatch)

    _bypass_proxy_for(MCP_URL)

    assert "mcp.mcd.cn" in os.environ["NO_PROXY"].split(",")
    # 大小写两种变量名都应写入，兼容不同库的读取习惯
    assert os.environ["no_proxy"] == os.environ["NO_PROXY"]


def test_preserves_existing_entries(monkeypatch):
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")

    _bypass_proxy_for(MCP_URL)

    entries = os.environ["NO_PROXY"].split(",")
    assert entries[:2] == ["localhost", "127.0.0.1"]
    assert "mcp.mcd.cn" in entries


def test_idempotent(monkeypatch):
    _clear_proxy_env(monkeypatch)

    _bypass_proxy_for(MCP_URL)
    first = os.environ["NO_PROXY"]
    _bypass_proxy_for(MCP_URL)
    second = os.environ["NO_PROXY"]

    assert first == second
    assert second.split(",").count("mcp.mcd.cn") == 1


def test_merges_case_variants_without_duplication(monkeypatch):
    _clear_proxy_env(monkeypatch)
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    _bypass_proxy_for(MCP_URL)

    entries = os.environ["NO_PROXY"].split(",")
    assert entries.count("127.0.0.1") == 1
    assert "mcp.mcd.cn" in entries


def test_ignores_invalid_url(monkeypatch):
    _clear_proxy_env(monkeypatch)

    _bypass_proxy_for("not-a-url")

    assert "NO_PROXY" not in os.environ
