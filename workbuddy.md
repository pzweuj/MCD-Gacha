# WorkBuddy 开发对话上下文

本项目（Mcd-Gacha · 麦门抽卡模拟器）使用**腾讯 WorkBuddy 智能体**完成调研、设计、编码与测试。
以下为开发过程的对话上下文记录（按时间线整理）。

> 说明：本文件用于核验 WorkBuddy 联动活动资格；完整对话可由 WorkBuddy 导出后追加至本节。

## 开发时间线

### 2026-10-10 · D1：立项、调研与骨架落地

**1. 立项**
- 用户（项目作者）在 WorkBuddy 中提出参赛创意：「麦门吃土盲盒抽卡模拟器」——
  用二游抽卡机制（SSR/SR/R/N 稀有度 + 10 发保底）包装「中午吃什么」的选择困难症，
  基于麦当劳 MCP 的菜单与核价能力。

**2. 比赛规则调研（WorkBuddy 联网完成）**
- 抓取并分析官方仓库 `M-China/mcd-developer-innovation-challenge`：
  必须文件清单（README / CONTEST_DECLARATION / MCP_INTEGRATION / mcp-config.example.json / 源代码 / workbuddy.md）、
  Star 排名规则、10/25 截止、合规红线；
- 抓取 `M-China/mcd-mcp-server` 官方工具清单：query-meals、calculate-price、
  list-nutrition-foods、now-time-info、query-my-coupons、create-order 等 30+ Tools；
- 分析官方排行榜（10/10 快照）：头部为实用工具类，游戏化抽卡方向存在差异化空间。

**3. 方案设计（WorkBuddy 输出）**
- 确定三层架构：CLI（rich 渲染）→ 抽卡引擎（概率/保底/组合生成）→ 数据源抽象（mock/MCP 双实现）；
- 关键决策：内置演示快照让「无 Token 用户零配置可玩」；MCP 失败自动回退；
  官方 mcp SDK 作为可选 extra 隔离；概率透明化（内置 simulate 蒙特卡洛自证）。

**4. 编码实现（WorkBuddy 生成）**
- 核心模块：`engine.py`（保底引擎）、`generators.py`（四档组合策略：
  R=规整组合 / SR=经典正餐 / SSR=0/1 背包价值最大化 / N=抽象整活）、
  `optimizer.py`（背包 + 最优券）、`datasource/`（mock 实现）、
  `state.py`（保底计数持久化）、`reveal.py`（rich 开箱渲染）、`cli.py`（typer 命令）；
- 数据文件：`banners.json`（卡池/概率参数单一真源）、`mock_menu.json`（演示菜单快照）、
  `mock_prices.json`（券规则快照）。

**5. 测试与修复（WorkBuddy 执行）**
- 编写 39 项测试（保底不变量、预算约束、背包正确性、蒙特卡洛统计、状态持久化）；
- 实测修复：CLI 未加载本地状态导致保底计数被覆盖的缺陷、跨平台配置目录双层路径问题、
  组合多样性不足（改为软加权随机）、SR 档混入无主食组合的过滤缺失；
- 蒙特卡洛验证：SSR 有效出率 12.4%（基础 5% + 10 发硬保底），最大间隔恰好 10 抽。

**6. 交付物（D1）**
- 五件套文档 + 可运行 CLI（`mcd-gacha pull/ten/banners/status/simulate`）+ 39 项测试全绿；
- 后续里程碑：D3 开箱动画与分享卡、D4 真实 MCP 联调、D5 网页演示页、D6 文档定稿。

### 2026-10-10 · D4 提前完成：真实 MCP 联调

**7. 真实麦当劳 MCP 联调（WorkBuddy 联网实测 + 缺陷修复）**
- 通过官方 mcp SDK（mcp 2.3.0）接入 https://mcp.mcd.cn，实测 35 个真实工具；
- 打通全链路：门店解析（query-nearby-stores）→ 真实菜单（query-meals，139 个 SKU）
  → 抽卡组合生成 → 真实核价（calculate-price）→ 营养（list-nutrition-foods）；
- 实测发现并修复关键问题：
  1) 价格口径：活动类商品（canWithOrder=true）核价按原价，普通商品按现价
     ——数据源价格与核价对齐后，组合永不超预算；
  2) 商品实时售罄 → 引擎增加「生成→核价→重试」循环；
  3) 周边/限定人群/辅料（酱料）商品混入组合 → 增加过滤规则；
