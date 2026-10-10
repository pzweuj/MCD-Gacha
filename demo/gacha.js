/**
 * gacha.js — Mcd-Gacha 网页版抽卡引擎
 *
 * 与 Python 版（src/mcd_gacha）规则保持一致：
 *   - 稀有度权重 SSR 5 / SR 25 / R 60 / N 10，10 发硬保底（每卡池独立）
 *   - 四档生成策略：R=规整 / SR=经典正餐 / SSR=预算内价值最大化 / N=抽象整活
 *   - 金额全程用「分」（整数）；单券最优（满减 / 单品券）
 *   - 预算约束：券后实付 ≤ 预算
 *
 * 纯逻辑、零依赖、可测试（node --test demo/gacha.test.mjs）。
 */

export const RARITY_WEIGHTS = { SSR: 5, SR: 25, R: 60, N: 10 };
export const HARD_PITY = 10;
export const MAX_ITEMS = 3;

export const RARITY_LABELS = {
  SSR: "金卡 · 欧皇时刻",
  SR: "紫卡 · 稳稳的幸福",
  R: "蓝卡 · 经典保底",
  N: "隐藏灰卡 · 抽象艺术",
};

export const FLAVOR_POOL = {
  SSR: [
    "欧皇时刻！这套价格，连店员都想拍照。",
    "金光一闪：传说级性价比，今日手气在线。",
    "这就是金色传说吗？券后价格太能打了。",
  ],
  SR: [
    "紫气东来：经典组合，稳稳的幸福。",
    "熟悉的味道，闭眼冲不踩雷。",
    "稳定发挥：没有惊喜，只有好吃。",
  ],
  R: [
    "蓝光普照：规矩的一顿，能量满格。",
    "中规中矩的快乐，干饭人的日常。",
    "经典搭配回归：吃饱最重要。",
  ],
  N: [
    "抽象艺术大师：这套搭配有点想法，但不多。",
    "隐藏款！菜单看了都沉默了一下。",
    "搭配鬼才：每一分钱都精确到分毫。",
  ],
};

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------

export function yuanToCents(value) {
  return Math.round(Number(value) * 100);
}

export function formatPrice(cents) {
  const s = (cents / 100).toFixed(2);
  return s.replace(/\.?0+$/, "");
}

