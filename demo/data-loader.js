/**
 * data-loader.js — 数据加载与格式转换。
 *
 * 纯转换函数（供测试与浏览器共用）：
 *   mock json（元 / snake 字段）→ 引擎格式（分 / camelCase）
 */

export function convertMenu(rawMenu) {
  return (rawMenu.items || []).map((item) => ({
    code: String(item.code),
    name: item.name,
    category: item.category,
    priceCents: Math.round(Number(item.price) * 100),
    tags: item.tags || [],
    calories: item.calories ?? null,
  }));
}

export function convertBanners(rawConfig) {
  return (rawConfig.banners || []).map((b) => ({
    key: b.key,
    name: b.name,
    emoji: b.emoji,
    budgetMinCents: Math.round(b.budget_min * 100),
    budgetMaxCents: Math.round(b.budget_max * 100),
    defaultBudgetCents: Math.round((b.default_budget ?? b.budget_max) * 100),
    requireTags: b.require_tags || [],
    preferTags: b.prefer_tags || [],
    timeWindow: b.time_window || null,
    desc: b.desc || "",
  }));
}

export function convertCoupons(rawPrices) {
  return (rawPrices.coupons || []).map((c) => ({
    id: c.id,
    name: c.name,
    type: c.type,
    amountCents: Math.round(Number(c.amount) * 100),
    thresholdCents: c.threshold ? Math.round(Number(c.threshold) * 100) : null,
    itemCode: c.item_code || null,
  }));
}

/** 浏览器环境：从 data/ 目录加载全部数据。 */
export async function loadData(baseUrl = "./data/") {
  const [menuRaw, bannersRaw, pricesRaw] = await Promise.all([
    fetch(`${baseUrl}mock_menu.json`).then((r) => r.json()),
    fetch(`${baseUrl}banners.json`).then((r) => r.json()),
    fetch(`${baseUrl}mock_prices.json`).then((r) => r.json()),
  ]);
  return {
    menu: convertMenu(menuRaw),
    banners: convertBanners(bannersRaw),
    coupons: convertCoupons(pricesRaw),
    hardPity: bannersRaw.hard_pity || 10,
    weights: bannersRaw.rarity_weights,
    snapshotNote: menuRaw.snapshot_note || "",
  };
}
