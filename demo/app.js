/**
 * app.js — 网页演示交互逻辑（抽卡动画 / 保底持久化 / 十连网格 / 分享）。
 */

import { GachaEngine, RARITY_LABELS, formatPrice } from "./gacha.js";
import { loadData } from "./data-loader.js";

const PITY_KEY = "mcd-gacha-pity";

const state = {
  banner: "poor_standard",
  pity: {},
  busy: false,
  data: null,
  engine: null,
};

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function toast(message, ms = 2200) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), ms);
}

// ---------------------------------------------------------------------------
// 初始化
// ---------------------------------------------------------------------------

async function init() {
  try {
    state.data = await loadData();
  } catch (err) {
    toast("数据加载失败，请刷新重试");
    console.error(err);
    return;
  }
  state.engine = new GachaEngine({
    menu: state.data.menu,
    banners: state.data.banners,
    coupons: state.data.coupons,
  });
  try {
    state.pity = JSON.parse(localStorage.getItem(PITY_KEY) || "{}");
  } catch {
    state.pity = {};
  }
  renderTabs();
  updatePity();
  bindEvents();
  // 每 60 秒刷新卡池开放状态（深夜池跨时段）
  setInterval(renderTabs, 60_000);
}

function bindEvents() {
  $("pullBtn").addEventListener("click", () => pull(false));
  $("tenBtn").addEventListener("click", () => pull(true));
  $("copyCmd").addEventListener("click", async () => {
    const cmd =
      "uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha pull";
    try {
      await navigator.clipboard.writeText(cmd);
      toast("📋 安装命令已复制，去终端开抽！");
    } catch {
      toast(cmd, 5000);
    }
  });
}

// ---------------------------------------------------------------------------
// 卡池与保底
// ---------------------------------------------------------------------------

function renderTabs() {
  const el = $("bannerTabs");
  el.innerHTML = "";
  for (const banner of state.data.banners) {
    const open = state.engine.isBannerOpen(banner);
    const btn = document.createElement("button");
    btn.className =
      "banner-tab" +
      (banner.key === state.banner ? " active" : "") +
      (open ? "" : " locked");
    const shortName = banner.name.split(" · ")[0];
    btn.innerHTML = `
      <span class="b-name">${banner.emoji} ${shortName}</span>
      <span class="b-range">¥${banner.budgetMinCents / 100}–${banner.budgetMaxCents / 100}</span>
      <span class="b-state">${open ? "✅ 开放中" : "⏰ 21:00–04:00"}</span>`;
    btn.addEventListener("click", () => {
      state.banner = banner.key;
      renderTabs();
      updatePity();
    });
    el.appendChild(btn);
  }
}

function updatePity() {
  const count = state.pity[state.banner] || 0;
  const bar = $("pityBar");
  bar.innerHTML = "";
  for (let i = 0; i < 10; i++) {
    const block = document.createElement("div");
    block.className = "pity-block" + (i < count ? " filled" : "");
    bar.appendChild(block);
  }
  $("pityCount").textContent = `${count}/10`;
}

function savePity() {
  try {
    localStorage.setItem(PITY_KEY, JSON.stringify(state.pity));
  } catch {
    /* 隐私模式等场景静默失败 */
  }
}

// ---------------------------------------------------------------------------
// 抽卡
// ---------------------------------------------------------------------------

async function pull(ten) {
  if (state.busy) return;
  const banner = state.engine.getBanner(state.banner);
  if (!state.engine.isBannerOpen(banner)) {
    toast("⏰ 深夜玄学池 21:00–04:00 限时开放");
    return;
  }
  state.busy = true;
  setButtonsDisabled(true);

  const budget = banner.defaultBudgetCents;
  let pity = state.pity[state.banner] || 0;

  if (!ten) {
    const result = state.engine.pull(state.banner, budget, pity);
    await playSingle(result);
    state.pity[state.banner] = result.pityAfter;
  } else {
    const results = [];
    for (let i = 0; i < 10; i++) {
      const r = state.engine.pull(state.banner, budget, pity);
      pity = r.pityAfter;
      results.push(r);
    }
    state.pity[state.banner] = pity;
    await playTen(results);
  }

  savePity();
  updatePity();
  state.busy = false;
  setButtonsDisabled(false);
}