- 新增 `mcd-gacha stores`（门店查询）、`config set-store`（门店配置）与诊断工具
  `scripts/check_mcp.py`；MCP_INTEGRATION.md 同步全部实测结论。

**8. Skill 形态补强（对应用户反馈，WorkBuddy 完成）**
- 明确项目定位为「AI Skill + CLI 应用」双形态：SKILL.md 为交互层，Python 引擎为能力底座；
- WorkBuddy 产出 `SKILL.md`（Skill 定义：触发词、调用命令、JSON 字段说明、展示指引、合规红线），
  支持装入 WorkBuddy / Claude 等 Agent 后以「抽一发」「帮我决定午饭」等自然语言触发；
- README 同步增加「三种用法」说明（AI Skill / CLI / 在线试玩），并更新差异化说明。

### 2026-10-10 · 性能优化 / 重铸 / 展示层 / 网页版（WorkBuddy 全天冲刺）

**9. 性能优化与重铸玩法**
- 生成器重构：剪枝枚举 + 会话级候选缓存，大菜单下性能提升约 26 倍
  （真实模式十连从 15-20 秒降至 7 秒级）；
- 新增「重铸」玩法（`mcd-gacha reroll --slot N`）：同品类锁定重铸、优先升级/平价、
  不消耗保底——由竞品分析驱动（吸取实用功能，用二游"重铸"外壳重塑）；
- 修复：券弹性候选误杀（本地快筛改为券后价）、SSR 并列最优永远取第一个（近优带随机）。

**10. 展示层（开箱动画 + Hero GIF）**
- `play_reveal` 开箱动画：连接 → 蓄力 → 稀有度检定 → 金色传说（SSR）；
- `scripts/make_gif.py`：Pillow 逐帧渲染 Hero GIF（50 帧 / 6.7 秒 / 0.18MB，零外部工具）。

**11. 网页演示页（demo/，零依赖）**
- 单页应用：翻牌动画、四档稀有度光效、十连网格、保底 localStorage 持久化；
- JS 引擎与 Python 规则一致（node --test 8 项测试）；数据单一真源同步；
- GitHub Pages 工作流就绪（pages.yml）；浏览器自动化实测通过。

### 2026-10-10 · 文档定稿（D6）

**12. README_EN 英文版 + 文档核对**
- 英文版 README（面向国际社区）；中文版补充语言切换；
- design.md 补重铸算法与多端一致性说明；「当前限制」清单随完成度更新。

### 2026-10-10 · D6：补全「下单」闭环（order 命令）

**13. 下单能力接入（WorkBuddy 实现）**
- 背景：反馈「只抽卡不能下单，闭环缺失」；实测确认麦当劳 MCP 本身**具备完整下单能力**
  （`create-order` / `cancel-order` / `query-order` / `order-list`），此前未接入是项目侧的合规取舍；
- 新增 `mcd-gacha order`：提交最近一次**真实**抽卡组合 → 默认 **dry-run 试运行**，
  加 `--confirm` 才调用 `create-order`，返回订单号与支付链接（不代付）；
- 关键技术点：`create-order` 到店场景**必传 `takeWayCode`**，取值来自 `calculate-price`
  返回的 `data.takeWayList[].code`（2026-10-10 实测：`eat-in` 堂食 / `locker-in` 取餐柜）——
  为此在数据源层补了 `takeWayList` 解析；同时 `last_result` 新增 `data_source` 字段，用于拦截 mock 组合；
- 安全设计：三层闸门（默认 dry-run / 显式 `--confirm` / 只提交不代付）；仅支持到店自取，
  外送 / 得来速 / 团餐明确报错而非半成品提交；
- 验证：新增 14 项测试（安全闸门、参数构造、错误路径），全套 81 项测试通过；
  `ruff check` 与合规自检均通过；真实 MCP 端到端试运行已验证（未产生任何真实订单）。

**14. 下单前确认「地点 + 取餐方式」（WorkBuddy 实现）**
- 背景：产品思路是「先抽卡，下单时再向用户确认地点与取餐方式」——抽卡阶段不打扰，
  只在真正下单这一步做选择；
