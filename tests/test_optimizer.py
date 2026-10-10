"""背包与价格计算测试。"""

from __future__ import annotations

from mcd_gacha.models import Coupon, LineItem, Meal
from mcd_gacha.optimizer import best_subset, compute_price, fits_budget, plan_with_required


def _meal(code: str, price_yuan: float, tags: tuple[str, ...] = ()) -> Meal:
    return Meal(
        code=code,
        name=code,
        category="burger",
        price_cents=int(round(price_yuan * 100)),
        tags=tags,
    )


def _subtotal(lines: list[LineItem]) -> int:
    return sum(line.subtotal_cents for line in lines)


# ---------------------------------------------------------------------------
# 0/1 背包
# ---------------------------------------------------------------------------


def test_best_subset_respects_capacity():
    meals = [_meal("A", 10), _meal("B", 15), _meal("C", 7)]
    lines = best_subset(meals, 2000)
    total = _subtotal(lines)
    assert total <= 2000
    assert total == 1700  # 10 + 7 为预算内最大（15 + 7 = 22 超出）


def test_best_subset_exact_fit():
    meals = [_meal("A", 10), _meal("B", 15)]
    lines = best_subset(meals, 1500)
    assert _subtotal(lines) == 1500


def test_best_subset_uses_each_item_once():
    meals = [_meal("A", 10)]
    lines = best_subset(meals, 5000)
    assert len(lines) == 1  # 0/1：同一商品只用一次


def test_best_subset_empty_when_capacity_too_small():
    meals = [_meal("A", 10)]
    assert best_subset(meals, 500) == []


def test_plan_with_required_contains_anchor():
    anchor = _meal("ANCHOR", 22, ("premium",))
    meals = [anchor, _meal("A", 8), _meal("B", 9)]
    lines = plan_with_required(meals, 1000, [anchor])
    assert any(line.meal.code == "ANCHOR" for line in lines)
    assert _subtotal(lines) <= 2200 + 1000


# ---------------------------------------------------------------------------
# 价格计算（券语义）
# ---------------------------------------------------------------------------


def test_threshold_coupon_applies_above_threshold():
    lines = [LineItem(_meal("A", 30))]
    coupons = [Coupon("C1", "满25减4", "threshold", 400, threshold_cents=2500)]
    quote = compute_price(lines, coupons)
    assert quote.paid_cents == 2600
    assert quote.coupon_id == "C1"


def test_threshold_coupon_not_applied_below_threshold():
    lines = [LineItem(_meal("A", 20))]
    coupons = [Coupon("C1", "满25减4", "threshold", 400, threshold_cents=2500)]
    quote = compute_price(lines, coupons)
    assert quote.paid_cents == 2000
    assert quote.coupon_id is None


def test_best_coupon_is_selected():
    lines = [LineItem(_meal("A", 35))]
    coupons = [
        Coupon("C1", "满25减4", "threshold", 400, threshold_cents=2500),
        Coupon("C2", "满30减6", "threshold", 600, threshold_cents=3000),
    ]
    quote = compute_price(lines, coupons)
    assert quote.coupon_id == "C2"
    assert quote.paid_cents == 2900


def test_item_coupon_requires_target_item():
    lines = [LineItem(_meal("A", 20)), LineItem(_meal("B", 10))]
    coupons = [Coupon("C1", "A立减3", "item", 300, item_code="A")]
    quote = compute_price(lines, coupons)
    assert quote.paid_cents == 2700

    no_target = [LineItem(_meal("B", 10))]
    assert compute_price(no_target, coupons).paid_cents == 1000


def test_fits_budget():
    lines = [LineItem(_meal("A", 30))]
    coupons = [Coupon("C1", "满30减6", "threshold", 600, threshold_cents=3000)]
    assert fits_budget(lines, coupons, 2400)
    assert not fits_budget(lines, coupons, 2300)