/** 可复现随机数（mulberry32）；不传 seed 用 Math.random。 */
export function makeRng(seed) {
  if (seed === undefined || seed === null) return Math.random;
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------------------------
// 价格计算（单券最优，与 Python optimizer.compute_price 一致）
// ---------------------------------------------------------------------------

function couponDiscount(coupon, lines, subtotal) {
  if (coupon.type === "threshold") {
    const threshold = coupon.thresholdCents ?? 0;
    return subtotal >= threshold && threshold > 0 ? coupon.amountCents : 0;
  }
  if (coupon.type === "item") {
    return lines.some((l) => l.meal.code === coupon.itemCode) ? coupon.amountCents : 0;
  }
  return 0;
}

export function computePrice(lines, coupons) {
  const subtotal = lines.reduce((acc, l) => acc + l.meal.priceCents * l.qty, 0);
  let bestDiscount = 0;
  let bestCoupon = null;
  for (const coupon of coupons) {
    const discount = couponDiscount(coupon, lines, subtotal);
    if (discount > bestDiscount) {
      bestDiscount = discount;
      bestCoupon = coupon;
    }
  }
  return {
    originalCents: subtotal,
    discountCents: bestDiscount,
    paidCents: Math.max(0, subtotal - bestDiscount),
    couponName: bestCoupon ? bestCoupon.name : null,
  };
}

// ---------------------------------------------------------------------------
// 组合枚举（价格升序 + 超预算剪枝，与 Python _iter_combos 一致）
// ---------------------------------------------------------------------------

function buildPool(menu, budgetCents) {
  return menu.filter((m) => m.priceCents > 0 && m.priceCents <= budgetCents);
}

function* iterCombos(pool, budgetCents, maxK, allowRepeat) {
  const items = [...pool].sort((a, b) => a.priceCents - b.priceCents);
  const n = items.length;

  function* rec(start, k, prefix, prefixSum) {
    for (let i = start; i < n; i++) {
      const total = prefixSum + items[i].priceCents;
      if (total > budgetCents) break; // 升序剪枝
      const combo = [...prefix, items[i]];
      if (k === 1) {
        yield combo;
      } else {
        yield* rec(allowRepeat ? i : i + 1, k - 1, combo, total);
      }
    }
  }

  for (let k = 1; k <= maxK; k++) {
    yield* rec(0, k, [], 0);
  }
}

// ---------------------------------------------------------------------------
// 评分辅助
// ---------------------------------------------------------------------------

const subtotalOf = (lines) => lines.reduce((acc, l) => acc + l.meal.priceCents * l.qty, 0);
const tagsOf = (lines) => new Set(lines.flatMap((l) => l.meal.tags));
const catsOf = (lines) => new Set(lines.map((l) => l.meal.category));

function preferBonus(tags, banner) {
  return 0.25 * (banner.preferTags || []).filter((t) => tags.has(t)).length;
}

// ---------------------------------------------------------------------------
// 四档收集器（返回 [(score, lines)]）
// ---------------------------------------------------------------------------

export function collectR(menu, coupons, banner, budgetCents) {
  const scored = [];
  for (const combo of iterCombos(buildPool(menu, budgetCents), budgetCents, MAX_ITEMS, false)) {
    const lines = combo.map((meal) => ({ meal, qty: 1 }));
    const subtotal = subtotalOf(lines);
    if (subtotal <= 0) continue;
    const util = subtotal / budgetCents;
    if (util < 0.5) continue;
    const tags = tagsOf(lines);
    const n = lines.length;
    let score = 0;
    if (n === 1) {
      if (util < 0.75) continue;
      score += 1.0;
    } else if (n === 2) {
      score += 1.5;
    } else {
      score += 0.5;
    }
    if (tags.has("classic")) score += 1.5;
    if (tags.has("value")) score += 1.0;
    if (tags.has("deal")) score += 1.2;
    if (tags.has("staple")) score += 1.0;
    if (util >= 0.8) score += 0.8;
    score += preferBonus(tags, banner);
    scored.push([score, lines]);
  }
  return scored;
}

export function collectSR(menu, coupons, banner, budgetCents) {
  const scored = [];
  for (const combo of iterCombos(buildPool(menu, budgetCents), budgetCents, MAX_ITEMS, false)) {
    const lines = combo.map((meal) => ({ meal, qty: 1 }));
    const subtotal = subtotalOf(lines);
    if (subtotal <= 0) continue;
    const util = subtotal / budgetCents;
    if (util < 0.7) continue;
    const tags = tagsOf(lines);
    const cats = catsOf(lines);
    const hasMain = cats.has("burger") || cats.has("deal");
    if (!hasMain) continue;
    const hasSide = cats.has("snack");
    const hasDrink = cats.has("drink") || cats.has("coffee");
    let score = 1.5;
    if (hasSide) score += 1.0;
    if (hasDrink) score += 1.0;
    if (hasSide && hasDrink) score += 1.5;
    if (tags.has("classic")) score += 1.2;
    if (tags.has("premium")) score += 0.8;
    for (const t of banner.requireTags || []) if (tags.has(t)) score += 0.6;
    if (util >= 0.8) score += 1.0;
    if (util >= 0.9) score += 0.5;
    score += preferBonus(tags, banner);
    scored.push([score, lines]);
  }
  return scored;
}

export function collectSSR(menu, coupons, banner, budgetCents) {
  const candidates = [];
  const thresholdCoupons = coupons.filter((c) => c.type === "threshold");
  const itemCoupons = coupons.filter((c) => c.type === "item");

  // 收集全部合法组合（≤3 件），逐个试券方案，选券后可行的
  for (const combo of iterCombos(buildPool(menu, budgetCents + 800), budgetCents + 800, MAX_ITEMS, false)) {
    const lines = combo.map((meal) => ({ meal, qty: 1 }));
    const quote = computePrice(lines, coupons);
    if (quote.paidCents <= budgetCents && lines.length > 0) {
      const subtotal = subtotalOf(lines);
      const hasDrink = lines.some((l) => ["drink", "coffee"].includes(l.meal.category));
      // 与 Python 一致：原价价值为主序，饮品/件数做 tie-break
      candidates.push([subtotal + (hasDrink ? 0.5 : 0) + lines.length * 0.1, lines]);
    }
  }
  // 锚点约束（如"必含 premium"）由调用方过滤后降级
  if (banner.requireTags && banner.requireTags.length > 0) {
    const anchored = candidates.filter(([, lines]) =>
      lines.some((l) => banner.requireTags.some((t) => l.meal.tags.includes(t)))
    );
    if (anchored.length > 0) return anchored;
  }
  // 去重（按组合签名）
  const seen = new Set();
  const unique = [];
  for (const item of candidates) {
    const sig = item[1].map((l) => l.meal.code).sort().join("+");
    if (seen.has(sig)) continue;
    seen.add(sig);
    unique.push(item);
  }
  return unique;
}

export function collectN(menu, coupons, banner, budgetCents) {
  const scored = [];
  for (const combo of iterCombos(buildPool(menu, budgetCents), budgetCents, MAX_ITEMS, true)) {
    const lines = combo.map((meal) => ({ meal, qty: 1 }));
    const subtotal = subtotalOf(lines);
    if (subtotal <= 0) continue;
    const util = subtotal / budgetCents;
    const tags = tagsOf(lines);
    const cats = catsOf(lines);
    const n = lines.length;
    let absurd = 0;
    if (cats.size >= 3) absurd += 2.0;
    else if (cats.size === 2) absurd += 0.5;
    if (!tags.has("staple")) absurd += 1.5;
    if (cats.size === 1 && cats.has("drink")) absurd += 2.5;
    if (cats.size === 1 && cats.has("coffee")) absurd += 2.0;
    if (cats.size === 1 && cats.has("snack")) absurd += 1.0;
    if (tags.has("coffee") && (tags.has("hot") || tags.has("side"))) absurd += 1.5;
    if (util >= 0.95) absurd += 1.5;
    if (n >= 3) absurd += 0.5;
    if (n === 1) absurd -= 1.0;
    scored.push([absurd, lines]);
  }
  return scored;
}

// ---------------------------------------------------------------------------
// 选择（SSR=近优带软加权；其余=top12 软加权）
// ---------------------------------------------------------------------------

function pick(scored, rarity, rng) {
  if (!scored || scored.length === 0) return null;
  if (rarity === "SSR") {
    const best = Math.max(...scored.map(([s]) => s));
    const band = scored.filter(([s]) => s >= best * 0.88);
    const weights = band.map(([s]) => Math.exp((s - best) / 1.2));
    const lines = weightedPick(band.map((b) => b[1]), weights, rng);
    return lines;
  }
  scored.sort((a, b) => b[0] - a[0]);
  const top = scored.slice(0, rarity === "N" ? 8 : 12);
  const max = top[0][0];
  const weights = top.map(([s]) => Math.exp(s - max));
  return weightedPick(top.map((b) => b[1]), weights, rng);
}

function weightedPick(items, weights, rng) {
  const total = weights.reduce((a, b) => a + b, 0);
  let point = rng() * total;
  for (let i = 0; i < items.length; i++) {
    point -= weights[i];
    if (point <= 0) return items[i];
  }
  return items[items.length - 1];
}

const COLLECTORS = { R: collectR, SR: collectSR, SSR: collectSSR, N: collectN };

// ---------------------------------------------------------------------------
// 引擎
// ---------------------------------------------------------------------------

export class GachaEngine {
  /**
   * @param {object} opts
   * @param {Array} opts.menu    餐品列表（priceCents/tags/category 已转换）
   * @param {Array} opts.banners 卡池配置
   * @param {Array} opts.coupons 优惠券
   * @param {function} [opts.rng] 随机函数（可注入种子）
   */
  constructor({ menu, banners, coupons, rng }) {
    this.menu = menu;
    this.banners = banners;
    this.coupons = coupons;
    this.rng = rng || Math.random;
  }

  getBanner(key) {
    return this.banners.find((b) => b.key === key) || null;
  }

  isBannerOpen(banner, now = new Date()) {
    if (!banner.timeWindow) return true;
    const [start, end] = banner.timeWindow;
    const hour = now.getHours();
    if (start <= end) return hour >= start && hour < end;
    return hour >= start || hour < end;
  }

  rollRarity(pityCount) {
    if (pityCount >= HARD_PITY - 1) return "SSR";
    const total = Object.values(RARITY_WEIGHTS).reduce((a, b) => a + b, 0);
    let point = this.rng() * total;
    for (const [name, w] of Object.entries(RARITY_WEIGHTS)) {
      point -= w;
      if (point <= 0) return name;
    }
    return "N";
  }

  /**
   * 单抽。
   * @param {string} bannerKey
   * @param {number} budgetCents
   * @param {number} pityCount 该卡池当前保底计数
   * @returns {{ rarity, lines, quote, flavor, pityAfter }}
   */
  pull(bannerKey, budgetCents, pityCount = 0) {
    const banner = this.getBanner(bannerKey);
    if (!banner) throw new Error(`未知卡池: ${bannerKey}`);

    const rarity = this.rollRarity(pityCount);
    let combo = pick(COLLECTORS[rarity](this.menu, this.coupons, banner, budgetCents), rarity, this.rng);
    // 保护性降级：SSR 无解时退回 SR 池
    if (!combo && rarity === "SSR") {
      combo = pick(collectSR(this.menu, this.coupons, banner, budgetCents), "SR", this.rng);
    }
    if (!combo) throw new Error("当前预算下无法生成组合");

    const quote = computePrice(combo, this.coupons);
    const pool = FLAVOR_POOL[rarity];
    const flavor = pool[Math.floor(this.rng() * pool.length)];
    // 保底更新：SSR 清零，否则 +1
    const pityAfter = rarity === "SSR" ? 0 : pityCount + 1;
    return { rarity, bannerKey, lines: combo, quote, flavor, pityAfter };
  }
}
