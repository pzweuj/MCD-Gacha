"""MCP 连接诊断工具。

用途：排查真实 MCP 模式问题（Token / 网络 / 门店解析）。
运行：python scripts/check_mcp.py [城市名]

检查项：
1. Token 是否可获取（环境变量 / .env / 本地配置）
2. 连接 https://mcp.mcd.cn 并列出工具清单
3. 门店解析（若提供城市名或已配置）
4. now-time-info 冒烟调用
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from mcd_gacha.config import get_store_settings, get_token, mask_token  # noqa: E402


async def diagnose(city: str | None = None) -> int:
    token = get_token()
    if not token:
        print("❌ 未找到 MCP Token")
        print("   请设置环境变量 MCD_MCP_TOKEN，或在项目根 .env 写入，")
        print("   或运行：mcd-gacha config set-token <TOKEN>")
        return 1
    print(f"🔑 Token: {mask_token(token)}")

    store_code, configured_city = get_store_settings()
    use_city = city or configured_city
    print(f"🏪 门店设置: store_code={store_code or '（未配置）'}，city={use_city or '（未配置）'}")

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import (
            create_mcp_http_client,
            streamable_http_client,
        )
    except ImportError:
        print('❌ 未安装 mcp 依赖，请运行：pip install "mcd-gacha[mcp]"')
        return 1

    http_client = create_mcp_http_client(
        headers={"Authorization": f"Bearer {token}"}, timeout=None
    )
    try:
        async with (
            streamable_http_client("https://mcp.mcd.cn", http_client=http_client) as (
                read,
                write,
            ),
            ClientSession(read, write) as session,
        ):
            init = await session.initialize()
            print(f"✅ 已连接: {init.server_info.name} v{init.server_info.version}")
            print(f"   协议版本: {init.protocol_version}")

            tools = (await session.list_tools()).tools
            print(f"📋 工具数: {len(tools)}")

            if use_city:
                resp = await session.call_tool(
                    "query-nearby-stores",
                    {"beType": 1, "searchType": 2, "city": use_city, "keyword": "麦当劳"},
                )
                text = "".join(
                    getattr(block, "text", "") or "" for block in resp.content
                )
                if '"success":true' in text:
                    print(f"🏪 门店解析: 「{use_city}」查询成功")
                else:
                    print(f"⚠️ 门店查询返回异常: {text[-200:]}")

            resp = await session.call_tool("now-time-info", {})
            text = "".join(getattr(block, "text", "") or "" for block in resp.content)
            print(f"🕐 now-time-info 冒烟: {'成功' if 'success' in text else '异常'}")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 连接失败: {type(exc).__name__}: {exc}")
        print("   常见原因：Token 无效(401) / 网络代理问题（可尝试设置 NO_PROXY=mcp.mcd.cn）")
        return 1
    finally:
        await http_client.aclose()

    print("\n✅ 诊断通过：真实 MCP 模式可用")
    return 0


if __name__ == "__main__":
    city_arg = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(asyncio.run(diagnose(city_arg)))
