---
name: mcd-gacha
description: 麦门抽卡模拟器——用二游抽卡机制（SSR/SR/R/N 四档稀有度 + 10 发硬保底）决定"中午吃什么"，基于麦当劳 MCP 真实菜单与在线核价。触发场景：(1) 用户要求"抽卡 / 抽一发 / 十连 / 把午饭交给命运 / 麦门抽卡 / 玄学一下"；(2) 用户在选择困难语境下请求随机点餐建议（预算 15 元内的吃土局 / 25-40 元的打工人回血局 / 21:00-04:00 的深夜宵夜局）；(3) 用户对抽到的组合不满意，要求"重铸 / 换掉某一件 / 这件换一个"（reroll --slot N，同品类替换、不消耗保底）；(4) 用户要求把抽到的组合"下单 / 提交订单 / 结账"（order 命令：先抽卡，下单时再让用户确认「去哪家店（--store-code）+ 堂食还是外带（--take-way-code）」，默认只试运行，用户明确确认后才加 --confirm 提交）；(5) 查询抽卡保底进度、出金统计、卡池开放状态、概率验证；(6) 关键词：抽卡、麦门、Gacha、欧皇、非酋、保底、出金、重铸、换一件、盲盒、今天吃什么、选择困难、下单、提交订单、换门店、取餐方式、堂食、外带。默认 mock 演示数据零配置可用，配置 MCP Token 后可切换真实菜单与在线核价。
---

# 麦门抽卡模拟器（Mcd-Gacha）

把「中午吃什么」的选择困难症，变成二游式抽卡：四档稀有度 + 10 发硬保底 +
预算内组合优化（0/1 背包 + 最优券），经麦当劳 MCP 真实核价（可选）。

> ⚠️ 非官方第三方开源玩具。默认只做「抽卡 + 核价」演示，**不会产生真实订单**；
> 下单是可选能力（默认试运行，需用户显式确认；只提交订单，不代付）。
> 价格与供应以麦当劳官方渠道为准。

## 何时使用本技能

- 用户让你「抽一发 / 十连 / 决定午饭 / 玄学一下今天吃什么」；
- 用户在选择困难时希望「随机帮他点一单」（对应用户预算档位选择卡池）；
- 用户对抽到的组合不满意，想「重铸 / 换掉某一件」；
- 用户想「下单 / 提交订单 / 结账」——**先抽卡，下单时再向用户确认门店与取餐方式**；
- 用户想查看保底进度、出金记录，或验证概率（蒙特卡洛）。

## 快速使用

优先使用 `uvx` 零安装运行（若已安装 `mcd-gacha` 命令则直接用命令）：

```bash
# 单抽：自动按时段选卡池（21:00-04:00 深夜池，其余常驻池）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha pull --json

# 指定卡池：poor（≤15 元）/ worker（25-40 元）/ midnight（深夜限时）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha pull -b worker --budget 35 --json

# 十连（共享保底计数器，第 10 发必出金）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha ten -b poor --json

# 重铸：替换上次组合中的某一件（同品类，优先升级/平价，不消耗保底）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha reroll --slot 2 --json

# 保底进度与生涯统计
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha status

# 下单：先抽卡，下单时再向用户确认「地点 + 取餐方式」
# ① 试运行：返回候选门店 + 取餐方式 + confirm_hint（不产生订单）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha order --json
# ② 用户确认后真实下单（--store-code 换门店/地点、--take-way-code 换取餐方式）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha order --confirm \
  --store-code 1421182 --take-way-code eat-in --json

# 概率自证（蒙特卡洛）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha simulate -n 100000 --seed 42
```

**始终加 `--json`**（给 AI 消费）；面向用户展示时按下表转写为友好文案。

## JSON 输出字段

