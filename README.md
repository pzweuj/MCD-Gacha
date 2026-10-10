```
  ███╗   ███╗ ██████╗██████╗      ██████╗  █████╗  ██████╗██╗  ██╗ █████╗
  ████╗ ████║██╔════╝██╔══██╗    ██╔════╝ ██╔══██╗██╔════╝██║  ██║██╔══██╗
  ██╔████╔██║██║     ██║  ██║    ██║  ███╗███████║██║     ███████║███████║
  ██║╚██╔╝██║██║     ██║  ██║    ██║   ██║██╔══██║██║     ██╔══██║██╔══██║
  ██║ ╚═╝ ██║╚██████╗██████╔╝    ╚██████╔╝██║  ██║╚██████╗██║  ██║██║  ██║
  ╚═╝     ╚═╝ ╚═════╝╚═════╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝
```

<div align="center">

# 🍟 MCD-Gacha · 麦门抽卡模拟器

**用二游抽卡机制决定「中午吃什么」**

> 「中午不知道吃什么？把工位命运交给一顿预算内的单抽。」

<p align="center">
  <img src="docs/assets/hero-demo.gif" width="780" alt="Mcd-Gacha 抽卡演示：连接 → 蓄力 → 金色传说 → 开出 SSR 巨无霸+薯条" />
