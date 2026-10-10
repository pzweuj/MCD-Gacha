"""生成 Hero 演示 GIF（零外部工具依赖，Pillow 逐帧渲染）。

渲染一个模拟终端窗口的演示动画：
  打字机命令 → 连接动画 → 命运蓄力 → 稀有度检定 → 金卡爆发 → 面板揭晓 → 定格

运行：python scripts/make_gif.py
输出：docs/assets/hero-demo.gif（并同时输出 PNG 关键帧便于检查）
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_GIF = ROOT / "docs" / "assets" / "hero-demo.gif"

# ------ 画布与配色 ------
W, H = 960, 540
BG = (22, 24, 36)
TITLE_BG = (36, 39, 56)
FG = (225, 228, 240)
DIM = (128, 132, 152)
GREEN = (86, 205, 170)
GOLD = (245, 178, 60)
GOLD_DIM = (150, 110, 40)
PANEL_BG = (38, 30, 16)
PANEL_BORDER = (245, 178, 60)
RED, YELLOW, GREEN_DOT = (255, 95, 86), (255, 189, 46), (39, 201, 63)

FONT_DIR = Path("C:/Windows/Fonts")
_font_cache: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _font_cache:
        return _font_cache[key]
    candidates = (
        "msyhbd.ttc" if bold else "msyh.ttc",
    ) + (("CascadiaCode-Bold.ttf", "consolab.ttf") if bold else ("CascadiaMono.ttf", "consola.ttf"))
    for name in candidates:
        path = FONT_DIR / name
        if path.exists():
            f = ImageFont.truetype(str(path), size)
            _font_cache[key] = f
            return f
    f = ImageFont.load_default()
    _font_cache[key] = f  # type: ignore[assignment]
    return f  # type: ignore[return-value]


def base_window(title: str = "mcd-gacha — 麦门抽卡模拟器") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # 标题栏
    d.rectangle([0, 0, W, 42], fill=TITLE_BG)
    for i, color in enumerate((RED, YELLOW, GREEN_DOT)):
        x = 24 + i * 26
        d.ellipse([x, 15, x + 12, 27], fill=color)
    d.text((W / 2, 21), title, font=font(15), fill=DIM, anchor="mm")
    return img, d


def draw_prompt(d: ImageDraw.ImageDraw, text: str, y: int = 76) -> None:
    d.text((40, y), "$", font=font(24, bold=True), fill=GREEN)
    d.text((66, y), text, font=font(24), fill=FG)


# ---------------------------------------------------------------------------
# 场景帧
# ---------------------------------------------------------------------------


def typewriter_frames(command: str) -> list[Image.Image]:
    frames = []
    for i in range(1, len(command) + 1):
        img, d = base_window()
        draw_prompt(d, command[:i])
        frames.append(img)
    return frames


def connect_frames() -> list[Image.Image]:
    frames = []
    for dots in ("", "·", "··", "···", "····"):
        img, d = base_window()
        draw_prompt(d, "mcd-gacha pull -b worker")
        d.text((66, 128), f"连接金拱门量子服务器{dots}", font=font(22), fill=DIM)
        frames.append(img)
    return frames


def charge_frames() -> list[Image.Image]:
    frames = []
    for pct in (12, 28, 45, 62, 78, 90, 100):
        img, d = base_window()
        draw_prompt(d, "mcd-gacha pull -b worker")
        d.text((66, 128), "命运蓄力中", font=font(22), fill=FG)
        # 进度条
        x0, y0, bw, bh = 210, 130, 360, 18
        d.rectangle([x0, y0, x0 + bw, y0 + bh], outline=DIM, width=2)
        filled = int(bw * pct / 100)
        if filled > 0:
            d.rectangle([x0 + 2, y0 + 2, x0 + filled, y0 + bh - 2], fill=GOLD)
        d.text((x0 + bw + 16, y0 - 2), f"{pct}%", font=font(20), fill=GOLD)
        frames.append(img)
    return frames


def flicker_frames() -> list[Image.Image]:
    frames = []
    phases = [(DIM, ""), (GOLD, ""), (DIM, ""), (GOLD, "")]
    for color, _ in phases:
        img, d = base_window()
        draw_prompt(d, "mcd-gacha pull -b worker")
        d.text((W / 2, 200), "★ ★ ★", font=font(64, bold=True), fill=color, anchor="mm")
        frames.append(img)
    return frames


def burst_frames() -> list[Image.Image]:
    frames = []
    bursts = [
        ("★ ★ ★", GOLD, 52),
        ("★ ★ ★", (255, 215, 120), 58),
        ("★ 金 色 传 说 ★", (255, 224, 130), 46),
    ]
    for text, color, size in bursts:
        img, d = base_window()
        draw_prompt(d, "mcd-gacha pull -b worker")
        d.text((W / 2, 210), text, font=font(size, bold=True), fill=color, anchor="mm")
        frames.append(img)
    return frames


# --- 结果面板（PIL 直绘，共用布局函数，逐行揭示）---

PANEL_X0, PANEL_Y0, PANEL_X1, PANEL_Y1 = 60, 118, 900, 452
RESULT_ROWS = [
    ("banner", "SSR · 金卡 · 欧皇时刻"),
    ("item", "巨无霸"),
    ("item", "薯条"),
    ("price", None),
    ("cal", None),
]


def panel_base(draw_lines: int, footer_lines: int) -> Image.Image:
    """绘制面板框 + 前 n 行内容（逐行揭示用）。"""
    img, d = base_window()
    draw_prompt(d, "mcd-gacha pull -b worker")

    # 面板框
    d.rounded_rectangle(
        [PANEL_X0, PANEL_Y0, PANEL_X1, PANEL_Y1], radius=14,
        fill=PANEL_BG, outline=PANEL_BORDER, width=3,
    )
    # 顶部铭牌
    d.rounded_rectangle([230, PANEL_Y0 - 16, 730, PANEL_Y0 + 16], radius=16, fill=BG)
    d.text((W / 2, PANEL_Y0), "━ 开 箱 ━", font=font(20, bold=True), fill=GOLD, anchor="mm")

    rows = [
        ("★ SSR · 金卡 · 欧皇时刻 ★", 22, GOLD),
        ("巨无霸", 26, FG),
        ("薯条", 26, FG),
        ("原价 ¥40.5  →  券后 ¥34.5", 26, FG),
        ("满 30 减 6 · 省 ¥6 · 总热量 890 kcal", 20, DIM),
    ]
    prices = ["¥26", "¥14.5"]
    y = PANEL_Y0 + 52
    price_idx = 0
    for shown, (text, size, color) in enumerate(rows):
        if shown >= draw_lines:
            break
        d.text((PANEL_X0 + 40, y), text, font=font(size, bold=(size == 22)), fill=color)
        if text in ("巨无霸", "薯条"):
            d.text((PANEL_X1 - 40, y), prices[price_idx], font=font(24), fill=DIM, anchor="ra")
            price_idx += 1
        y += 44 if size >= 26 else 36

    # 文案与保底（footer_lines 控制逐行出现）
    y_footer = 470
    if footer_lines >= 1:
        d.text((64, y_footer), "金光一闪：传说级性价比，今日手气在线。", font=font(20), fill=FG)
    if footer_lines >= 2:
        # 保底进度条（手绘方块，避免字体缺字）
        bx, by = 64, y_footer + 42
        d.text((bx, by), "保底进度", font=font(20), fill=DIM)
        for i in range(10):
            x = bx + 116 + i * 22
            d.rectangle([x, by + 3, x + 14, by + 17], outline=DIM, width=2)
        d.text((bx + 352, by), "0/10（再抽 10 发内必出金）", font=font(20), fill=DIM)
    return img


def panel_frames() -> list[Image.Image]:
    """面板逐行揭示 + 定格帧。"""
    frames = []
    for n in range(1, len(RESULT_ROWS) + 1):
        frames.append(panel_base(n, 0))
    frames.append(panel_base(len(RESULT_ROWS), 1))
    frames.append(panel_base(len(RESULT_ROWS), 2))
    return frames


def build_frames() -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []

    def add(batch: list[Image.Image], ms: int) -> None:
        frames.extend(batch)
        durations.extend([ms] * len(batch))

    add(typewriter_frames("mcd-gacha pull -b worker"), 55)
    add(connect_frames(), 110)
    add(charge_frames(), 85)
    add(flicker_frames(), 110)
    add(burst_frames(), 140)
    panel = panel_frames()
    add(panel[:-1], 130)
    frames.append(panel[-1])
    durations.append(2600)  # 定格
    return frames, durations


def main() -> int:
    import sys

    OUT_GIF.parent.mkdir(parents=True, exist_ok=True)
    frames, durations = build_frames()
    print(f"总帧数: {len(frames)}，总时长约 {sum(durations) / 1000:.1f} 秒")

    # --debug：导出关键帧便于检查渲染质量（调试专用，不入库）
    if "--debug" in sys.argv:
        debug_dir = ROOT / ".tmp-probe"
        debug_dir.mkdir(exist_ok=True)
        for idx in (5, 20, 28, 33, 40, len(frames) - 1):
            if idx < len(frames):
                frames[idx].save(debug_dir / f"hero-frame{idx:02d}.png")
        print(f"调试帧已导出到 {debug_dir}")

    frames[0].save(
        OUT_GIF,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )
    size_mb = OUT_GIF.stat().st_size / 1024 / 1024
    print(f"✅ 已生成: {OUT_GIF}（{size_mb:.2f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
