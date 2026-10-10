"""doctor --json 测试：AI 首次抽卡前的强制自检依赖该输出判定 MCP 是否接入。

行为契约（见 SKILL.md「STEP 0」）：
- 未配置 Token → `token_found=false` / `mcp_connected=false` / `mode="mock"`；
- 已配置且连通 → `mcp_connected=true` / `mode="mcp"`，且 Token 必须脱敏。
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from mcd_gacha.cli import app

runner = CliRunner()


def _isolate(tmp_path, monkeypatch) -> None:
    """隔离本地配置与工作目录，避免读到真实 Token / .env。"""
    monkeypatch.setenv("MCD_GACHA_HOME", str(tmp_path))
    monkeypatch.delenv("MCD_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MCD_STORE_CODE", raising=False)
    monkeypatch.delenv("MCD_CITY", raising=False)
    monkeypatch.chdir(tmp_path)


def test_doctor_json_without_token(tmp_path, monkeypatch):
    """无 Token：判定为未接入，模式 mock。"""
    _isolate(tmp_path, monkeypatch)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["token_found"] is False
    assert data["mcp_connected"] is False
    assert data["mode"] == "mock"
    assert data["token_masked"] is None


def test_doctor_json_connected(tmp_path, monkeypatch):
    """已配置且连通：判定为已接入，模式 mcp，Token 脱敏。"""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("MCD_MCP_TOKEN", "test-token-abcd")
    monkeypatch.setenv("MCD_STORE_CODE", "1421182")

    class _FakeSource:
        def __init__(self, token, store_code=None, city=None, url=None):
            self._store = None

        async def start(self) -> None:
            return None

        async def query_meals(self, store_code=None):
            return [1, 2, 3]

        async def tool_count(self) -> int:
            return 28

        async def close(self) -> None:
            return None

    monkeypatch.setattr("mcd_gacha.datasource.mcp.McpDataSource", _FakeSource)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["token_found"] is True
    assert data["mcp_connected"] is True
    assert data["mode"] == "mcp"
    assert data["meal_count"] == 3
    assert data["mcp_tools"] == 28
    assert "test-token-abcd" not in result.stdout  # Token 必须脱敏


def test_doctor_json_connection_failed(tmp_path, monkeypatch):
    """有 Token 但连通失败：token_found=true 而 mcp_connected=false，附错误。"""
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("MCD_MCP_TOKEN", "test-token-abcd")

    class _BrokenSource:
        def __init__(self, token, store_code=None, city=None, url=None):
            self._store = None

        async def start(self) -> None:
            raise RuntimeError("network unreachable")

    monkeypatch.setattr("mcd_gacha.datasource.mcp.McpDataSource", _BrokenSource)

    result = runner.invoke(app, ["doctor", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["token_found"] is True
    assert data["mcp_connected"] is False
    assert data["mode"] == "mock"
    assert "network unreachable" in (data["mcp_error"] or "")