</p>

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#-安装)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Gacha](https://img.shields.io/badge/Gacha-Active-success.svg)](#-卡池与概率)
[![保底](https://img.shields.io/badge/保底-10_发必出金-F5A623.svg)](#-保底规则)
[![MCP](https://img.shields.io/badge/MCP-mcp.mcd.cn-red.svg)](MCP_INTEGRATION.md)
[![非官方](https://img.shields.io/badge/非官方-第三方开源玩具-lightgrey.svg)](#-合规声明)

**简体中文** | [English](README_EN.md)

</div>

---

> ⚠️ **本项目为非官方第三方开源玩具**，与麦当劳官方无隶属关系。餐品信息、价格与供应状态以麦当劳官方渠道的实时结果为准。

## 💭 为什么用「抽卡」而不是推荐算法？

面对麦当劳几十个在售餐品，选择困难症的真实成本不是「不知道有什么」，而是**「决定不了吃什么」**：

- 想省钱，但一张张翻券、算门槛很累；
- 想控制预算，但「主食+配餐+饮料」的组合是人算不过来的；
- 好不容易点完，又开始纠结「是不是点贵了」。

推荐算法给出的是「你可能喜欢」——那只是又一个待决策项，负担并没有减轻。
**抽卡给的是一份已经满足预算约束的完整搭配**，而且附带一个说得出口的理由：「命运选的」。

- 一抽定午饭，决策成本归零；
- 「10 发保底」和保底进度条，让摸鱼时间有了目标感；
- 抽到金卡可以截图晒群——选择困难症的解法，也可以是一种工位娱乐。

> 随机不是为了偷懒，而是——在几十个选项里，把「选不动」变成「抽一下」。

## 🎰 这是什么？

把「中午吃什么」的选择困难症，包装成**二游抽卡**：

- 🎴 **三个卡池**：吃土经济学常驻池 / 打工人回血限定 UP 池 / 深夜玄学宵夜池（21:00-04:00 限时）
- ✨ **四档稀有度**：金卡（欧皇金光）→ 紫卡 → 蓝卡 → 隐藏灰卡（抽象艺术）
- 🛡️ **10 发硬保底**：连续 9 发未出金，第 10 发必出金
- 🔨 **重铸玩法**：不满意组合里某一件？同品类重铸换一件（优先升级/平价），**不消耗保底进度**
- 💰 **真实核价**：接入[麦当劳 MCP Server](MCP_INTEGRATION.md)，菜单与价格来自官方接口（也可离线试玩）
- 🛒 **可下单（安全闸门）**：`mcd-gacha order` 把抽到的组合提交给官方 MCP。**先抽卡，下单时再确认地点和取餐方式**——默认只试运行并列出候选门店 + 取餐方式，加 `--confirm --store-code <编号> --take-way-code <堂食/外带>` 才真正下单并回显支付链接
- 🧾 **晒卡利器**：抽卡结果一键生成像素风 SVG 分享卡，随手发群
- ⚖️ **概率透明**：内置 `simulate` 蒙特卡洛自证命令，出率随时可验证

## 🧩 三种用法（任选其一，同一套引擎）

| 形态 | 怎么用 | 适合场景 |
|------|--------|----------|
| 🧩 **AI Skill** | 把本仓库装进 WorkBuddy / Claude 等支持 Skill 的 Agent，对 AI 说「抽一发」「帮我决定午饭」即可（定义见 [`SKILL.md`](SKILL.md)） | 对话式摸鱼 |
| ⌨️ **CLI 应用** | `uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha pull`（即下方「30 秒上手」） | 终端极客、脚本自动化 |
| 🌐 **在线试玩** | **[点开即抽](https://pzweuj.github.io/mcd-gacha/)**（GitHub Pages，零安装翻牌动画版） | 不想装环境的路人 |

> Skill 形态与 CLI 应用共享同一套概率引擎与核价逻辑：`SKILL.md` 是交互层，Python 引擎是能力底座。

> 🌐 **在线试玩是怎么部署的**：[`demo/`](demo/) 是**零依赖纯静态站**（无构建步骤、全部相对路径，可直接跑在子路径下），
> 由 [`.github/workflows/pages.yml`](.github/workflows/pages.yml) 在每次推送后自动发布到 GitHub Pages。
> 仓库需命名为小写 `mcd-gacha`，并在 **Settings → Pages → Source** 选择「GitHub Actions」。

## 🚀 30 秒上手

**方式零：在线试玩（零安装，翻牌动画版）**

👉 **<https://pzweuj.github.io/mcd-gacha/>**

**方式一：零配置试玩（内置演示菜单，无需任何 Token）**

```bash
# 需要已安装 uv（https://docs.astral.sh/uv/）
uvx --from git+https://github.com/pzweuj/mcd-gacha mcd-gacha pull
```

**方式二：安装到本地（推荐，后续命令更短）**

```bash
# 用 uv 或 pipx 安装
uv tool install git+https://github.com/pzweuj/mcd-gacha
# 或
pipx install git+https://github.com/pzweuj/mcd-gacha
```

然后用一条命令开抽：

```bash
$ mcd-gacha pull                    # 单抽（按时段自动选卡池）
$ mcd-gacha ten -b worker           # 打工人 UP 池十连
$ mcd-gacha simulate -n 100000      # 概率自证
```

## 🎮 体验预览

```text
━━━ 开 箱 ━━━
╭──────────── SSR · 金卡 · 欧皇时刻 ✨ ────────────╮
│                                                  │
│  🍔 巨无霸           ¥25.5                        │
│  🍟 中薯条           ¥12.5                        │
│  🥤 可口可乐（中）    ¥9.5                         │
│                                                  │
│  原价 ¥47.5  →  券后 ¥39.5（满40减8 · 省 ¥8）      │
│  总热量 1040 kcal                                 │
│                                                  │
╰──────────────────────────────────────────────────╯
  欧皇时刻！这套价格，连店员都想拍照。
  保底进度 ░░░░░░░░░░ 0/10（再抽 10 发内必出金）
```

## 🎴 卡池与概率

| 卡池 | 预算 | 特色 | 开放时间 |
|------|------|------|----------|
| 🍟 吃土经济学 · 常驻池 | ¥8–15 | 卡在预算线内的快乐 | 全天 |
| 🍔 打工人回血 · 限定 UP 池 | ¥25–40 | 必含招牌大件（巨无霸/安格斯） | 全天 |
| 🌙 深夜玄学 · 宵夜池 | ¥15–35 | 咖啡因与宵夜的玄学搭配 | 21:00–04:00 |

| 稀有度 | 基础概率 | 组合特征 | 视觉 |
|--------|---------|----------|------|
| **SSR（金卡）** | 5% | 预算内价值最大化 + 最优券，性价比之王 | ✨ 金光 |
| **SR（紫卡）** | 25% | 经典热销正餐（主+配+饮） | 💜 紫光 |
| **R（蓝卡）** | 60% | 规矩的一顿（1+1 随心配 / 主+配） | 💙 蓝光 |
| **N（隐藏款）** | 10% | 抽象整活：意料之外的搭配艺术 | 🩶 灰光 |

### 保底规则

- 每个卡池**独立计数**：连续 9 发未出金，第 10 发**必出金**；出金后计数清零。
- 十连 = 顺序 10 次单抽，共享计数器。

### 📢 概率透明声明

基础出金率 5% 叠加 10 发硬保底后，**SSR 有效出率约 12.5%**（平均约 8 抽一金）。
不信？自己验：

```bash
$ mcd-gacha simulate -n 100000 --seed 42
```

```
🎲 蒙特卡洛模拟（100,000 次 seed=42）
 SSR   基础 5%   实测 12.40%
 ⛳ SSR 平均间隔 8.06 抽；最大间隔 10 抽；保底触发 7,855 次
```

## 🔨 重铸玩法

抽到的组合里有一件不想要？**重铸**它——二游式「锁定重铸」：

```bash
$ mcd-gacha reroll --slot 2
  🔨 重铸第 2 件：“辣”么快乐套餐 → 麦香鸡套餐
```

- **同品类替换**：只换指定件（可乐换可乐位、汉堡换汉堡位），其余卡面保持；
- **优先升级/平价**：候选里有更好的先试，实在放不下才降级；
- **不消耗保底**：重铸是「工艺」不是抽卡——保底进度条纹丝不动；
- **预算硬约束**：重铸后组合仍在预算内（券后实付 ≤ 预算）。

## 📦 安装

```bash
# 方式 A：uv（推荐）
uv tool install git+https://github.com/pzweuj/mcd-gacha

# 方式 B：pipx
pipx install git+https://github.com/pzweuj/mcd-gacha

# 方式 C：pip（进入虚拟环境后）
pip install git+https://github.com/pzweuj/mcd-gacha
```

### 🔗 真实 MCP 模式（可选）

默认使用内置演示菜单（离线可玩）。若要体验**真实菜单与在线核价**：

1. 在 [麦当劳 MCP 开放平台](https://open.mcd.cn/mcp) 申请 MCP Token；
2. 配置 Token（三选一）：
   - 环境变量：`export MCD_MCP_TOKEN=你的Token`
   - 项目根 `.env` 写入：`MCD_MCP_TOKEN=你的Token`
   - 本地保存：`mcd-gacha config set-token 你的Token`
3. 配置门店（到店取餐，二选一）：
   - `mcd-gacha config set-store --city 深圳市`（自动选择最近门店）
   - `mcd-gacha config set-store --store-code 1421182`（固定门店；编号可用 `mcd-gacha stores --city 深圳市` 查询）
4. 安装 MCP 依赖并开抽：

```bash
pip install "mcd-gacha[mcp]"
mcd-gacha pull --real          # 有 Token 时也可省略 --real 直接体验
mcd-gacha stores               # 查询附近门店（选 storeCode 用）
```

MCP 接入细节（工具清单、调用流程、价格口径与安全设计）见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。

## 🕹️ 命令一览

| 命令 | 说明 |
|------|------|
| `mcd-gacha pull` | 单抽（`-b` 选卡池，`--budget` 定预算，`--real` 真实 MCP，`--json` 输出 JSON） |
| `mcd-gacha ten` | 十连（共享保底计数器） |
| `mcd-gacha reroll --slot N` | 重铸第 N 件（同品类替换，不耗保底） |
| `mcd-gacha order` | 下单最近一次组合（先抽卡，**下单时再确认地点与取餐方式**）：默认**试运行**并列出候选门店 + 取餐方式；`--confirm --store-code <编号> --take-way-code <堂食/外带>` 才真正提交 |
| `mcd-gacha banners` | 卡池一览与开放状态 |
| `mcd-gacha status` | 保底进度与生涯统计 |
| `mcd-gacha simulate` | 蒙特卡洛概率自证 |
| `mcd-gacha doctor` | 环境自检（Token 来源 / 门店 / MCP 连通性） |
| `mcd-gacha stores` | 查询附近门店（真实模式用） |
| `mcd-gacha config set-token` | 保存 MCP Token（仅存本地） |
| `mcd-gacha config set-store` | 保存门店（城市或门店编号） |

## 🏗️ 架构

```mermaid
flowchart LR
    CLI[CLI / rich 渲染] --> Engine[抽卡引擎<br/>概率 · 保底 · 组合生成]
    Engine --> Optimizer[预算优化<br/>0/1 背包 + 最优券]
    Engine --> DS{数据源抽象}
    DS -->|无 Token| Mock[内置演示快照<br/>离线可玩]
    DS -->|有 Token| MCP[麦当劳 MCP<br/>真实菜单与核价]
```

- **数据源抽象**：`MockDataSource`（内置快照）与 `McpDataSource`（真实 MCP）同协议，随时切换、失败自动回退；
- **组合生成**：四档稀有度对应四种策略，统一出口校验「券后实付 ≤ 预算」；
- **参数单一真源**：概率 / 卡池 / 预算集中在 `banners.json`，CLI 与网页演示页共用。

## 🛡️ 安全与合规

- **下单需显式确认，且先确认地点与取餐方式**：`mcd-gacha order` 默认只做**试运行**（dry-run，不产生订单）并列出候选门店与取餐方式；必须加 `--confirm`（可配 `--store-code` / `--take-way-code`）才会调用 `create-order`；命令只返回订单号与支付链接，**支付由用户在麦当劳官方渠道自行完成**，本项目不代付；
- **Token 安全**：Token 仅存本地（环境变量 / `.env` / 本地配置），不进版本库，示例配置只含环境变量占位符；
- **非官方声明**：本项目为第三方开源玩具，非麦当劳官方产品；请理性消费、快乐生活。

## 🚧 当前限制（诚实清单）

本项目遵循「文档不假装已完成」原则——以下是有意不做或尚未覆盖的部分：

**有意不做**

- ❄️ **不自动下单 / 不代付**：抽卡与核价默认全程只读；`order` 命令必须显式 `--confirm` 且只负责提交订单、回显支付链接——支付与退款一律走麦当劳官方渠道；
- 🎯 **不做营养/医疗建议**：热量数据仅供娱乐参考，不构成膳食建议；
- 🧮 **不做全量忌口系统**：组合生成不排除过敏原（麦当劳 MCP 未提供结构化过敏原字段），有严格忌口需求请以官方菜单标注为准。

**受上游能力限制**

- 📍 门店查询为城市级（麦当劳 MCP 不接受经纬度），无法按真实距离排序门店；
- 🍔 菜单随门店与时段实时变化，内置演示快照与实际菜单存在时间差（输出中已标注数据来源）；
- 💳 优惠券以账号实际可用为准；无券账号的「省」显示为 0（这是真实状态，不是 bug）。

**尚未完成（路线图内）**

- 🖼️ 分享卡 PNG 一键导出（SVG 原生支持；PNG 需可选依赖 cairosvg）；
- 📱 网页版移动端细节打磨（已响应式，持续优化）。

## 🤝 参与贡献

欢迎 Issue / PR：新卡池点子、文案梗、分享卡模板、真实 MCP 联调反馈都收。

**如果这个玩具让你会心一笑，点个 ⭐ Star 就是最好的打赏。**

## 📄 License

[MIT](LICENSE) © 2026 Mcd-Gacha contributors
