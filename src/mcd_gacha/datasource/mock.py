"""内置演示数据源：读取随包发布的菜单/券快照，完全离线可用。

内容为「典型菜单快照」，用于无 Token 场景下完整跑通抽卡体验；
真实价格与供应状态请使用 --real（McpDataSource）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..models import Coupon, LineItem, Meal, Nutrition, OrderResult, PriceQuote, Store, yuan
from ..optimizer import compute_price
from .base import OrderNotSupportedError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MENU_FILE = DATA_DIR / "mock_menu.json"
PRICES_FILE = DATA_DIR / "mock_prices.json"


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class MockDataSource:
    """读取打包快照的离线数据源。"""

    mode = "mock"

    def __init__(self, menu_path: Path | None = None, prices_path: Path | None = None) -> None:
        menu_raw = _load_json(menu_path or MENU_FILE)
        prices_raw = _load_json(prices_path or PRICES_FILE)

        self.snapshot_note: str = menu_raw.get("snapshot_note", "")
        self.store = Store(
            code=menu_raw.get("store", {}).get("code", "MOCK-001"),
            name=menu_raw.get("store", {}).get("name", "金拱门 · 演示餐厅"),
            city=menu_raw.get("store", {}).get("city", ""),
        )
        self._meals: list[Meal] = [
            Meal(
                code=item["code"],
                name=item["name"],
                category=item["category"],
                price_cents=yuan(item["price"]),
                tags=tuple(item.get("tags", [])),
                calories=item.get("calories"),
            )
            for item in menu_raw.get("items", [])
        ]
        self._coupons: list[Coupon] = [
            Coupon(
                id=coupon["id"],
                name=coupon["name"],
                type=coupon["type"],
                amount_cents=yuan(coupon["amount"]),
                threshold_cents=yuan(coupon["threshold"]) if coupon.get("threshold") else None,
                item_code=coupon.get("item_code"),
                desc=coupon.get("desc", ""),
            )
            for coupon in prices_raw.get("coupons", [])
        ]

    # ------------------------------------------------------------------
    # 只读属性（便于测试与外部检查）
    # ------------------------------------------------------------------

    @property
    def meals(self) -> list[Meal]:
        return list(self._meals)

    @property
    def coupons(self) -> list[Coupon]:
        return list(self._coupons)

    # ------------------------------------------------------------------
    # MenuDataSource 协议实现
    # ------------------------------------------------------------------

    async def query_meals(self, store_code: str | None = None) -> list[Meal]:
        return list(self._meals)

    async def calculate_price(self, lines: list[LineItem]) -> PriceQuote:
        quote = compute_price(lines, self._coupons)
        quote.source = self.mode
        return quote

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
        """内置演示数据没有真实 SKU，无法下单——显式拒绝而不是伪造订单。"""
        raise OrderNotSupportedError(
            "内置演示数据不支持下单：组合中的商品编码不是真实 SKU。"
            "请先用真实模式抽卡（mcd-gacha pull --real）后再下单。"
        )

    async def list_coupons(self, store_code: str | None = None) -> list[Coupon]:
        return list(self._coupons)

    async def list_nutrition(self, codes: list[str]) -> dict[str, Nutrition]:
        wanted = set(codes)
        result: dict[str, Nutrition] = {}
        for meal in self._meals:
            if meal.code in wanted and meal.calories is not None:
                result[meal.code] = Nutrition(energy_kcal=meal.calories)
        return result

    async def nearby_stores(self, address: str | None = None) -> list[Store]:
        return [self.store]

    async def now_time(self) -> datetime:
        return datetime.now().astimezone()

    async def close(self) -> None:
        return None
