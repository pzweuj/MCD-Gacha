"""抽卡引擎：概率、保底、生成调度、核价与状态维护。

核心不变量：
1. 保底：某卡池连续 9 发未出 SSR 后，下一发（第 10 发）必出 SSR；
2. 预算：所有产出的组合在核价后实付不超过预算；
3. 一致性：十连 = 顺序 10 次单抽，共享同一保底计数器。
"""

from __future__ import annotations

import random
from datetime import datetime
from statistics import mean

from .banners import Banner, BannerConfig, load_banner_config
from .datasource.base import MenuDataSource
from .generators import COLLECTORS, pick_combo
from .i18n import FLAVOR_POOL, REROLL_FLAVORS
from .models import Combo, Coupon, LineItem, Meal, Nutrition, PullResult, yuan
from .optimizer import compute_price
from .rarity import Rarity
from .state import GachaState, save_state

# 稀有度抽样的固定遍历顺序（与权重字典顺序一致，保证结果可复现）
_RARITY_ORDER = ("SSR", "SR", "R", "N")


class GachaError(Exception):
    """抽卡业务错误（卡池未开放、组合无法生成等）。"""


class McdGacha:
    """麦门抽卡引擎。"""

    def __init__(
        self,
        source: MenuDataSource,
        *,
        state: GachaState | None = None,
        config: BannerConfig | None = None,
        rng: random.Random | None = None,
        state_path=None,
        persist_state: bool = True,
    ) -> None:
        self.source = source
        self.config = config or load_banner_config()
        self.state = state or GachaState()
        self.rng = rng or random.Random()
        self.state_path = state_path
        self.persist_state = persist_state
        # 会话级缓存：同一进程内菜单与券只拉取一次（真实 MCP 模式下省请求）
        self._menu_cache: list[Meal] | None = None
        self._coupon_cache: list[Coupon] | None = None
        # 候选评分缓存：同卡池/预算下十连的 10 次生成只做一次枚举（性能关键）
        self._scored_cache: dict[tuple[str, str, int], list[tuple[float, list[LineItem]]]] = {}

    # ------------------------------------------------------------------
    # 概率层
    # ------------------------------------------------------------------

    def _roll_rarity(self, banner: Banner) -> Rarity:
        """保底优先，其余按基础权重加权抽样。"""
        if self.state.pity_for(banner.key) >= self.config.hard_pity - 1:
            return Rarity.SSR
        return self._weighted_roll(self.rng, self.config.rarity_weights)

    @staticmethod
    def _weighted_roll(rng: random.Random, weights: dict[str, int]) -> Rarity:
        total = sum(weights.values()) or 100
        point = rng.random() * total
        acc = 0.0
        for name in _RARITY_ORDER:
            acc += weights.get(name, 0)
            if point < acc:
                return Rarity(name)
        return Rarity.N  # 浮点兜底

    def _update_pity(self, banner: Banner, rarity: Rarity) -> None:
        if rarity is Rarity.SSR:
            self.state.pity[banner.key] = 0
        else:
            self.state.pity[banner.key] = self.state.pity_for(banner.key) + 1

    # ------------------------------------------------------------------
    # 抽卡主流程
    # ------------------------------------------------------------------

    async def roll(
        self,
        banner_key: str,
        budget_yuan: float | None = None,
        *,
        now: datetime | None = None,
        pull_index: int = 1,
    ) -> PullResult:
        """单抽。"""
        banner = self.config.require(banner_key)
        now = now or await self.source.now_time()
        if not banner.is_available(now):
            window = ""
            if banner.time_window:
                window = f"，限时 {banner.time_window[0]:02d}:00-{banner.time_window[1]:02d}:00 开放"
            raise GachaError(
                f"卡池「{banner.name}」当前未开放{window}（当前时间 {now:%H:%M}）"
            )

        budget_cents = (
            yuan(budget_yuan) if budget_yuan is not None else banner.default_budget_cents
        )
        # 预算下限保护：低于卡池定位时抬到卡池下限
        budget_cents = max(budget_cents, banner.budget_min_cents)

        meals = await self._get_menu()
        coupons = await self._get_coupons()

        rarity = self._roll_rarity(banner)

        # 生成 → 核价 验证循环：
        # 真实模式下商品可能售罄、或核价口径偏差导致超预算，此时重新生成（最多 4 次尝试）。
        # 注意：稀有度已在此前锁定，重试不改变本发稀有度（保底语义不受影响）。
        combo: Combo | None = None
        quote = None
        max_attempts = 4
        for _attempt in range(max_attempts):
            candidate = self._dispatch_generate(rarity, meals, coupons, banner, budget_cents)
            # 保护性降级：SSR 生成失败时退回 SR（保证保底发一定出货）
            if candidate is None and rarity is Rarity.SSR:
                candidate = self._dispatch_generate(
                    Rarity.SR, meals, coupons, banner, budget_cents
                )
                if candidate is not None:
                    # 保底发的文案保留「金」感
                    candidate.flavor = self.rng.choice(FLAVOR_POOL[Rarity.SSR])
            if candidate is None:
                continue
            try:
                candidate_quote = await self.source.calculate_price(candidate.lines)
            except Exception:  # noqa: BLE001 —— 售罄/接口瞬时错误 → 重新生成
                continue
            if candidate_quote.paid_cents <= budget_cents:
                combo = candidate
                quote = candidate_quote
                break

        if combo is None or quote is None:
            raise GachaError(
                "多次尝试后仍无法生成预算内的可用组合（可能受商品售罄影响），请稍后再试。"
            )

        nutrition = await self._aggregate_nutrition(combo.lines)

        # 状态更新与持久化
        self._update_pity(banner, rarity)
        today = now.date().isoformat()
        self.state.bump_daily(today)
        self.state.record_stats(rarity.value)
        self.state.history.append(
            {
                "ts": now.isoformat(),
                "banner": banner.key,
                "rarity": rarity.value,
                "paid": quote.paid_cents,
                "saved": quote.discount_cents,
                "items": [line.meal.code for line in combo.lines],
            }
        )
        # 保存最近一次结果（供「重铸」使用）
        self.state.last_result = {
            "ts": now.isoformat(),
            "banner_key": banner.key,
            "rarity": rarity.value,
            "budget_cents": budget_cents,
            "pull_index": pull_index,
            "items": [{"code": line.meal.code, "qty": line.qty} for line in combo.lines],
            # 记录数据来源：下单命令据此判断该组合是否为真实 SKU（mock 无法下单）
            "data_source": self.source.mode,
        }
        if self.persist_state:
            save_state(self.state, self.state_path)

        return PullResult(
            rarity=rarity,
            banner_key=banner.key,
            banner_name=banner.name,
            lines=combo.lines,
            quote=quote,
            flavor=combo.flavor,
            nutrition=nutrition,
            ts=now,
            pity_after=self.state.pity_for(banner.key),
            pull_index=pull_index,
            data_source=self.source.mode,
        )

    async def ten_pull(
        self,
        banner_key: str,
        budget_yuan: float | None = None,
        *,
        now: datetime | None = None,
    ) -> list[PullResult]:
        """十连：顺序 10 次单抽，共享保底计数器。"""
        now = now or await self.source.now_time()
        results: list[PullResult] = []
        for index in range(1, 11):
            results.append(
                await self.roll(banner_key, budget_yuan, now=now, pull_index=index)
            )
        return results

    async def reroll(self, slot: int, *, now: datetime | None = None) -> PullResult:
        """重铸：替换上次抽卡结果中的第 slot 件商品（1 起）。

        规则（二游风味）：
        - 替换商品与原件同品类，且替换后组合仍在预算内；
        - 优先「升级或平价」替换，其次「降价」替换（不出现明显降级，除非别无选择）；
        - **不消耗保底进度、不改变稀有度**——重铸是"工艺"，不是抽卡。
        """
        last = self.state.last_result
        if not last:
            raise GachaError("还没有可重铸的结果——先抽一发（mcd-gacha pull）吧。")
        raw_items = last.get("items") or []
        if not (1 <= slot <= len(raw_items)):
            raise GachaError(
                f"槽位超出范围：当前组合共 {len(raw_items)} 件，有效槽位 1-{len(raw_items)}。"
            )

        banner = self.config.require(last["banner_key"])
        budget_cents = int(last.get("budget_cents") or banner.default_budget_cents)
        rarity = Rarity(last["rarity"])
        now = now or await self.source.now_time()

        meals = await self._get_menu()
        coupons = await self._get_coupons()
        meal_by_code = {meal.code: meal for meal in meals}

        # 重建当前组合
        current_lines: list[LineItem] = []
        for item in raw_items:
            meal = meal_by_code.get(str(item.get("code")))
            if meal is None:
                raise GachaError("上一次的组合已不在当前菜单中（可能已下架），请重新抽卡。")
            current_lines.append(LineItem(meal=meal, qty=int(item.get("qty", 1))))
        target = current_lines[slot - 1]

        # 候选池：同品类、不与组合内已有商品重复
        used_codes = {line.meal.code for line in current_lines}
        pool = [
            meal
            for meal in meals
            if meal.category == target.meal.category and meal.code not in used_codes
        ]
        if not pool:
            raise GachaError(f"「{target.meal.name}」同品类下没有其他可替换的商品。")

        # 优先升级/平价替换，其次降价替换
        upgrade = [meal for meal in pool if meal.price_cents >= target.meal.price_cents]
        downgrade = [meal for meal in pool if meal.price_cents < target.meal.price_cents]

        replacement: Meal | None = None
        new_lines_final: list[LineItem] = list(current_lines)
        new_quote = None
        # 真实模式下 external 券的减免额未知，本地筛保留余量，最终由核价裁决
        has_external_coupon = any(c.type == "external" for c in coupons)
        for batch in (upgrade, downgrade):
            self.rng.shuffle(batch)
            for candidate in batch:
                new_lines = list(current_lines)
                new_lines[slot - 1] = LineItem(meal=candidate, qty=target.qty)
                # 本地筛：券后实付（mock 精确；含未知额外部券时放宽余量）
                allowance = budget_cents + (1000 if has_external_coupon else 0)
                if compute_price(new_lines, coupons).paid_cents > allowance:
                    continue
                try:
                    quote = await self.source.calculate_price(new_lines)
                except Exception:  # noqa: BLE001 —— 售罄/接口瞬时错误 → 试下一个
                    continue
                if quote.paid_cents <= budget_cents:
                    replacement = candidate
                    new_lines_final = new_lines
                    new_quote = quote
                    break
            if replacement is not None:
                break

        if replacement is None or new_quote is None:
            raise GachaError(
                f"重铸失败：当前预算（¥{budget_cents / 100:.0f}）下没有可用的同品类替换商品。"
            )

        nutrition = await self._aggregate_nutrition(new_lines_final)
        result = PullResult(
            rarity=rarity,  # 稀有度锁定：重铸不改变卡面
            banner_key=banner.key,
            banner_name=banner.name,
            lines=new_lines_final,
            quote=new_quote,
            flavor=self.rng.choice(REROLL_FLAVORS),
            nutrition=nutrition,
            ts=now,
            pity_after=self.state.pity_for(banner.key),  # 保底进度不受影响
            pull_index=int(last.get("pull_index", 1)),
            data_source=self.source.mode,
        )

        # 更新状态：last_result 指向新组合，历史追加重铸记录
        self.state.last_result = {
            "ts": now.isoformat(),
            "banner_key": banner.key,
            "rarity": rarity.value,
            "budget_cents": budget_cents,
            "pull_index": result.pull_index,
            "items": [{"code": line.meal.code, "qty": line.qty} for line in new_lines_final],
            "data_source": self.source.mode,
        }
        self.state.history.append(
            {
                "ts": now.isoformat(),
                "type": "reroll",
                "slot": slot,
                "banner": banner.key,
                "rarity": rarity.value,
                "paid": new_quote.paid_cents,
                "saved": new_quote.discount_cents,
                "items": [line.meal.code for line in new_lines_final],
            }
        )
        if self.persist_state:
            save_state(self.state, self.state_path)

        return result

    # ------------------------------------------------------------------
    # 概率自证（蒙特卡洛）
    # ------------------------------------------------------------------

    def simulate(
        self,
        times: int = 100_000,
        *,
        seed: int | None = None,
    ) -> dict:
        """纯概率层蒙特卡洛：验证稀有度分布与保底行为（不触碰持久化状态）。"""
        rng = random.Random(seed)
        hard_pity = self.config.hard_pity
        counts = {name: 0 for name in _RARITY_ORDER}
        pity = 0
        gaps: list[int] = []
        current_gap = 0
        pity_triggers = 0
        max_gap = 0

        for _ in range(times):
            current_gap += 1
            if pity >= hard_pity - 1:
                rarity = Rarity.SSR
                pity_triggers += 1
            else:
                rarity = self._weighted_roll(rng, self.config.rarity_weights)
            counts[rarity.value] += 1
            if rarity is Rarity.SSR:
                gaps.append(current_gap)
                max_gap = max(max_gap, current_gap)
                current_gap = 0
                pity = 0
            else:
                pity += 1

        return {
            "times": times,
            "counts": counts,
            "rates": {name: counts[name] / times for name in _RARITY_ORDER},
            "ssr_avg_gap": mean(gaps) if gaps else 0.0,
            "ssr_max_gap": max_gap,
            "ssr_total": len(gaps),
            "pity_triggers": pity_triggers,
            "hard_pity": hard_pity,
        }

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    async def _get_menu(self) -> list[Meal]:
        if self._menu_cache is None:
            self._menu_cache = await self.source.query_meals()
        return self._menu_cache

    async def _get_coupons(self) -> list[Coupon]:
        if self._coupon_cache is None:
            self._coupon_cache = await self.source.list_coupons()
        return self._coupon_cache

    def _dispatch_generate(
        self,
        rarity: Rarity,
        meals: list[Meal],
        coupons: list[Coupon],
        banner: Banner,
        budget_cents: int,
    ) -> Combo | None:
        """按稀有度取候选（带缓存）并做软加权随机选取。"""
        scored = self._get_scored(rarity, meals, coupons, banner, budget_cents)
        return pick_combo(scored, self.rng, rarity)

    def _get_scored(
        self,
        rarity: Rarity,
        meals: list[Meal],
        coupons: list[Coupon],
        banner: Banner,
        budget_cents: int,
    ) -> list[tuple[float, list[LineItem]]]:
        """候选收集（确定性）+ 会话级缓存：十连只做一次枚举。"""
        key = (rarity.value, banner.key, budget_cents)
        scored = self._scored_cache.get(key)
        if scored is None:
            collector = COLLECTORS[rarity]
            scored = collector(meals, coupons, banner, budget_cents)
            self._scored_cache[key] = scored
        return scored

    async def _aggregate_nutrition(self, lines: list[LineItem]) -> Nutrition | None:
        codes = [line.meal.code for line in lines]
        per_item = await self.source.list_nutrition(codes)
        if not per_item:
            return None

        total = Nutrition()
        has_any = False
        for line in lines:
            single = per_item.get(line.meal.code)
            if single is None:
                continue
            has_any = True
            if single.energy_kcal is not None:
                total.energy_kcal = (total.energy_kcal or 0) + single.energy_kcal * line.qty
            for field_name in ("protein_g", "fat_g", "carb_g", "sodium_mg"):
                value = getattr(single, field_name)
                if value is not None:
                    current = getattr(total, field_name) or 0.0
                    setattr(total, field_name, current + value * line.qty)
        return total if has_any else None

    async def close(self) -> None:
        await self.source.close()