```json
{
  "rarity": "SSR",                       // SSR / SR / R / N
  "rarity_label": "金卡 · 欧皇时刻",
  "banner": "worker_up",
  "banner_name": "打工人回血 · 限定 UP 池",
  "items": [{"code": "9900000888", "name": "巨无霸四件套", "qty": 1, "price": "32", "calories": null}],
  "price": {"original": "32", "discount": "0", "paid": "32", "coupon": null},
  "total_calories": null,
  "flavor": "欧皇时刻！这套价格，连店员都想拍照。",
  "pity_after": 0,                       // 抽完后的保底计数（0=刚出金）
  "data_source": "mock"                  // mock=内置演示快照 / mcp=真实在线核价
}
```

十连输出为上述对象的数组（长度 10，含 `pull_index`）。

## 结果展示指引（给 AI）

1. **稀有度视觉**：SSR ✨金色 / SR 💜紫色 / R 💙蓝色 / N 🩶灰色（隐藏款）；
2. 展示：餐品列表 → 原价与券后实付（`price.paid`）→ 热量（若有）→ `flavor` 文案；
3. 补一句保底进度：「再抽 {10 - pity_after} 发内必出金」；
4. `data_source=mock` 时注明「当前为内置演示菜单；配置 MCP Token 后为真实核价」；
5. 出金（SSR）时可提示用户「建议截图晒卡」；N 档是整活彩蛋，用幽默语气展示；
6. 用户想换掉组合里的某一件（「重铸第 N 件」）→ 执行 `mcd-gacha reroll --slot N --json`，
   展示「旧件 → 新件」的对比（同品类替换、优先升级/平价、不消耗保底）；
7. 用户要求下单 → **先抽卡，下单时再确认地点与取餐方式**（见下节「下单确认流程」）：
   先执行 `order --json`（**试运行**），把它返回的 `stores`（候选门店）与 `take_way`（取餐方式）
   转写成友好选项让用户选；用户给出「哪家店 + 堂食/外带」后，用
   `order --confirm --store-code <编号> --take-way-code <code> --json` 提交，
   展示订单号与支付链接，并明确提示「请自行到麦当劳官方渠道完成支付」——
   本技能只提交订单，不代付。
8. **收尾必须给可点击选项**（见下节「交互收尾（强制）」）：
   不要把「十连 / 重铸 / 下单 / 看保底进度」写成让用户打字的提示。

## 下单确认流程（地点 + 取餐方式）

**核心原则：抽卡阶段不打扰用户；只有到「下单」这一步，才问地点和取餐方式。**

`mcd-gacha order --json`（不加 `--confirm`）是**试运行**，返回：

```json
{
  "mode": "dry_run",
  "store": {"code": "1421182", "name": "麦当劳深圳湾文化广场餐厅", "city": "深圳市"},
  "stores": [                                    // 候选门店（地点确认）
    {"code": "1421182", "name": "麦当劳深圳湾文化广场餐厅", "address": "..."},
    {"code": "1420920", "name": "麦当劳深圳后海汇餐厅", "address": "..."}
  ],
  "take_way": [                                  // 取餐方式候选（必选其一）
    {"code": "eat-in", "title": "堂食", "is_default": false},
    {"code": "locker-in", "title": "外带", "is_default": false}
  ],
  "take_way_default": "eat-in",
  "items": [{"code": "521951", "name": "灰焰圆筒", "qty": 1, "price": "5"}],
  "price": {"original": "30", "discount": "0", "paid": "30"},
  "need_confirm": true,
  "confirm_hint": "mcd-gacha order --confirm --store-code 1421182 --take-way-code eat-in"
}
```

AI 的行动顺序：

1. 把 `stores` 列成带序号的清单（`# / 门店 / 门店编号 / 地址`），问用户「**去哪家店取？**」；
2. 把 `take_way` 列成选项（如「1 堂食 / 2 外带」），问用户「**怎么取？**」；
3. 用户没特别指定 → 用 `store.code` + `take_way_default` 作为默认，明确复述一遍再确认；
4. 用户点头后执行 `order --confirm --store-code <code> --take-way-code <code>`；
5. 展示 `order_id` / `paid` / `pay_url`，提醒自行支付。

