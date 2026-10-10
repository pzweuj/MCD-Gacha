"""核心数据模型：餐品、券、组合、报价与抽卡结果。

金额约定：内部一律使用「分」（int）流转，仅展示层转换为元，避免浮点误差。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .rarity import RARITY_LABELS, Rarity


def yuan(value: float) -> int:
    """元 → 分。"""
    return int(round(value * 100))


def format_price(cents: int) -> str:
    """分 → 展示用价格字符串（去掉多余的 0）：1390 → '13.9'，2500 → '25'。"""
    text = f"{cents / 100:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


@dataclass(frozen=True)
class Meal:
    """单个餐品（或套餐 SKU）。"""

    code: str
    name: str
    category: str  # burger / snack / drink / coffee / deal
    price_cents: int
    tags: tuple[str, ...] = ()
    calories: int | None = None

    @property
    def price_yuan(self) -> str:
        return format_price(self.price_cents)

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags


@dataclass(frozen=True)
class Coupon:
    """优惠券。

    type = "threshold"：整单满 threshold 减 amount；
    type = "item"：指定 item_code 商品立减 amount（每单最多减一次）；
    type = "external"：真实 MCP 券（金额/门槛未知，交由服务端核价时计算）。

    code 为真实券码（mock 券可为 None）。
    """

    id: str
    name: str
    type: str
    amount_cents: int
    threshold_cents: int | None = None
    item_code: str | None = None
    desc: str = ""
    code: str | None = None


@dataclass
class LineItem:
    """组合中的一行：餐品 + 数量。"""

    meal: Meal
    qty: int = 1

    @property
    def subtotal_cents(self) -> int:
        return self.meal.price_cents * self.qty


@dataclass
class Combo:
    """一次生成的候选组合。"""

    lines: list[LineItem] = field(default_factory=list)
    coupon_id: str | None = None
    flavor: str = ""

    @property
    def subtotal_cents(self) -> int:
        return sum(line.subtotal_cents for line in self.lines)

    @property
    def item_count(self) -> int:
        return sum(line.qty for line in self.lines)

    @property
    def categories(self) -> set[str]:
        return {line.meal.category for line in self.lines}

    @property
    def all_tags(self) -> set[str]:
        tags: set[str] = set()
        for line in self.lines:
            tags.update(line.meal.tags)
        return tags

    def codes(self) -> list[str]:
        """返回展开的餐品编码列表（含重复）。"""
        out: list[str] = []
        for line in self.lines:
            out.extend([line.meal.code] * line.qty)
        return out


@dataclass
class PriceQuote:
    """价格计算结果（与 MCP calculate-price 语义一致）。"""

    original_cents: int  # 原价小计
    discount_cents: int  # 优惠金额
    paid_cents: int  # 应付
    coupon_id: str | None = None
    coupon_name: str | None = None
    source: str = "mock"  # mock / mcp

    @property
    def saved_ratio(self) -> float:
        if self.original_cents <= 0:
            return 0.0
        return self.discount_cents / self.original_cents


@dataclass
class OrderResult:
    """下单结果（真实 MCP create-order 返回）。

    字段名做多路兜底：不同场景返回的键名可能不同，未识别到的字段
    保留在 raw 中由 CLI 原样展示，避免静默丢信息。
    """

    order_id: str | None = None
    pay_url: str | None = None
    paid_cents: int | None = None
    status: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好的字典。"""
        return {
            "order_id": self.order_id,
            "pay_url": self.pay_url,
            "paid": format_price(self.paid_cents) if self.paid_cents is not None else None,
            "status": self.status,
        }


@dataclass(frozen=True)
class TakeWay:
    """取餐方式（下单时用户需要确认的选项之一）。

    code 即 create-order 的 takeWayCode，来源为 calculate-price 返回的 takeWayList。
    到店自取场景下该字段必传，因此下单前必须让用户明确选择。
    """

    code: str
    title: str = ""
    is_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好的字典。"""
        return {"code": self.code, "title": self.title, "is_default": self.is_default}


@dataclass
class Nutrition:
    """营养信息（mock 仅有热量，真实 MCP 可提供更全字段）。"""

    energy_kcal: int | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    sodium_mg: float | None = None


@dataclass
class Store:
    """门店信息。"""

    code: str
    name: str
    city: str = ""
    address: str = ""


@dataclass
class PullResult:
    """一次抽卡的完整结果。"""

    rarity: Rarity
    banner_key: str
    banner_name: str
    lines: list[LineItem]
    quote: PriceQuote
    flavor: str = ""
    nutrition: Nutrition | None = None
    ts: datetime | None = None
    pity_after: int = 0  # 本次抽卡后的保底计数
    free_pull: bool = False
    pull_index: int = 0  # 十连时的序号（1 起），单抽为 1
    data_source: str = "mock"

    @property
    def total_calories(self) -> int | None:
        total = 0
        has_value = False
        for line in self.lines:
            if line.meal.calories is None:
                continue
            has_value = True
            total += line.meal.calories * line.qty
        return total if has_value else None

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好的字典（--json 输出）。"""
        return {
            "rarity": self.rarity.value,
            "rarity_label": RARITY_LABELS[self.rarity],
            "banner": self.banner_key,
            "banner_name": self.banner_name,
            "items": [
                {
                    "code": line.meal.code,
                    "name": line.meal.name,
                    "qty": line.qty,
                    "price": line.meal.price_yuan,
                    "calories": line.meal.calories,
                }
                for line in self.lines
            ],
            "price": {
                "original": format_price(self.quote.original_cents),
                "discount": format_price(self.quote.discount_cents),
                "paid": format_price(self.quote.paid_cents),
                "coupon": self.quote.coupon_name,
            },
            "total_calories": self.total_calories,
            "flavor": self.flavor,
            "pity_after": self.pity_after,
            "free_pull": self.free_pull,
            "pull_index": self.pull_index,
            "ts": self.ts.isoformat() if self.ts else None,
            "data_source": self.data_source,
        }
