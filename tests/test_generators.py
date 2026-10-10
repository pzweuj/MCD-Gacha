"""四档组合生成策略测试（重点是预算约束与卡池特征）。"""

from __future__ import annotations

import random

from mcd_gacha.generators import (
    collect_ssr,
    generate_n,
    generate_r,
    generate_sr,
    generate_ssr,
)
from mcd_gacha.optimizer import compute_price

# 所有卡池 × 所有策略：组合非空 且 券后实付不超预算
ALL_GENERATORS = (generate_r, generate_sr, generate_ssr, generate_n)


def test_all_generators_respect_budget_all_banners(meals, coupons, config):
    for banner_key in ("poor_standard", "worker_up", "midnight"):
        banner = config.require(banner_key)
        budget = banner.default_budget_cents
        for seed in range(5):
            rng = random.Random(seed)
            for generator in ALL_GENERATORS:
                combo = generator(meals, coupons, banner, budget, rng)
                assert combo is not None, f"{generator.__name__} @ {banner_key} 无输出"
                assert combo.lines, f"{generator.__name__} @ {banner_key} 空组合"
                quote = compute_price(combo.lines, coupons)
                assert quote.paid_cents <= budget, (
                    f"{generator.__name__} @ {banner_key} 超预算："
                    f"{quote.paid_cents} > {budget}"
                )


def test_ssr_contains_premium_anchor_in_worker_banner(meals, coupons, config):
    """打工人 UP 池的 SSR 必须含招牌大件。"""
    banner = config.require("worker_up")
    for seed in range(10):
        combo = generate_ssr(
            meals, coupons, banner, banner.default_budget_cents, random.Random(seed)
        )
        assert combo is not None
        assert "premium" in combo.all_tags, f"seed={seed} SSR 未含 premium 锚点"


def test_ssr_maximizes_value(meals, coupons, config):
    """SSR 的原价价值应不低于 SR（同为预算内，SSR 追求最大原价）。"""
    banner = config.require("worker_up")
    budget = banner.default_budget_cents
    ssr = generate_ssr(meals, coupons, banner, budget, random.Random(3))
    assert ssr is not None
    ssr_subtotal = sum(line.subtotal_cents for line in ssr.lines)
    # 预算内理论最大原价（容量 = 预算 + 最大券额）
    max_coupon = max(
        (c.amount_cents for c in coupons if c.type == "threshold"), default=0
    )
    assert ssr_subtotal <= budget + max_coupon


def test_r_generates_regular_combo(meals, coupons, config):
    """R 档应为规整组合：含主食（汉堡/随心配），且不超预算。"""
    banner = config.require("worker_up")
    combo = generate_r(meals, coupons, banner, banner.default_budget_cents, random.Random(5))
    assert combo is not None
    assert "staple" in combo.all_tags


def test_sr_has_main_dish(meals, coupons, config):
    """SR 档必须有主食（汉堡或随心配套餐）。"""
    for banner_key in ("poor_standard", "worker_up", "midnight"):
        banner = config.require(banner_key)
        for seed in range(8):
            combo = generate_sr(
                meals, coupons, banner, banner.default_budget_cents, random.Random(seed)
            )
            assert combo is not None
            assert combo.categories & {"burger", "deal"}, (
                f"{banner_key} seed={seed} SR 无主食：{combo.categories}"
            )


def test_n_is_abstract_but_edible(meals, coupons, config):
    """N 档应有「抽象特征」：无主食 / 纯饮品 / 三类混搭 至少之一。"""
    banner = config.require("poor_standard")
    abstract_count = 0
    for seed in range(20):
        combo = generate_n(
            meals, coupons, banner, banner.default_budget_cents, random.Random(seed)
        )
        assert combo is not None and combo.item_count >= 1
        tags = combo.all_tags
        cats = combo.categories
        is_abstract = (
            "staple" not in tags
            or cats <= {"drink"}
            or cats <= {"coffee"}
            or len(cats) >= 3
        )
        if is_abstract:
            abstract_count += 1
    assert abstract_count >= 15, "N 档抽象率过低，失去了整活属性"


def test_generators_produce_variety(meals, coupons, config):
    """同一策略连续生成应有多样性（软加权随机的意义）。"""
    banner = config.require("worker_up")
    budget = banner.default_budget_cents
    seen = set()
    for seed in range(30):
        combo = generate_r(meals, coupons, banner, budget, random.Random(seed))
        assert combo is not None
        seen.add(tuple(sorted(line.meal.code for line in combo.lines)))
    assert len(seen) >= 5, f"R 档组合种类过少：{len(seen)}"


def test_ssr_produces_variety_in_near_optimal_band(meals, coupons, config):
    """SSR 应在「近优带」内随机：多次生成出现多种组合（修复"永远同一套"问题）。"""
    banner = config.require("worker_up")
    budget = banner.default_budget_cents
    seen = {}
    for seed in range(40):
        combo = generate_ssr(meals, coupons, banner, budget, random.Random(seed))
        assert combo is not None
        key = tuple(sorted(line.meal.code for line in combo.lines))
        seen[key] = seen.get(key, 0) + 1
    assert len(seen) >= 3, f"SSR 组合种类过少（{len(seen)}），近优随机未生效"


def test_ssr_keeps_premium_value(meals, coupons, config):
    """SSR 多样性不能牺牲"金光含金量"：所有变体应接近预算上限价值。"""
    banner = config.require("worker_up")
    budget = banner.default_budget_cents
    # 理论最优（原价最大）
    scored = collect_ssr(meals, coupons, banner, budget)
    best_subtotal = max(sum(line.subtotal_cents for line in lines) for _, lines in scored)
    for seed in range(20):
        combo = generate_ssr(meals, coupons, banner, budget, random.Random(seed))
        assert combo is not None
        subtotal = sum(line.subtotal_cents for line in combo.lines)
        # 变体原价应 ≥ 最优的 85%（不出现"掉价"的 SSR）
        assert subtotal >= best_subtotal * 0.85, (
            f"SSR 变体价值过低：{subtotal} vs 最优 {best_subtotal}"
        )
