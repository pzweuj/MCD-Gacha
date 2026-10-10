"""下单（order）功能测试：安全闸门、参数构造与错误处理（全程不触网）。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from mcd_gacha.cli import app
from mcd_gacha.datasource.base import OrderNotSupportedError
from mcd_gacha.datasource.mcp import (
    McpDataSource,
    _normalize_take_ways,
    _parse_order,
    _pick_take_way,
)
from mcd_gacha.models import LineItem, Meal, OrderResult, PriceQuote, Store, TakeWay

runner = CliRunner()

TEST_MEALS = [
    Meal(code="M1", name="测试巨无霸", category="burger", price_cents=2600),
    Meal(code="M2", name="测试可乐", category="drink", price_cents=950),
]


# ---------------------------------------------------------------------------
# 纯函数：takeWayCode 挑选与下单返回解析
# ---------------------------------------------------------------------------


def test_pick_take_way_prefers_default():
    assert _pick_take_way([{"code": "A"}, {"code": "B", "isDefault": True}]) == "B"


def test_pick_take_way_falls_back_to_first():
    assert _pick_take_way([{"code": "A"}, {"code": "B"}]) == "A"


def test_pick_take_way_empty():
    assert _pick_take_way([]) is None
    assert _pick_take_way([{"name": "无 code"}]) is None


def test_normalize_take_ways_maps_title_and_default():
    """takeWayList 的 title/name 键名差异要归一，并标出默认项。"""
    options = _normalize_take_ways(
        [
            {"code": "eat-in", "title": "堂食"},
            {"code": "locker-in", "name": "取餐柜", "isDefault": True},
            {"no_code": True},  # 无 code 应丢弃
        ]
    )
    assert [o.code for o in options] == ["eat-in", "locker-in"]
    assert options[0].title == "堂食"
    assert options[1].title == "取餐柜"
    assert options[1].is_default is True
    assert options[1].to_dict() == {
        "code": "locker-in",
        "title": "取餐柜",
        "is_default": True,
    }


async def test_mcp_exposes_take_way_options_after_pricing(monkeypatch):
    """核价后应能通过 take_way_options / default_take_way 拿到候选供用户确认。"""
    src = McpDataSource(token="t", store_code="1421182")

    async def fake_call(tool: str, args: dict) -> dict:
        if tool == "query-store-coupons":
            return {"success": True, "data": []}
        return {
            "success": True,
            "data": {
                "originalPrice": 2600,
                "price": 2600,
                "takeWayList": [
                    {"code": "eat-in", "title": "堂食", "isDefault": True},
                    {"code": "locker-in", "title": "取餐柜"},
                ],
            },
        }

    monkeypatch.setattr(src, "_call", fake_call)
    assert src.take_way_options == []  # 核价前为空
    await src.calculate_price([LineItem(meal=TEST_MEALS[0], qty=1)])
    assert [o.code for o in src.take_way_options] == ["eat-in", "locker-in"]
    assert src.default_take_way == "eat-in"


def test_parse_order_extracts_common_fields():
    payload = {
        "success": True,
        "data": {"orderId": "12345", "payUrl": "https://pay.example/x", "price": 2950},
    }
    result = _parse_order(payload, payload["data"])
    assert result.order_id == "12345"
    assert result.pay_url == "https://pay.example/x"
    assert result.paid_cents == 2950


def test_parse_order_tolerates_unknown_shape():
    """返回结构未知时不应崩溃，原始 payload 完整保留。"""
    payload = {"success": True, "data": {"orderNo": "A1", "totalPrice": "32.5"}}
    result = _parse_order(payload, payload["data"])
    assert result.order_id == "A1"
    assert result.paid_cents == 3250  # "32.5" 视为元
    assert result.raw == payload


# ---------------------------------------------------------------------------
# 数据源层
# ---------------------------------------------------------------------------


async def test_mock_source_refuses_order(source):
    """内置演示数据必须显式拒绝下单，而不是伪造订单。"""
    line = LineItem(meal=source.meals[0], qty=1)
    with pytest.raises(OrderNotSupportedError, match="不支持"):
        await source.create_order([line])


async def test_mcp_create_order_builds_required_args(monkeypatch):
    """到店下单必须带 storeCode / orderType / beType / takeWayCode（来自核价）。"""
    src = McpDataSource(token="t", store_code="1421182")
    calls: list[tuple[str, dict]] = []

    async def fake_call(tool: str, args: dict) -> dict:
        calls.append((tool, args))
        if tool == "query-store-coupons":
            return {"success": True, "data": []}
        if tool == "calculate-price":
            return {
                "success": True,
                "data": {
                    "originalPrice": 3550,
                    "price": 2950,
                    "discount": 600,
                    "takeWayList": [{"code": "TW1", "name": "到店自取", "isDefault": True}],
                },
            }
        return {"success": True, "data": {"orderId": "O1", "payUrl": "https://p"}}

    monkeypatch.setattr(src, "_call", fake_call)
    lines = [LineItem(meal=TEST_MEALS[0], qty=1)]

    result = await src.create_order(lines)

    assert result.order_id == "O1"
    order_args = next(args for tool, args in calls if tool == "create-order")
    assert order_args["storeCode"] == "1421182"
    assert order_args["orderType"] == 1
    assert order_args["beType"] == 1
    assert order_args["takeWayCode"] == "TW1"
    assert order_args["items"] == [{"productCode": "M1", "quantity": 1}]


async def test_mcp_create_order_requires_take_way(monkeypatch):
    """核价未提供 takeWayList 时，到店下单应给出明确错误而不是静默失败。"""
    src = McpDataSource(token="t", store_code="1421182")

    async def fake_call(tool: str, args: dict) -> dict:
        if tool == "query-store-coupons":
            return {"success": True, "data": []}
        if tool == "calculate-price":
            return {"success": True, "data": {"originalPrice": 2600, "price": 2600}}
        return {"success": True, "data": {}}

    monkeypatch.setattr(src, "_call", fake_call)
    with pytest.raises(Exception, match="takeWayCode"):
        await src.create_order([LineItem(meal=TEST_MEALS[0], qty=1)])


async def test_engine_records_data_source(engine):
    """last_result 需记录数据来源，供下单命令判定是否为真实 SKU。"""
    await engine.roll("worker_up")
    assert engine.state.last_result["data_source"] == "mock"
    assert engine.state.last_result["items"]


# ---------------------------------------------------------------------------
# CLI 层：安全闸门（用桩数据源，不触网）
# ---------------------------------------------------------------------------


class _StubMcpSource:
    """替身：模拟真实 MCP 数据源，记录 create_order 是否被调用。"""

    mode = "mcp"
    instances: list[_StubMcpSource] = []

    def __init__(self, token, store_code=None, city=None, url=None):
        self.token = token
        self.store_code = store_code
        self.city = city
        self._store = SimpleNamespace(name="测试门店", code=store_code or "")
        self.order_kwargs: dict | None = None
        _StubMcpSource.instances.append(self)

    async def start(self) -> None:
        return None

    async def query_meals(self, store_code=None):
        return list(TEST_MEALS)

    async def calculate_price(self, lines) -> PriceQuote:
        return PriceQuote(original_cents=3550, discount_cents=600, paid_cents=2950, source="mcp")

    @property
    def take_way_options(self) -> list[TakeWay]:
        return [
            TakeWay(code="eat-in", title="堂食", is_default=True),
            TakeWay(code="locker-in", title="取餐柜"),
        ]

    @property
    def default_take_way(self) -> str:
        return "eat-in"

    async def nearby_stores(self, address=None):
        return [
            Store(code="1421182", name="测试门店", city="深圳市", address="测试路 1 号"),
            Store(code="1421183", name="分店二", city="深圳市", address="测试路 2 号"),
        ]

    async def create_order(self, lines, **kwargs) -> OrderResult:
        self.order_kwargs = kwargs
        return OrderResult(
            order_id="ORD-777", pay_url="https://pay.example/777", paid_cents=2950
        )

    async def close(self) -> None:
        return None


@pytest.fixture
def order_env(tmp_path, monkeypatch):
    """隔离的本地配置 + 真实来源的 last_result + 桩数据源。"""
    monkeypatch.setenv("MCD_GACHA_HOME", str(tmp_path))
    monkeypatch.setenv("MCD_MCP_TOKEN", "test-token")
    monkeypatch.setenv("MCD_STORE_CODE", "1421182")
    monkeypatch.setenv("MCD_CITY", "深圳市")
    monkeypatch.setattr("mcd_gacha.datasource.mcp.McpDataSource", _StubMcpSource)

    import json

    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "pity": {},
                "history": [],
                "stats": {},
                "last_result": {
                    "ts": "2026-10-10T12:00:00",
                    "banner_key": "worker_up",
                    "rarity": "R",
                    "budget_cents": 3500,
                    "pull_index": 1,
                    "data_source": "mcp",
                    "items": [
                        {"code": "M1", "qty": 1},
                        {"code": "M2", "qty": 1},
                    ],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    _StubMcpSource.instances = []
    return tmp_path


def test_order_without_confirm_is_dry_run(order_env):
    """不加 --confirm：只试运行，绝不调用 create_order。"""
    result = runner.invoke(app, ["order", "--json"])
    assert result.exit_code == 0, result.output
    assert "dry_run" in result.output
    assert _StubMcpSource.instances[0].order_kwargs is None, "试运行不应下单"


def test_order_with_confirm_places_order(order_env):
    """加 --confirm：真正调用下单并展示订单号。"""
    result = runner.invoke(app, ["order", "--confirm", "--json"])
    assert result.exit_code == 0, result.output
    assert "ORD-777" in result.output
    kwargs = _StubMcpSource.instances[0].order_kwargs
    assert kwargs is not None
    assert kwargs["be_type"] == 1
    assert kwargs["order_type"] == 1


def test_order_refuses_mock_last_result(order_env):
    """最近一次是演示数据抽取时，必须拒绝下单。"""
    import json

    state_path = order_env / "state.json"
    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["last_result"]["data_source"] = "mock"
    state_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    result = runner.invoke(app, ["order", "--confirm"])
    assert result.exit_code == 1
    assert "无法下单" in result.output
    assert not _StubMcpSource.instances, "拒绝路径不应连接 MCP"


def test_order_without_prior_pull(order_env):
    """没有任何抽卡记录时给出友好提示。"""
    (order_env / "state.json").unlink()
    result = runner.invoke(app, ["order"])
    assert result.exit_code == 1
    assert "先运行" in result.output


def test_order_rejects_unsupported_be_type(order_env):
    """外送/团餐尚未实现，应明确拒绝而不是半成品下单。"""
    result = runner.invoke(app, ["order", "--confirm", "--be-type", "2"])
    assert result.exit_code == 2
    assert "尚未实现" in result.output


def test_order_dry_run_exposes_stores_and_take_way(order_env):
    """试运行需给出候选门店 + 取餐方式 + 确认提示，供用户先确认再下单。"""
    import json

    result = runner.invoke(app, ["order", "--json"])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.output)

    assert preview["mode"] == "dry_run"
    assert preview["store"]["code"] == "1421182"
    assert [s["code"] for s in preview["stores"]] == ["1421182", "1421183"]
    assert [t["code"] for t in preview["take_way"]] == ["eat-in", "locker-in"]
    assert preview["take_way_default"] == "eat-in"
    assert "--confirm" in preview["confirm_hint"]
    assert "--store-code 1421182" in preview["confirm_hint"]
    assert "--take-way-code eat-in" in preview["confirm_hint"]
    assert _StubMcpSource.instances[0].order_kwargs is None, "试运行不应下单"


def test_order_store_code_overrides_config(order_env):
    """--store-code 应在下单时覆盖本地配置的门店（地点确认）。"""
    result = runner.invoke(app, ["order", "--json", "--store-code", "9999999"])
    assert result.exit_code == 0, result.output
    assert _StubMcpSource.instances[0].store_code == "9999999"


def test_order_confirm_uses_chosen_take_way(order_env):
    """--take-way-code 应作为用户选定的取餐方式传给下单接口。"""
    result = runner.invoke(app, ["order", "--confirm", "--take-way-code", "locker-in"])
    assert result.exit_code == 0, result.output
    kwargs = _StubMcpSource.instances[0].order_kwargs
    assert kwargs is not None
    assert kwargs["take_way_code"] == "locker-in"


def test_order_human_preview_hint_uses_store_code(order_env):
    """人类可读预览的确认提示必须给出门店编号（而非门店名），否则照抄会失败。"""
    result = runner.invoke(app, ["order"])
    assert result.exit_code == 0, result.output
    assert "--store-code 1421182" in result.output
    assert "--take-way-code eat-in" in result.output
    assert "未产生任何订单" in result.output


def test_order_confirm_falls_back_to_default_take_way(order_env):
    """未显式指定取餐方式时，使用核价给出的默认项。"""
    result = runner.invoke(app, ["order", "--confirm", "--json"])
    assert result.exit_code == 0, result.output
    kwargs = _StubMcpSource.instances[0].order_kwargs
    assert kwargs is not None
    assert kwargs["take_way_code"] == "eat-in"