function setButtonsDisabled(disabled) {
  $("pullBtn").disabled = disabled;
  $("tenBtn").disabled = disabled;
}

// ---------------------------------------------------------------------------
// 动画
// ---------------------------------------------------------------------------

async function playSingle(result) {
  // 切换到单卡模式
  $("cardSlot").style.display = "";
  $("tenGrid").classList.remove("show");

  const slot = $("cardSlot");
  slot.classList.remove("flipped");
  renderCardFace(result);

  // 卡背抖动（开抽中）
  slot.classList.add("drawing");
  await sleep(680);
  slot.classList.remove("drawing");

  // SSR 金色传说横幅
  if (result.rarity === "SSR") {
    const bannerEl = $("ssrBanner");
    bannerEl.classList.add("show");
    await sleep(650);
    bannerEl.classList.remove("show");
  }

  slot.classList.add("flipped");
  await sleep(420);
}

async function playTen(results) {
  $("cardSlot").style.display = "none";
  $("cardSlot").classList.remove("flipped");
  const grid = $("tenGrid");
  grid.innerHTML = "";
  grid.classList.add("show");

  const cards = results.map((r) => {
    const card = document.createElement("div");
    card.className = `tg-card t-${r.rarity}`;
    const combo = r.lines
      .map((l) => l.meal.name + (l.qty > 1 ? `×${l.qty}` : ""))
      .join(" + ");
    const q = r.quote;
    card.innerHTML = `
      <div class="tg-rarity">${r.rarity} · ${r.lines.length} 件</div>
      <div class="tg-items">${combo}</div>
      <div class="tg-paid">¥${formatPrice(q.paidCents)}${q.discountCents > 0 ? `（省 ¥${formatPrice(q.discountCents)}）` : ""}</div>`;
    grid.appendChild(card);
    return card;
  });

  for (const card of cards) {
    card.classList.add("in");
    await sleep(135);
  }

  if (results.some((r) => r.rarity === "SSR")) {
    const bannerEl = $("ssrBanner");
    bannerEl.classList.add("show");
    await sleep(700);
    bannerEl.classList.remove("show");
  }
}

function renderCardFace(r) {
  const face = $("cardFace");
  face.className = `card-face r-${r.rarity}`;

  const banner = state.engine.getBanner(r.bannerKey);
  const items = r.lines
    .map(
      (l) => `
      <div class="rc-item">
        <span>${l.meal.name}${l.qty > 1 ? ` ×${l.qty}` : ""}</span>
        <span class="price">¥${formatPrice(l.meal.priceCents)}</span>
      </div>`
    )
    .join("");

  const q = r.quote;
  const calories = r.lines.reduce(
    (acc, l) => acc + (l.meal.calories ?? 0) * l.qty,
    0
  );
  const priceLine =
    q.discountCents > 0
      ? `原价 ¥${formatPrice(q.originalCents)} → ${q.couponName} · <span class="rc-saved">省 ¥${formatPrice(q.discountCents)}</span>`
      : "本单无可用券";

  face.innerHTML = `
    <div class="rc-head">
      <div class="rc-rarity">★ ${r.rarity} ★</div>
      <div class="rc-label">${RARITY_LABELS[r.rarity]}</div>
      <div class="rc-banner">${banner.name}</div>
    </div>
    <div class="rc-items">${items}</div>
    <div class="rc-price">
      <div class="rc-paid">¥${formatPrice(q.paidCents)}</div>
      <div class="rc-original">${priceLine}</div>
    </div>
    <div class="rc-extra">
      <span>${calories > 0 ? `🔥 ${calories} kcal` : ""}</span>
      <span>再抽 ${10 - r.pityAfter} 发必出金</span>
    </div>
    <div class="rc-flavor">「${r.flavor}」</div>`;
}

init();
