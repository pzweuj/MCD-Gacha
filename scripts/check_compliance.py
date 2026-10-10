"""合规自检：扫描仓库中的禁用词。

配合 docs/compliance.md 使用；CI 与本地均可运行：
    python scripts/check_compliance.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcd_gacha.i18n import BANNED_WORDS  # noqa: E402

SCAN_GLOBS = ("*.md", "*.py", "*.json", "*.yml", "*.yaml", "*.html", "*.js", "*.toml")
SKIP_DIRS = {
    ".venv",
    ".git",
    ".workbuddy",  # 本地智能体工作数据（不属于仓库内容）
    ".tmp-probe",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
}
# 词表定义文件自身包含禁用词，跳过
SKIP_FILES = {"i18n.py", "check_compliance.py"}


def iter_files():
    for pattern in SCAN_GLOBS:
        for path in ROOT.rglob(pattern):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.name in SKIP_FILES:
                continue
            yield path


def main() -> int:
    violations: list[tuple[Path, str]] = []
    for path in iter_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for word in BANNED_WORDS:
            if word in text:
                violations.append((path, word))

    if violations:
        print("❌ 合规自检未通过，以下位置含禁用词：")
        for path, word in violations:
            print(f"  [{word}] {path.relative_to(ROOT)}")
        print("\n请参考 src/mcd_gacha/i18n.py 的 REPLACEMENTS 进行柔化替换。")
        return 1

    print("✅ 合规自检通过：未发现禁用词。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
