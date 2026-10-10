"""真实麦当劳 MCP 数据源（Streamable HTTP）。

联调实测结论（2026-10-10，mcd-mcp v1.0.0 / 协议 2025-06-18）：
- 接入：https://mcp.mcd.cn，Streamable HTTP，请求头 Authorization: Bearer <token>；
- 到店取餐场景：beType=1, orderType=1，query-meals / calculate-price 必传 storeCode；
- 门店解析：query-nearby-stores(beType=1, searchType=2, city=..., keyword="麦当劳")
  → data[].storeCode / beCode；
- 菜单结构：data.categories（分类）+ data.meals（{code: {name, currentPrice,
  originalPrice, canWithOrder}}）；
- 核价：calculate-price(items=[{productCode, quantity, couponId?, couponCode?}])
  → data.originalPrice / discount / price（单位：分）；
- 营养：list-nutrition-foods 一次返回全量 CSV 文本（productName,...,energyKcal,...）；
- 券：query-store-coupons（无券时 data 为空数组）。

设计约束：
- 连接生命周期 = 一次 CLI 进程（AsyncExitStack 管理）；
- 会话内缓存菜单/营养/券，单次抽卡请求数 ≤ 4；
- 任何异常包装为 McpUnavailableError / McpQueryError，由调用方回退内置演示数据。
"""

from __future__ import annotations

import json
import os
from contextlib import AsyncExitStack
from datetime import datetime
from urllib.parse import urlparse

from ..models import (
    Coupon,
    LineItem,
    Meal,
    Nutrition,
    OrderResult,
    PriceQuote,
    Store,
    TakeWay,
    yuan,
)

MCP_URL = "https://mcp.mcd.cn"
DEFAULT_KEYWORD = "麦当劳"

# 非餐品关键词（周边/玩具/限定人群商品，不进入抽卡池）
NON_FOOD_KEYWORDS = (
    "周边",
    "毛绒",
    "公仔",
    "玩具",
    "盲盒",
    "盲袋",
    "福袋",
    "百宝袋",
    "徽章",
    "帽子",
    "棒球帽",
    "联名",
    "卡券",
    "兑换券",
    "礼盒",
    "学生",
)


class McpUnavailableError(RuntimeError):
    """真实 MCP 不可用（依赖缺失 / 鉴权失败 / 网络异常 / 未配置门店）。"""


class McpQueryError(RuntimeError):
    """MCP 业务错误（success=false 或返回不可解析）。"""


def _bypass_proxy_for(url: str) -> None:
    """确保访问 MCP 主机时绕过系统代理。

    部分环境（沙箱 / CI / 企业网络）会设置 HTTP(S)_PROXY，导致 mcp.mcd.cn
    不可达，需要把主机名追加进 NO_PROXY（httpx 在建立连接时读取该变量）。
    这里只做追加、不覆盖用户已有配置；仅在未包含目标主机时才写入。
    """
    host = urlparse(url).hostname
    if not host:
        return
    entries: list[str] = []
    for key in ("NO_PROXY", "no_proxy"):
        for part in os.environ.get(key, "").split(","):
            part = part.strip()
            if part and part not in entries:
                entries.append(part)
    if host in entries:
        return
    entries.append(host)
    merged = ",".join(entries)
    # 同时写入大小写两种变量名，兼容不同库/平台的读取习惯
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