换城市找店：`order --json --city 广州市`（用于列候选门店）；
`--store-code` 为空时用本地配置或按城市自动选最近门店。

## 交互收尾（强制）：给可点击选项，不要让用户打字

每次展示完抽卡 / 十连 / 重铸结果后，**必须**给出**可点击的选项按钮**来承接下一步
（使用 WorkBuddy 的提问-选项能力渲染按钮），**不要**在文案里写
「要十连 / 重铸 / 下单，说一声就行」这类**要求用户自己打字**的收尾。

固定提供以下 4 个选项（label 要短）：

| 选项 label | description（说清代价与结果） |
|-----------|------------------------------|
| `十连` | 一次抽 10 发（共享保底计数器，第 10 发必出金） |
| `重铸一件` | 换掉这套里不满意的某一件（同品类替换、不消耗保底） |
| `下单` | 提交这套组合；会先让你确认门店与取餐方式（堂食 / 外带） |
| `看保底进度` | 查看当前保底计数与生涯出金统计 |

规则：

- 按结果**动态微调**选项，而不是死板照抄：
  - 已出 SSR → 把 `十连` 换成 `再来一发`；
  - 结果来自 mock 演示数据 → 把 `下单` 换成 `切换真实菜单再抽`，并说明 mock 编码是虚拟 SKU；
  - 用户是十连结果 → 去掉 `十连`；若这轮十连里出过 SSR，用 `再来一发` 补位；
- **不得**给任何选项标注「推荐 / Recommended」——不诱导消费是硬红线，只做并列呈现。
- 选项之外保留自由输入（提问组件自带），用户提出其他要求时照常处理。
- 用户点了某个选项后，**直接执行**对应命令，不要重复追问一遍。

## 配置（真实 MCP 模式，可选）

```bash
# 1) Token（环境变量 MCD_MCP_TOKEN，或本地保存）
mcd-gacha config set-token <TOKEN>

# 2) 门店（到店取餐场景需要；city 用完整城市名）
mcd-gacha stores --city 深圳市        # 查询附近门店（拿 storeCode）
mcd-gacha config set-store --city 深圳市
```

- 未配置时自动使用**内置演示菜单**（离线可玩，输出标注 mock）；
- 依赖安装：`pip install "mcd-gacha[mcp]"`（或 `uvx --from "mcd-gacha[mcp]"`）；
- 任何真实接口异常都会自动回退演示数据并提示，不会中断抽卡体验。

## 边界与红线

- **交互收尾必须给可点击选项**：抽卡 / 十连 / 重铸后，用选项按钮承接下一步
  （十连 / 重铸一件 / 下单 / 看保底进度），**不得**要求用户自己打字；
  也不得给任何选项标注「推荐」，避免诱导消费；
- **下单是唯一的写操作，且必须显式确认**：`mcd-gacha order` 默认**只试运行**（dry-run，不产生订单），必须由用户明确说「确认下单」后，才加 `--confirm` 真正提交；
- **下单前必须先向用户确认「地点 + 取餐方式」**：用试运行返回的 `stores` / `take_way` 让用户选，
  不得代替用户直接拍板（可给默认值，但要复述确认）；
- **只提交、不代付**：命令返回订单号与支付链接，支付由用户在麦当劳官方渠道自行完成；不自动下单、不代付；
- **仅支持到店自取**（`beType=1`）：外送 / 得来速 / 团餐尚未实现，会明确报错；
- **演示数据无法下单**：mock 模式抽出的组合是虚拟 SKU，`order` 会直接拒绝——须先用 `--real` 抽卡；
- 不诱导消费：追随用户预算，不鼓励加预算/多点餐；
- 输出中不得出现贬损品牌或不当消费引导的表述（文案池已内置合规柔化）。