- 实现：`order` 命令新增 `--store-code`（换门店/地点）与 `--city`（切换候选门店搜索城市）；
  试运行（`order --json`）在原有组合 + 价格之外，新增返回 `stores`（候选门店，来自
  `query-nearby-stores`）、`take_way`（取餐方式候选，来自核价 `takeWayList`）、
  `take_way_default` 与 `confirm_hint`（可直接照抄的确认命令）；
- 数据源层新增 `TakeWay` 模型与 `take_way_options` / `default_take_way` 属性，
  把不同门店返回的 `title`/`name` 键名统一归一；
- 人机双形态：JSON 输出供 AI 消费，人类可读版把候选门店与取餐方式渲染成带序号的表格；
- 安全红线：新增「下单前必须先向用户确认地点与取餐方式」约束，不得代替用户拍板；
- 验证：新增 6 项测试（门店覆盖、候选输出、取餐方式选择/默认、确认提示用编号），
  全套 88 项测试通过；`ruff` 与合规自检通过；真实 MCP 试运行实测返回 5 家候选门店与
  「堂食/外带」两种取餐方式（未产生任何真实订单）。

**15. 交互收尾改为可点击选项 + 修复门店打烊崩溃（WorkBuddy 实现）**
- 背景：抽卡后用「要 十连 / 重铸 / 下单，说一声就行」收尾，**要求用户自己打字**，体验差；
- 实现：`SKILL.md` 新增「交互收尾（强制）」章节——抽卡/十连/重铸后**必须**给出
  可点击选项（`十连` / `重铸一件` / `下单` / `看保底进度`），并按结果动态微调
  （出 SSR → `再来一发`；mock 数据 → `下单` 换成 `切换真实菜单再抽`；
  十连结果 → 去掉 `十连`）；同时明确**不得标注「推荐」**，守住不诱导消费红线；
- 附带修复真 bug：门店打烊时 `query-meals` 返回业务错误（code=600057），
  而 `_open_source` 的回退兜底只包住 `start()`，运行期错误会直接中断抽卡——
  与文档「任何真实接口异常都会自动回退演示数据」的承诺不符。现增加启动后的
  菜单探测（结果被数据源缓存，无额外请求），并在回退时关闭会话避免连接泄漏；
- 验证：新增 `tests/test_source_fallback.py`（门店打烊回退 / 健康时保留真实源），
  全套 **90 项测试通过**；`ruff` 与合规自检通过；实测门店打烊时十连可正常回退完成。

### 2026-10-10 · 做减法：收敛为「纯 Skill」单形态

**16. 项目形态收敛（WorkBuddy 实现）**
- 背景：项目此前提供「AI Skill / CLI / 网页试玩」三种形态，功能面越铺越宽，
  与「这是一个 Skill」的定位不符；决定做减法，只保留 Skill 单形态；
- 删除：`demo/` 网页试玩站（含 JS 引擎与测试）、
  `docs/assets/hero-demo.gif` 与 `ui-initial.png` 演示素材、
  `scripts/build_demo_data.py`、`scripts/make_gif.py`、`tests/test_data_sync.py`（网页数据同步测试）；
- 保留：Python 引擎（`src/mcd_gacha/`）作为 Skill 的能力底座；CLI 从「独立产品」降级为
  「Skill 内核 / 进阶调试入口」，命令一览移入 README 折叠区；
- README 重写为单形态叙事：以「这是一个 AI Skill」开篇，删除网页试玩、三种用法与英文版链接，
  hero 图改用分享卡样例 SVG；**中英双语同步改写**（`README.md` + `README_EN.md`）
  并恢复双向语言切换链接，英文版同样只讲 Skill 单形态；
- 同步清理悬空引用：`pyproject.toml` 移除 `pillow` 依赖并重锁 `uv.lock`、
  `banners.py` 注释、`docs/design.md` 「多端一致性」章节改为「交互层（Skill）」、
  `docs/compliance.md` 去网页表述；
- 验证：删除后全套测试与合规自检通过，仓库跟踪文件从 64 个收敛到 49 个（含中英双语 README）。

## 工具使用说明

- 本项目的调研（联网抓取比赛规则与 MCP 文档）、架构设计、代码生成、测试编写、
  缺陷修复、文档撰写均在 WorkBuddy 中完成；
- 开发环境：Windows + Git Bash，Python 3.13（uv 管理），WorkBuddy 直接读写项目文件并执行测试命令。
