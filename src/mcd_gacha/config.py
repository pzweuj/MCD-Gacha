"""路径与本地配置（token / 门店等）。

Token 查找优先级：环境变量 MCD_MCP_TOKEN > 当前目录 .env > 本地 config.toml。
门店查找优先级：环境变量 MCD_STORE_CODE / MCD_CITY > 当前目录 .env > config.toml。

凭据只会写入本地配置目录（platformdirs）或用户自己的 .env，绝不进入版本库。
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import platformdirs

APP_NAME = "mcd-gacha"
ENV_TOKEN = "MCD_MCP_TOKEN"
ENV_STORE_CODE = "MCD_STORE_CODE"
ENV_CITY = "MCD_CITY"
ENV_HOME = "MCD_GACHA_HOME"


def get_config_dir() -> Path:
    """本地配置目录（MCD_GACHA_HOME 可覆盖，便于测试与隔离）。

    注意：不使用 platformdirs.user_config_dir(appname)（Windows 下会产生
    appauthor/appname 双层目录），统一用平台根目录 + APP_NAME。
    """
    override = os.environ.get(ENV_HOME, "").strip()
    base = (
        Path(override)
        if override
        else Path(platformdirs.user_config_dir()) / APP_NAME
    )
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_config_file() -> Path:
    return get_config_dir() / "config.toml"


def get_state_file() -> Path:
    return get_config_dir() / "state.json"


def get_cache_dir() -> Path:
    path = get_config_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_config(path: Path) -> dict[str, str]:
    """极简 TOML 子集解析（flat key = "value"），避免额外依赖。"""
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _read_dotenv() -> dict[str, str]:
    """读取当前工作目录的 .env 文件（KEY=VALUE 行）。"""
    return _read_config(Path.cwd() / ".env")


def get_token_with_source() -> tuple[str | None, str]:
    """获取 MCP Token 及其来源描述（用于 doctor 自检）。"""
    env_token = os.environ.get(ENV_TOKEN, "").strip()
    if env_token:
        return env_token, f"环境变量 {ENV_TOKEN}"
    dotenv_token = _read_dotenv().get(ENV_TOKEN, "").strip()
    if dotenv_token:
        return dotenv_token, f".env 文件（{Path.cwd() / '.env'}）"
    token = _read_config(get_config_file()).get("token", "").strip()
    if token:
        return token, f"本地配置（{get_config_file()}）"
    return None, "未找到"


def get_token() -> str | None:
    """获取 MCP Token：环境变量优先，其次当前目录 .env，最后本地配置。"""
    return get_token_with_source()[0]


def get_store_settings() -> tuple[str | None, str | None]:
    """获取门店设置：(store_code, city)。按 环境变量 > .env > config.toml 合并。"""
    dotenv = _read_dotenv()
    config = _read_config(get_config_file())

    def pick(env_key: str, config_key: str) -> str | None:
        for candidate in (
            os.environ.get(env_key, ""),
            dotenv.get(env_key, ""),
            config.get(config_key, ""),
        ):
            value = candidate.strip()
            if value:
                return value
        return None

    return pick(ENV_STORE_CODE, "store_code"), pick(ENV_CITY, "city")


def save_token(token: str) -> Path:
    """将 Token 写入本地配置（尽量收紧文件权限，POSIX 下 0600）。"""
    return _write_config({"token": token})


def save_store_settings(store_code: str | None = None, city: str | None = None) -> Path:
    """保存门店设置（与 token 合并写入，旧值保留）。"""
    updates: dict[str, str] = {}
    if store_code:
        updates["store_code"] = store_code
    if city:
        updates["city"] = city
    if not updates:
        raise ValueError("至少需要提供 store_code 或 city")
    return _write_config(updates)


def _write_config(updates: dict[str, str]) -> Path:
    """合并写入本地 config.toml（保留现有键值）。"""
    path = get_config_file()
    current = _read_config(path)
    current.update(updates)
    lines = ["# Mcd-Gacha 本地配置（请勿提交到版本库）", "# 也可改用环境变量提供（MCD_MCP_TOKEN / MCD_STORE_CODE / MCD_CITY）"]
    for key, value in current.items():
        lines.append(f'{key} = "{value}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):  # Windows 上 chmod 语义有限，忽略
        os.chmod(path, 0o600)
    return path


def mask_token(token: str | None) -> str:
    """脱敏展示 Token。"""
    if not token:
        return "（未配置）"
    if len(token) <= 8:
        return token[0] + "***"
    return f"{token[:4]}****{token[-4:]}"