def _to_cents(value: object) -> int:
    """MCP 价格（元，字符串或数字）→ 分。"""
    if value is None:
        return 0
    try:
        return yuan(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _classify(category_name: str, item_name: str) -> str:
    """推断餐品类别：名称规则优先，分类名兜底。"""
    name = item_name

    # 套餐类（名称）
    if any(
        k in name
        for k in ("四件套", "三件套", "双人", "分享", "随心选", "套餐", "拼盘", "1+1", "随心配", "组合")
    ):
        return "deal"
    # 咖啡类（名称）
    if any(k in name for k in ("咖啡", "拿铁", "美式", "卡布奇诺", "澳白", "奶铁", "摩卡")):
        return "coffee"
    # 饮品类（名称）
    if any(k in name for k in ("可乐", "雪碧", "橙汁", "红茶", "奶茶", "柠檬", "矿泉水", "阳光橙", "椰")):
        return "drink"
    # 汉堡类（名称）
    if any(
        k in name
        for k in ("汉堡", "巨无霸", "牛堡", "吉士", "鱼堡", "鸡腿堡", "卷", "双牛", "堡", "麦香鱼")
    ):
        return "burger"
    # 小食类（名称）
    if any(
        k in name
        for k in ("薯条", "鸡块", "麦乐鸡", "鸡翅", "派", "新地", "麦旋风", "圆筒", "冰淇淋", "鸡排", "炸鸡", "鸡条")
    ):
        return "snack"

    # 分类名兜底
    cat = category_name.replace("\n", "")
    if any(k in cat for k in ("随心配", "单人餐", "多人餐", "套餐", "大卡", "乐园", "分享", "拼盘")):
        return "deal"
    if "咖啡" in cat:
        return "coffee"
    if "饮品" in cat:
        return "drink"
    if any(k in cat for k in ("小食", "甜品", "炸鸡", "蘸酱")):
        return "snack"
    if any(k in cat for k in ("汉堡", "牛堡", "卷", "厚牛")):
        return "burger"
    return "snack"  # 保守兜底：当作小食处理


def _derive_tags(name: str, category: str, price_cents: int) -> tuple[str, ...]:
    """从名称/类别/价格推导语义标签（供抽卡策略使用）。"""
    tags: list[str] = []
    if category == "deal":
        tags += ["deal", "staple"]
    elif category == "burger":
        tags.append("staple")
    elif category == "coffee":
        tags += ["coffee", "night"]
    elif category == "drink":
        tags.append("drink")
    elif category == "snack":
        if any(k in name for k in ("薯条", "鸡块", "麦乐鸡", "鸡翅", "鸡排", "炸鸡", "鸡条")):
            tags.append("side")
        if any(k in name for k in ("派", "新地", "麦旋风", "圆筒", "冰淇淋")):
            tags.append("dessert")

    if any(k in name for k in ("安格斯", "巨无霸", "双人", "分享", "四件套", "厚牛", "大鸡排", "牛堡")):
        tags.append("premium")
    if any(
        k in name
        for k in ("巨无霸", "麦辣", "麦香", "板烧", "双层", "吉士", "可乐", "薯条", "麦乐鸡", "新地", "麦旋风", "圆筒")
    ):
        tags.append("classic")
    if price_cents <= 1500:
        tags.append("value")
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return tuple(out)


def _parse_nutrition_text(text: str) -> dict[str, int]:
    """解析 list-nutrition-foods 的 CSV 文本 → {productName: energyKcal}。"""
    table: dict[str, int] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[") or "productName" in line:
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        name = parts[0]
        try:
            kcal = int(float(parts[3]))
        except ValueError:
            continue
        if name:
            table[name] = kcal
    return table


def _pick_take_way(candidates: list[dict]) -> str | None:
    """从 calculate-price 的 takeWayList 中挑选取餐方式 code。

    优先标记为默认的项（isDefault/default），否则取第一个有效项。
    到店/得来速下单（orderType=1）的 create-order 必传 takeWayCode。
    """
    for item in candidates:
        code = item.get("code")
        if code and (item.get("isDefault") or item.get("default")):
            return str(code)
    for item in candidates:
        code = item.get("code")
        if code:
            return str(code)
    return None


def _normalize_take_ways(candidates: list[dict]) -> list[TakeWay]:
    """把 calculate-price 的 takeWayList 规范化为 TakeWay 列表（供用户选择）。

    不同门店返回的键名可能是 title / name，这里统一归一；
    无 code 的条目直接丢弃（下单必传 code）。
    """
    options: list[TakeWay] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        if not code:
            continue
        options.append(
            TakeWay(
                code=str(code),
                title=str(item.get("title") or item.get("name") or ""),
                is_default=bool(item.get("isDefault") or item.get("default")),
            )
        )
    return options


def _parse_cents(value: object) -> int | None:
    """尽力解析金额（分）。无法确定时返回 None，由调用方展示原始字段。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
        return _to_cents(text)
    return None


def _parse_order(payload: dict, data: dict) -> OrderResult:
    """从 create-order 返回中提取订单号 / 支付链接（键名多路兜底）。"""

    def pick(*keys: str) -> str | None:
        for source in (data, payload):
            for key in keys:
                value = source.get(key)
                if value:
                    return str(value)
        return None

    paid = _parse_cents(data.get("price") or data.get("paidPrice") or data.get("totalPrice"))
    return OrderResult(
        order_id=pick("orderId", "orderNo", "order_id", "id"),
        pay_url=pick("payUrl", "pay_url", "paymentUrl", "payLink", "url"),
        paid_cents=paid,
        status=pick("status", "orderStatus", "state"),
        raw=payload,
    )


def _extract_json(response) -> dict | None:
    """从 MCP Tool 返回的 content blocks 中提取 JSON 负载。"""
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        index = text.rfind('{"success"')
        if index < 0:
            index = text.find("{")
        if index < 0:
            continue
        try:
            payload, _ = json.JSONDecoder().raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


class McpDataSource:
    """麦当劳 MCP 数据源（到店取餐场景）。"""

    mode = "mcp"

    def __init__(
        self,
        token: str,
        *,
        store_code: str | None = None,
        city: str | None = None,
        url: str = MCP_URL,
    ) -> None:
        if not token:
            raise McpUnavailableError("MCP Token 为空")
        self.token = token
        self.url = url
        self.store_code = store_code
        self.city = city

        self._stack = AsyncExitStack()
        self._session = None
        self._store: Store | None = None
        # 会话级缓存
        self._meals: list[Meal] | None = None
        self._coupons: list[Coupon] | None = None
        self._nutrition_table: dict[str, int] | None = None
        self._last_nearby: list[Store] | None = None
        # 最近一次核价返回的取餐方式列表（create-order 到店场景的 takeWayCode 来源）
        self._take_way_list: list[dict] = []

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """建立连接、初始化会话并解析门店。"""
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import (
                create_mcp_http_client,
                streamable_http_client,
            )
        except ImportError as exc:  # pragma: no cover
            raise McpUnavailableError(
                '未安装 mcp 依赖，请运行：pip install "mcd-gacha[mcp]"'
            ) from exc

        # 让 MCP 主机绕过可能存在的系统代理，避免真实链路被代理拦截后回退 mock
        _bypass_proxy_for(self.url)

        try:
            http_client = await self._stack.enter_async_context(
                create_mcp_http_client(
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=None,
                )
            )
            streams = await self._stack.enter_async_context(
                streamable_http_client(self.url, http_client=http_client)
            )
            read, write = streams
            self._session = await self._stack.enter_async_context(ClientSession(read, write))
            await self._session.initialize()
            await self._resolve_store()
        except McpUnavailableError:
            await self.close()
            raise
        except Exception as exc:  # noqa: BLE001 —— 网络/鉴权等统一包装
            await self.close()
            raise McpUnavailableError(f"MCP 连接失败：{exc}") from exc

    async def close(self) -> None:
        try:
            await self._stack.aclose()
        except Exception:  # noqa: BLE001 —— 退出阶段的清理错误不影响主流程
            pass
        finally:
            self._session = None

    async def tool_count(self) -> int:
        """返回当前连接可用工具数（doctor 诊断用）。"""
        if self._session is None:
            return 0
        try:
            result = await self._session.list_tools()
            return len(result.tools)
        except Exception:  # noqa: BLE001
            return 0

    # ------------------------------------------------------------------
    # 取餐方式候选（供 CLI 在下单前向用户确认）
    # ------------------------------------------------------------------

    @property
    def take_way_options(self) -> list[TakeWay]:
        """最近一次核价返回的取餐方式候选（下单时供用户选择）。

        注意：只有在调用过 calculate_price 之后才有值；为空表示该门店
        未返回到店取餐方式（可能不支持到店下单）。
        """
        return _normalize_take_ways(self._take_way_list)

    @property
    def default_take_way(self) -> str | None:
        """取餐方式默认项 code（优先 isDefault，否则第一个）。"""
        return _pick_take_way(self._take_way_list)

    # ------------------------------------------------------------------
    # 内部：调用与解析
    # ------------------------------------------------------------------

    async def _call(self, tool: str, arguments: dict) -> dict:
        if self._session is None:
            raise McpUnavailableError("MCP 会话未初始化（请先调用 start()）")
        try:
            response = await self._session.call_tool(tool, arguments)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "401" in message or "Unauthorized" in message:
                raise McpUnavailableError(
                    "Token 无效或已过期（401），请检查 MCD_MCP_TOKEN"
                ) from exc
            if "429" in message:
                raise McpUnavailableError("请求过于频繁（429 限流），请稍后再试") from exc
            raise McpUnavailableError(f"MCP 调用失败（{tool}）：{exc}") from exc

        payload = _extract_json(response)
        if payload is None:
            raise McpQueryError(f"{tool} 未返回可解析数据")
        if payload.get("success") is False:
            raise McpQueryError(
                f"{tool} 返回错误：{payload.get('message')}（code={payload.get('code')}）"
            )
        return payload

    async def _resolve_store(self) -> None:
        """确定门店：优先使用已配置的 storeCode，否则按城市搜索第一个门店。"""
        if self.store_code:
            self._store = Store(code=str(self.store_code), name="", city=self.city or "")
            return
        if not self.city:
            raise McpUnavailableError(
                "未配置门店：请先运行 `mcd-gacha config set-store --city 深圳市`"
                "（或 --store-code 门店编号）"
            )
        payload = await self._call(
            "query-nearby-stores",
            {
                "beType": 1,
                "searchType": 2,
                "city": self.city,
                "keyword": DEFAULT_KEYWORD,
            },
        )
        stores = payload.get("data") or []
        if not stores:
            raise McpUnavailableError(
                f"未在「{self.city}」找到门店，请尝试换用完整城市名（如：深圳市）"
            )
        self._last_nearby = [
            Store(
                code=str(item.get("storeCode") or ""),
                name=item.get("storeName") or "",
                city=self.city or "",
                address=item.get("address") or "",
            )
            for item in stores
        ]
        first = stores[0]
        self.store_code = str(first.get("storeCode"))
        self._store = self._last_nearby[0]

    # ------------------------------------------------------------------
    # MenuDataSource 协议实现
    # ------------------------------------------------------------------

    async def query_meals(self, store_code: str | None = None) -> list[Meal]:
        if self._meals is None:
            payload = await self._call(
                "query-meals",
                {"storeCode": self.store_code, "orderType": 1, "beType": 1},
            )
            self._meals = self._convert_meals(payload)
        return list(self._meals)

    def _convert_meals(self, payload: dict) -> list[Meal]:
        data = payload.get("data") or {}
        meals_raw: dict = data.get("meals") or {}

        # code → 分类名（跳过跨类聚合的"人气热卖"，首个真实分类优先）
        category_of: dict[str, str] = {}
        for category in data.get("categories") or []:
            name = (category.get("name") or "").replace("\n", "")
            if name == "人气热卖":
                continue
            for entry in category.get("meals") or []:
                code = entry.get("code")
                if code and code not in category_of:
                    category_of[code] = name

        meals: list[Meal] = []
        for code, item in meals_raw.items():
            name = item.get("name") or ""
            if not name or any(k in name for k in NON_FOOD_KEYWORDS):
                continue
            # 辅料/调味品（如"韩式烟熏芝士风味酱"）不应作为组合主体，
            # 避免出现「酱 + 饮料」式的凑单组合；注意"蘸酱炸鸡"等餐品不误伤。
            if name.endswith("酱") or "酱料" in name:
                continue
            # 核价口径（2026-10-10 实测）：
            # canWithOrder=True 的活动类商品（四件套/分享餐等）裸核价按【原价】；
            # 其余商品核价按【现价】。这里采用与核价一致的价格，
            # 保证「本地预算校验 = 服务端核价」不虚高（核价不超预算的不变量）。
            if item.get("canWithOrder"):
                price_cents = _to_cents(item.get("originalPrice")) or _to_cents(
                    item.get("currentPrice")
                )
            else:
                price_cents = _to_cents(item.get("currentPrice")) or _to_cents(
                    item.get("originalPrice")
                )
            if price_cents <= 0:
                continue
            category = _classify(category_of.get(code, ""), name)
            meals.append(
                Meal(
                    code=str(code),
                    name=name,
                    category=category,
                    price_cents=price_cents,
                    tags=_derive_tags(name, category, price_cents),
                    calories=None,  # 由 list_nutrition 懒加载填充
                )
            )
        return meals

    async def calculate_price(self, lines: list[LineItem]) -> PriceQuote:
        items = [{"productCode": line.meal.code, "quantity": line.qty} for line in lines]
        # 有券时：把第一张券附到组合中最贵的商品上，由服务端核销并计算真实折扣
        coupons = await self.list_coupons()
        if coupons and items:
            coupon = coupons[0]
            target = max(lines, key=lambda line: line.meal.price_cents)
            for item, line in zip(items, lines, strict=True):
                if line is target:
                    item["couponId"] = coupon.id
                    if coupon.code:
                        item["couponCode"] = coupon.code
                    break

        payload = await self._call(
            "calculate-price",
            {
                "storeCode": self.store_code,
                "orderType": 1,
                "beType": 1,
                "items": items,
            },
        )
        data = payload.get("data") or {}
        original = int(data.get("originalPrice") or data.get("productOriginalPrice") or 0)
        paid = int(data.get("price") or original)
        discount = int(data.get("discount") or max(0, original - paid))
        # 取餐方式（create-order 到店下单必传 takeWayCode，来源即此处）
        take_ways = data.get("takeWayList")
        if isinstance(take_ways, list):
            self._take_way_list = [item for item in take_ways if isinstance(item, dict)]
        coupon_name = None
        if discount > 0 and coupons:
            coupon_name = coupons[0].name
        return PriceQuote(
            original_cents=original,
            discount_cents=discount,
            paid_cents=paid,
            coupon_id=coupons[0].id if (discount > 0 and coupons) else None,
            coupon_name=coupon_name,
            source=self.mode,
        )

    async def _resolve_take_way_code(self, lines: list[LineItem]) -> str | None:
        """获取到店下单必需的取餐方式 code（触发一次核价以拿到 takeWayList）。"""
        if not self._take_way_list:
            try:
                await self.calculate_price(lines)
            except (McpUnavailableError, McpQueryError):
                return None
        return _pick_take_way(self._take_way_list)

    async def create_order(
        self,
        lines: list[LineItem],
        *,
        be_type: int = 1,
        order_type: int = 1,
        address_id: str | None = None,
        remark: str | None = None,
        take_way_code: str | None = None,
    ) -> OrderResult:
        """创建订单（真实下单）。

        安全约定：本方法只应由 CLI 的 `order --confirm` 调用，
        调用方负责二次确认——本层不再做交互确认。

        参数规则（2026-10-10 实测 schema）：
        - 到店自取 beType=1 → orderType=1，不传 beCode，但 **必传 takeWayCode**；
        - 外送/团餐 → orderType=2，需 beCode 与 addressId（本项目暂未实现）。
        """
        if not lines:
            raise McpQueryError("订单商品为空，无法下单")
        if not self.store_code:
            raise McpUnavailableError(
                "未配置门店：请先运行 `mcd-gacha config set-store --city 深圳市`"
            )

        items: list[dict] = [
            {"productCode": line.meal.code, "quantity": line.qty} for line in lines
        ]
        # 券：与核价口径保持一致（把第一张可用券挂到最贵的商品上，由服务端核销）
        coupons = await self.list_coupons()
        if coupons:
            coupon = coupons[0]
            target = max(lines, key=lambda line: line.meal.price_cents)
            for item, line in zip(items, lines, strict=True):
                if line is target:
                    item["couponId"] = coupon.id
                    if coupon.code:
                        item["couponCode"] = coupon.code
                    break

        args: dict = {
            "storeCode": self.store_code,
            "orderType": order_type,
            "beType": be_type,
            "items": items,
        }
        if order_type == 1:
            code = take_way_code or await self._resolve_take_way_code(lines)
            if not code:
                raise McpQueryError(
                    "未能从核价结果获取取餐方式（takeWayCode），该门店可能不支持到店下单；"
                    "可用 --take-way-code 手动指定"
                )
            args["takeWayCode"] = code
        else:
            if not address_id:
                raise McpQueryError("外送/团餐下单需要 --address-id")
            args["addressId"] = address_id
        if remark:
            args["remark"] = remark[:50]

        payload = await self._call("create-order", args)
        data = payload.get("data") or {}
        return _parse_order(payload, data)

    async def list_coupons(self, store_code: str | None = None) -> list[Coupon]:
        if self._coupons is None:
            try:
                payload = await self._call(
                    "query-store-coupons",
                    {"storeCode": self.store_code, "orderType": 1, "beType": 1},
                )
            except (McpUnavailableError, McpQueryError):
                self._coupons = []
                return []
            coupons: list[Coupon] = []
            for item in payload.get("data") or []:
                coupon_id = item.get("couponId")
                if not coupon_id:
                    continue
                coupons.append(
                    Coupon(
                        id=str(coupon_id),
                        name=item.get("title") or "优惠券",
                        type="external",  # 金额与门槛未知，交由服务端核价
                        amount_cents=0,
                        desc=item.get("title") or "",
                        code=item.get("couponCode"),
                    )
                )
            self._coupons = coupons
        return list(self._coupons)

    async def list_nutrition(self, codes: list[str]) -> dict[str, Nutrition]:
        if self._nutrition_table is None:
            try:
                payload = await self._call("list-nutrition-foods", {})
                raw = payload.get("data")
                self._nutrition_table = _parse_nutrition_text(raw if isinstance(raw, str) else "")
            except (McpUnavailableError, McpQueryError):
                self._nutrition_table = {}

        meals_by_code = {meal.code: meal for meal in (self._meals or [])}
        result: dict[str, Nutrition] = {}
        for code in codes:
            meal = meals_by_code.get(code)
            if meal is None:
                continue
            kcal = self._nutrition_table.get(meal.name)
            if kcal is None:
                # 名称归一化再试（去空格）
                normalized = meal.name.replace(" ", "")
                for key, value in self._nutrition_table.items():
                    if key.replace(" ", "") == normalized:
                        kcal = value
                        break
            if kcal is not None:
                result[code] = Nutrition(energy_kcal=kcal)
        return result

    async def nearby_stores(self, address: str | None = None) -> list[Store]:
        # 复用初始化时的搜索结果（同城），避免重复请求
        if address is None and self._last_nearby is not None:
            return list(self._last_nearby)
        city = address or self.city
        if not city:
            raise McpUnavailableError("查询门店需要提供城市名（--city）")
        payload = await self._call(
            "query-nearby-stores",
            {"beType": 1, "searchType": 2, "city": city, "keyword": DEFAULT_KEYWORD},
        )
        stores: list[Store] = []
        for item in payload.get("data") or []:
            stores.append(
                Store(
                    code=str(item.get("storeCode") or ""),
                    name=item.get("storeName") or "",
                    city=city,
                    address=item.get("address") or "",
                )
            )
        return stores

    async def now_time(self) -> datetime:
        try:
            payload = await self._call("now-time-info", {})
            data = payload.get("data")
            if isinstance(data, dict):
                for key in ("datetime", "dateTime", "time"):
                    value = data.get(key)
                    if isinstance(value, str) and value:
                        parsed = _try_parse_datetime(value)
                        if parsed:
                            return parsed
        except (McpUnavailableError, McpQueryError):
            pass
        return datetime.now().astimezone()


def _try_parse_datetime(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).astimezone()
        except ValueError:
            continue
    return None
