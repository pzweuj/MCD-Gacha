"""价格计算与组合优化。

- compute_price：复刻 MCP calculate-price 的语义（单券最优）；
- best_subset：0/1 背包，在预算容量内选出小计最大（即「预算内点最贵」）的组合。
"""

from __future__ import annotations

from .models import Coupon, LineItem, Meal, PriceQuote


def coupon_discount(coupon: Coupon, lines: list[LineItem], subtotal_cents: int) -> int:
    """计算单张券可减免的金额（不可用时为 0）。"""
    if coupon.type == "threshold":
        if coupon.threshold_cents is not None and subtotal_cents >= coupon.threshold_cents:
            return coupon.amount_cents
        return 0
    if coupon.type == "item":
        if coupon.item_code and any(line.meal.code == coupon.item_code for line in lines):
            # 每单最多核销一次
            return coupon.amount_cents
        return 0
    return 0


def compute_price(lines: list[LineItem], coupons: list[Coupon] | None = None) -> PriceQuote:
    """计算点单价格：自动选择最优惠的一张券（与真实点餐惯例一致）。"""
    subtotal = sum(line.subtotal_cents for line in lines)
    best_coupon: Coupon | None = None
    best_discount = 0
    for coupon in coupons or []:
        discount = coupon_discount(coupon, lines, subtotal)
        if discount > best_discount:
            best_discount = discount
            best_coupon = coupon

    paid = max(0, subtotal - best_discount)
    return PriceQuote(
        original_cents=subtotal,
        discount_cents=best_discount,
        paid_cents=paid,
        coupon_id=best_coupon.id if best_coupon else None,
        coupon_name=best_coupon.name if best_coupon else None,
        source="mock",
    )


def plan_with_required(
    meals: list[Meal],
    remaining_capacity_cents: int,
    required: list[Meal] | None = None,
) -> list[LineItem]:
    """构造「必含 required 组合」+ 剩余容量内的最优子集。"""
    required = required or []
    lines: list[LineItem] = [LineItem(meal=m, qty=1) for m in required]
    used = {m.code for m in required}
    rest = [m for m in meals if m.code not in used]
    if remaining_capacity_cents < 0:
        return []
    if remaining_capacity_cents > 0 and rest:
        lines.extend(best_subset(rest, remaining_capacity_cents))
    return lines


def best_subset(meals: list[Meal], capacity_cents: int) -> list[LineItem]:
    """0/1 背包：在容量内选出小计金额最大的餐品子集。

    「价值 = 重量 = 单价」，即目标为预算内点最贵的组合。
    复杂度 O(n × capacity)，菜单规模下为微秒~毫秒级。
    """
    if capacity_cents <= 0 or not meals:
        return []

    items = [m for m in meals if m.price_cents <= capacity_cents]
    weights = [m.price_cents for m in items]

    reach = [False] * (capacity_cents + 1)
    parent: list[tuple[int, int] | None] = [None] * (capacity_cents + 1)
    reach[0] = True

    for index, weight in enumerate(weights):
        # 从后往前更新，保证每个物品最多使用一次（0/1 背包）
        for cap in range(capacity_cents, weight - 1, -1):
            if reach[cap - weight] and not reach[cap]:
                reach[cap] = True
                parent[cap] = (cap - weight, index)

    best_cap = 0
    for cap in range(capacity_cents, -1, -1):
        if reach[cap]:
            best_cap = cap
            break

    lines: list[LineItem] = []
    cursor = best_cap
    while cursor > 0 and parent[cursor] is not None:
        prev_cap, index = parent[cursor]
        lines.append(LineItem(meal=items[index], qty=1))
        cursor = prev_cap
    return lines


def fits_budget(lines: list[LineItem], coupons: list[Coupon], budget_cents: int) -> bool:
    """组合券后实付是否在预算内。"""
    return compute_price(lines, coupons).paid_cents <= budget_cents
