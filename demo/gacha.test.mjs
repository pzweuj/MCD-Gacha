/**
 * gacha.test.mjs — 网页版引擎测试（node --test demo/gacha.test.mjs）
 *
 * 覆盖：数据加载转换、概率分布、保底不变量、预算约束、SSR 近优带多样性。
 */

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { GachaEngine, makeRng, computePrice, RARITY_WEIGHTS, HARD_PITY } from "./gacha.js";
import { convertMenu, convertBanners, convertCoupons } from "./data-loader.js";

const HERE = dirname(fileURLToPath(import.meta.url));

function loadFixtures() {
  const menu = convertMenu(JSON.parse(readFileSync(join(HERE, "data/mock_menu.json"), "utf-8")));
  const banners = convertBanners(JSON.parse(readFileSync(join(HERE, "data/banners.json"), "utf-8")));
  const coupons = convertCoupons(JSON.parse(readFileSync(join(HERE, "data/mock_prices.json"), "utf-8")));
  return { menu, banners, coupons };
}

function makeEngine(seed = 42) {
  return new GachaEngine({ ...loadFixtures(), rng: makeRng(seed) });
}

test("数据转换：菜单/卡池/券字段齐全", () => {
  const { menu, banners, coupons } = loadFixtures();
  assert.ok(menu.length >= 40, `菜单数量异常: ${menu.length}`);
  assert.equal(banners.length, 3);
  assert.ok(coupons.length >= 3);
  for (const m of menu) {
    assert.ok(m.priceCents > 0, `${m.name} 价格无效`);
    assert.ok(Array.isArray(m.tags));
  }
});

test("稀有度权重与保底常量与 Python 版一致", () => {
  assert.deepEqual(RARITY_WEIGHTS, { SSR: 5, SR: 25, R: 60, N: 10 });
  assert.equal(HARD_PITY, 10);
});

test("保底：pity>=9 时下一发必出 SSR", () => {
  const engine = makeEngine(1);
  const result = engine.pull("poor_standard", 1500, 9);
  assert.equal(result.rarity, "SSR");
  assert.equal(result.pityAfter, 0);
});

test("保底不变量：任意 10 连内必有 SSR", () => {
  const engine = makeEngine(7);
  let pity = 0;
  const rarities = [];
  for (let i = 0; i < 60; i++) {
    const r = engine.pull("worker_up", 3500, pity);
    pity = r.pityAfter;
    rarities.push(r.rarity);
  }
  for (let start = 0; start + 10 <= rarities.length; start++) {
    assert.ok(
      rarities.slice(start, start + 10).includes("SSR"),
      `窗口 [${start}, ${start + 9}] 内无 SSR`
    );
  }
});

test("预算约束：所有抽卡结果券后实付 ≤ 预算", () => {
  const { menu, banners, coupons } = loadFixtures();
  const engine = new GachaEngine({ menu, banners, coupons, rng: makeRng(99) });
  for (const bannerKey of ["poor_standard", "worker_up", "midnight"]) {
    const banner = engine.getBanner(bannerKey);
    const budget = banner.defaultBudgetCents;
    for (let i = 0; i < 40; i++) {
      const r = engine.pull(bannerKey, budget, i % 10);
      assert.ok(
        r.quote.paidCents <= budget,
        `${bannerKey} 超预算: ${r.quote.paidCents} > ${budget}`
      );
      assert.ok(r.lines.length > 0);
    }
  }
});

test("SSR 近优带多样性：多次生成出现多种组合", () => {
  const engine = makeEngine(2026);
  const seen = new Set();
  for (let i = 0; i < 30; i++) {
    const r = engine.pull("worker_up", 3500, 9); // 强制 SSR
    seen.add(r.lines.map((l) => l.meal.code).sort().join("+"));
  }
  assert.ok(seen.size >= 3, `SSR 组合种类过少: ${seen.size}`);
});

test("深夜池时段判断", () => {
  const engine = makeEngine();
  const banner = engine.getBanner("midnight");
  assert.equal(engine.isBannerOpen(banner, new Date("2026-10-10T23:00:00")), true);
  assert.equal(engine.isBannerOpen(banner, new Date("2026-10-10T03:00:00")), true);
  assert.equal(engine.isBannerOpen(banner, new Date("2026-10-10T15:00:00")), false);
});

test("价格计算：单券最优", () => {
  const { coupons } = loadFixtures();
  const meal = (price) => ({ code: "X", name: "X", category: "burger", priceCents: price, tags: [] });
  const lines = [{ meal: meal(3000), qty: 1 }];
  const quote = computePrice(lines, coupons);
  // 满 30 减 6 优于满 25 减 4
  assert.equal(quote.paidCents, 2400);
  assert.equal(quote.couponName, "满 30 减 6");
});
