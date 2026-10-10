"""四档稀有度的组合生成策略。

架构（v0.2 重构）：
- collect_*：收集全部合法候选并评分（**确定性**，引擎层可缓存复用）；
- pick_combo 逻辑（`_pick`）：从候选中软加权随机选取（随机性只在这一步）；
- generate_*：薄壳（collect + pick），保持向后兼容。

性能设计：
- 候选池先按预算过滤（单价 ≤ 预算）；
- 组合枚举采用「价格升序 + 超预算剪枝」（只生成合法组合）；
- 剪枝保证小计 ≤ 预算，因此「券后实付 ≤ 预算」恒成立（券只降不升）；
- 大菜单（>40 候选）下 N 档退化为固定种子采样，保证确定性可缓存。

统一约定：
- collect_*(meals, coupons, banner, budget_cents) -> list[(score, lines)]
- 组合件数上限 3（预算 15~40 元区间内符合真实点餐习惯）。
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator

from .banners import Banner
from .i18n import FLAVOR_POOL
from .models import Combo, Coupon, LineItem, Meal
from .optimizer import compute_price, plan_with_required
from .rarity import Rarity

MAX_ITEMS = 3  # 组合最大件数


def _subtotal(lines: list[LineItem]) -> int:
    return sum(line.subtotal_cents for line in lines)


def _tags(lines: list[LineItem]) -> set[str]:
    tags: set[str] = set()
    for line in lines:
        tags.update(line.meal.tags)
    return tags


def _categories(lines: list[LineItem]) -> set[str]:
    return {line.meal.category for line in lines}


def _build_pool(meals: list[Meal], budget_cents: int) -> list[Meal]:
    """候选池：单价在预算内的商品。"""
    return [meal for meal in meals if 0 < meal.price_cents <= budget_cents]


def _iter_combos(
    pool: list[Meal], budget_cents: int, max_k: int, allow_repeat: bool
) -> Iterator[tuple[Meal, ...]]:
    """枚举合法组合（小计 ≤ budget_cents）。

    价格升序 + 剪枝：一旦累计金额超预算即终止该分支（排序保证后续更大）。
    """
    items = sorted(pool, key=lambda meal: meal.price_cents)
    prices = [meal.price_cents for meal in items]
    n = len(items)

    def rec(start: int, k: int, prefix: tuple[Meal, ...], prefix_sum: int):
        for index in range(start, n):
            total = prefix_sum + prices[index]
            if total > budget_cents:
                break  # 升序剪枝
            combo = prefix + (items[index],)
            if k == 1:
                yield combo
            else:
                next_start = index if allow_repeat else index + 1
                yield from rec(next_start, k - 1, combo, total)

    for k in range(1, max_k + 1):
        yield from rec(0, k, (), 0)


def _pick(
    scored: list[tuple[float, list[LineItem]]],
    rng: random.Random,
    rarity: Rarity,
    top_n: int = 12,
    temperature: float = 1.0,
) -> Combo | None:
    """从候选集中选择。

    - SSR：在「近优带」（≥ 最优分的 88%）内按优势软加权随机——
      保留"金光最豪华"定位的同时避免同预算下永远出同一套组合；
    - 其余：在评分 top_n 内软加权随机。
    """
    if not scored:
        return None
    if rarity is Rarity.SSR:
        best_score = max(score for score, _ in scored)
        band = [(score, lines) for score, lines in scored if score >= best_score * 0.88]
        weights = [math.exp((score - best_score) / 1.2) for score, _ in band]
        _, lines = rng.choices(band, weights=weights, k=1)[0]
        return Combo(lines=lines, flavor=rng.choice(FLAVOR_POOL[rarity]))
    scored.sort(key=lambda item: -item[0])
    pool = scored[:top_n]
    max_score = pool[0][0]
    weights = [math.exp((score - max_score) / temperature) for score, _ in pool]
    _, lines = rng.choices(pool, weights=weights, k=1)[0]
    return Combo(lines=lines, flavor=rng.choice(FLAVOR_POOL[rarity]))


def _prefer_bonus(tags: set[str], banner: Banner) -> float:
    return 0.25 * len([t for t in banner.prefer_tags if t in tags])


# ---------------------------------------------------------------------------
# R：经典保底 —— 规矩的一顿（1+1 随心配 / 主 + 配角）
# ---------------------------------------------------------------------------


def collect_r(
    meals: list[Meal], coupons: list[Coupon], banner: Banner, budget_cents: int
) -> list[tuple[float, list[LineItem]]]:
    scored: list[tuple[float, list[LineItem]]] = []
    pool = _build_pool(meals, budget_cents)
    for combo in _iter_combos(pool, budget_cents, MAX_ITEMS, allow_repeat=False):
        lines = [LineItem(meal=m, qty=1) for m in combo]
        subtotal = _subtotal(lines)
        if subtotal <= 0:
            continue
        util = subtotal / budget_cents
        if util < 0.5:
            continue
        tags = _tags(lines)
        n = len(lines)

        score = 0.0
        if n == 1:
            # 单品仅当接近预算上限时算「规整」（如 1+1 套餐）
            if util >= 0.75:
                score += 1.0
            else:
                continue
        elif n == 2:
            score += 1.5
        else:
            score += 0.5

        if "classic" in tags:
            score += 1.5
        if "value" in tags:
            score += 1.0
        if "deal" in tags:
            score += 1.2
        if "staple" in tags:
            score += 1.0
        if util >= 0.8:
            score += 0.8
        score += _prefer_bonus(tags, banner)

        scored.append((score, lines))
    return scored


# ---------------------------------------------------------------------------
# SR：稳稳的幸福 —— 经典热销正餐（主 + 配 + 饮）
# ---------------------------------------------------------------------------


def collect_sr(
    meals: list[Meal], coupons: list[Coupon], banner: Banner, budget_cents: int
) -> list[tuple[float, list[LineItem]]]:
    scored: list[tuple[float, list[LineItem]]] = []
    pool = _build_pool(meals, budget_cents)
    for combo in _iter_combos(pool, budget_cents, MAX_ITEMS, allow_repeat=False):
        lines = [LineItem(meal=m, qty=1) for m in combo]
        subtotal = _subtotal(lines)
        if subtotal <= 0:
            continue
        util = subtotal / budget_cents
        if util < 0.7:
            continue
        tags = _tags(lines)
        cats = _categories(lines)

        has_main = bool(cats & {"burger", "deal"})
        has_side = "snack" in cats
        has_drink = bool(cats & {"drink", "coffee"})
        if not has_main:
            continue  # 正餐必须有主食（汉堡或随心配套餐）

        score = 1.5  # 已保证含主食
        if has_side:
            score += 1.0
        if has_drink:
            score += 1.0
        if has_side and has_drink:
            score += 1.5  # 三件套完整正餐
        if "classic" in tags:
            score += 1.2
        if "premium" in tags:
            score += 0.8
        for tag in banner.require_tags:
            if tag in tags:
                score += 0.6
        if util >= 0.8:
            score += 1.0
        if util >= 0.9:
            score += 0.5
        score += _prefer_bonus(tags, banner)

        scored.append((score, lines))
    return scored


# ---------------------------------------------------------------------------
# SSR：欧皇时刻 —— 预算内价值最大化（0/1 背包 + 券方案枚举）
# ---------------------------------------------------------------------------


def collect_ssr(
    meals: list[Meal], coupons: list[Coupon], banner: Banner, budget_cents: int
) -> list[tuple[float, list[LineItem]]]:
    """枚举「券方案 × 必含锚点」组合，评分 = 原价价值（tie-break：饮品/件数）。"""
    candidates: list[list[LineItem]] = []

    anchors: list[Meal | None] = [None]
    if banner.require_tags:
        matched = [m for m in meals if any(m.has_tag(t) for t in banner.require_tags)]
        if matched:
            anchors = list(matched)

    threshold_coupons = [c for c in coupons if c.type == "threshold" and c.threshold_cents]
    item_coupons = [c for c in coupons if c.type == "item" and c.item_code]

    def _accept_candidate(lines: list[LineItem]) -> None:
        # 统一校验：券后实付 ≤ 预算（mock 菜单下必然成立，防菜单异常）
        if lines and compute_price(lines, coupons).paid_cents <= budget_cents:
            candidates.append(lines)

    for anchor in anchors:
        required = [anchor] if anchor else []
        required_price = sum(m.price_cents for m in required)

        # 方案 0：不使用券
        if required_price <= budget_cents:
            _accept_candidate(
                plan_with_required(meals, budget_cents - required_price, required)
            )

        # 方案 1：每种满减券 → 容量放宽至 预算 + 券额，使用券后门槛由核价校验
        for coupon in threshold_coupons:
            capacity = budget_cents + coupon.amount_cents - required_price
            if capacity < 0:
                continue
            _accept_candidate(plan_with_required(meals, capacity, required))

        # 方案 2：每种单品券 → 必含目标商品，容量按折扣放宽
        for coupon in item_coupons:
            target = next((m for m in meals if m.code == coupon.item_code), None)
            if target is None:
                continue
            req = list(required)
            if all(m.code != target.code for m in req):
                req.append(target)
            capacity = budget_cents + coupon.amount_cents - sum(m.price_cents for m in req)
            if capacity < 0:
                continue
            _accept_candidate(plan_with_required(meals, capacity, req))

    scored: list[tuple[float, list[LineItem]]] = []
    seen: set[tuple[str, ...]] = set()
    for lines in candidates:
        # 去重：不同券方案可能产出相同组合（保留首个即可）
        signature = tuple(sorted(line.meal.code for line in lines))
        if signature in seen:
            continue
        seen.add(signature)
        subtotal = _subtotal(lines)
        has_drink = any(line.meal.category in ("drink", "coffee") for line in lines)
        score = subtotal + (0.5 if has_drink else 0.0) + len(lines) * 0.1
        scored.append((score, lines))
    return scored


# ---------------------------------------------------------------------------
# N：隐藏款 —— 抽象整活（类别跳跃 / 凑单精度 / 意料之外）
# ---------------------------------------------------------------------------


def collect_n(
    meals: list[Meal], coupons: list[Coupon], banner: Banner, budget_cents: int
) -> list[tuple[float, list[LineItem]]]:
    """以「离谱度」评分挑选组合：有趣、能吃、数量克制（预算内适度点餐）。"""
    pool = _build_pool(meals, budget_cents)
    # 大菜单下限制枚举规模（固定种子采样，保证确定性以支持缓存）
    if len(pool) > 40:
        return _collect_n_sampled(pool, budget_cents)

    scored: list[tuple[float, list[LineItem]]] = []
    for combo in _iter_combos(pool, budget_cents, MAX_ITEMS, allow_repeat=True):
        lines = [LineItem(meal=m, qty=1) for m in combo]
        score = _score_absurdity(lines, budget_cents)
        if score is not None:
            scored.append((score, lines))
    return scored


def _collect_n_sampled(
    pool: list[Meal], budget_cents: int, samples: int = 4000
) -> list[tuple[float, list[LineItem]]]:
    """大菜单下的采样版 N 候选收集（固定种子保证确定性，便于缓存）。"""
    rng = random.Random(0x9CD0)  # 固定采样种子
    scored: list[tuple[float, list[LineItem]]] = []
    items = sorted(pool, key=lambda meal: meal.price_cents)
    tried = 0
    while tried < samples:
        tried += 1
        k = rng.choice((2, 3, 3, 3))  # 偏向 3 件（更抽象）
        combo: list[Meal] = []
        total = 0
        ok = True
        for _ in range(k):
            candidates = [m for m in items if total + m.price_cents <= budget_cents]
            if not candidates:
                ok = False
                break
            # 偏向低价商品（提高合法组合命中率），再随机取
            pick = rng.choice(candidates[: max(3, len(candidates) // 2)])
            combo.append(pick)
            total += pick.price_cents
        if not ok or not combo:
            continue
        lines = [LineItem(meal=m, qty=1) for m in combo]
        score = _score_absurdity(lines, budget_cents)
        if score is not None:
            scored.append((score, lines))
    return scored


def _score_absurdity(lines: list[LineItem], budget_cents: int) -> float | None:
    subtotal = _subtotal(lines)
    if subtotal <= 0:
        return None
    util = subtotal / budget_cents
    tags = _tags(lines)
    cats = _categories(lines)
    n = len(lines)

    absurd = 0.0
    if len(cats) >= 3:
        absurd += 2.0  # 三类混搭（如 汉堡 + 咖啡 + 冰淇淋）
    elif len(cats) == 2:
        absurd += 0.5
    if "staple" not in tags:
        absurd += 1.5  # 没有正经主食
    if cats <= {"drink"}:
        absurd += 2.5  # 全是饮料
    if cats <= {"coffee"}:
        absurd += 2.0  # 全是咖啡
    if cats <= {"snack"}:
        absurd += 1.0  # 全是小食
    if "coffee" in tags and ("hot" in tags or "side" in tags):
        absurd += 1.5  # 咖啡配炸物的神秘搭配
    if util >= 0.95:
        absurd += 1.5  # 分毫凑满预算
    if n >= 3:
        absurd += 0.5
    if any(line.qty >= 2 for line in lines):
        absurd += 0.8  # 同款多份
    if n == 1:
        absurd -= 1.0
    return absurd


# ---------------------------------------------------------------------------
# 向后兼容的 generate_* 接口（collect + pick）
# ---------------------------------------------------------------------------


def generate_r(meals, coupons, banner, budget_cents, rng) -> Combo | None:
    return _pick(collect_r(meals, coupons, banner, budget_cents), rng, Rarity.R)


def generate_sr(meals, coupons, banner, budget_cents, rng) -> Combo | None:
    return _pick(collect_sr(meals, coupons, banner, budget_cents), rng, Rarity.SR)


def generate_ssr(meals, coupons, banner, budget_cents, rng) -> Combo | None:
    return _pick(collect_ssr(meals, coupons, banner, budget_cents), rng, Rarity.SSR)


def generate_n(meals, coupons, banner, budget_cents, rng) -> Combo | None:
    return _pick(collect_n(meals, coupons, banner, budget_cents), rng, Rarity.N, top_n=8)


# 收集器注册表（引擎按稀有度取用）
COLLECTORS = {
    Rarity.R: collect_r,
    Rarity.SR: collect_sr,
    Rarity.SSR: collect_ssr,
    Rarity.N: collect_n,
}

# 公开选择接口（引擎层使用）
pick_combo = _pick
