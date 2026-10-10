"""数据源抽象协议。

上层引擎只依赖本协议，因此：
- 无 Token 用户 → MockDataSource（内置演示快照，完全离线可玩）；
- 有 Token 用户 → McpDataSource（真实菜单与核价，失败时回退 mock）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..models import Coupon, LineItem, Meal, Nutrition, OrderResult, PriceQuote, Store


class OrderNotSupportedError(RuntimeError):
    """当前数据源不支持下单（如内置演示数据）。"""


@runtime_checkable
class MenuDataSource(Protocol):
    """菜单与核价数据源。"""

    mode: str  # "mock" | "mcp"

    async def query_meals(self, store_code: str | None = None) -> list[Meal]:
        """查询当前可售卖餐品列表。"""
        ...

    async def calculate_price(self, lines: list[LineItem]) -> PriceQuote:
        """计算点单价格（自动选择最优惠券）。"""
        ...

    async def create_order(
        self,
        lines: list[LineItem],
        *,
        be_type: int = 1,
        order_type: int = 1,
        address_id: str | None = None,
        remark: str | None = None,
        take_way_code: str | None = None,
    ) -> OrderResult:
        """创建订单（默认到店自取）。

        安全约定：仅由 CLI 的 `order --confirm` 调用，调用方负责二次确认。
        内置演示数据源不支持，会抛出 OrderNotSupportedError。
        """
        ...

    async def list_coupons(self, store_code: str | None = None) -> list[Coupon]:
        """查询可用优惠券列表。"""
        ...

    async def list_nutrition(self, codes: list[str]) -> dict[str, Nutrition]:
        """查询餐品营养信息（按编码索引）。"""
        ...

    async def nearby_stores(self, address: str | None = None) -> list[Store]:
        """查询附近门店。"""
        ...

    async def now_time(self) -> datetime:
        """获取当前时间（真实模式走 MCP now-time-info，用于深夜池判定）。"""
        ...

    async def close(self) -> None:
        """释放资源。"""
        ...
