# 📋 泰拉瑞亚猫娘 — 逐文件说明

> **neko_terraria v0.1.0** — 让 AI 猫娘作为独立玩家加入泰拉瑞亚世界
>
> 双轨任务调度 · 复杂任务大脑 · mod 合成推演 · 自主行为 v2
>
> *最后更新: 2026-07-31*

> **版本** `v0.1.0` · **平台** Windows / tModLoader · **SDK** N.E.K.O v0.8.3.2+ · **入口点** 41+

---

## 目录

- [项目结构总览](#项目结构总览)
- [`__init__.py` — 主插件类](#__init__py--主插件类)
- [`entries/` — 入口点层](#entries--入口点层)
- [`llm/` — LLM 工具层](#llm--llm-工具层)
- [`bridge/` — 游戏交互桥](#bridge--游戏交互桥)
- [`core/` — 核心服务](#core--核心服务)
- [`autonomous/` — 自主行为大脑](#autonomous--自主行为大脑)
- [`perception/` / `state/` — 感知与状态](#perception--state--感知与状态)
- [`executor/` / `polish/` — 执行增强与人性化](#executor--polish--执行增强与人性化)
- [`mod/` — tModLoader 服务端 mod](#mod--tmodloader-服务端-mod)
- [`surfaces/` / `ui/` — 前端 UI](#surfaces--ui--前端-ui)
- [`data/` / `docs/` / `i18n/`](#data--docs--i18n)
- [数据流图](#数据流图)
- [入口点统计](#入口点统计)
- [开发规则](#开发规则)
- [版本历史](#版本历史)

---

## 项目结构总览

<details>
<summary><b>📂 点击展开完整目录树</b></summary>

```
neko_terraria/
│
├── 📄 __init__.py                 # ★ 主插件类 NTerrariaPlugin (~35行)
├── ⚙️ plugin.toml                 # 插件元数据与运行时配置
├── 📦 pyproject.toml              # Python 包元数据与依赖
│
├── 🎯 entries/                    # N.E.K.O 入口点层 (4 文件)
│   ├── lifecycle_mixin.py         #   生命周期 + 核心服务初始化
│   ├── ui_actions.py              #   6 个 @ui.action 面板按钮
│   └── ui_context.py              #   2 个 @ui.context 状态上下文
│
├── 🔧 llm/                        # LLM 工具层 (3 文件, ~26 个 @llm_tool)
│   ├── goal_tools.py              #   目标/打断/聊天工具
│   ├── action_tools.py            #   动作/查询/任务/配方/长期任务工具
│   └── prompts.py                 #   猫娘人格与边界提示词
│
├── 🌉 bridge/                     # 游戏交互桥 (24 文件)
│   ├── agent.py                   #   TerrariaAgent 双轨调度中枢
│   ├── connection.py              #   双通道连接 + mod 请求原子化
│   ├── raw_bot.py                 #   Terraria-Bot 协议登录/聊天/传送
│   ├── protocol.py                #   Terraria 协议包构造
│   ├── mod_link.py                #   tModLoader mod 接口封装
│   ├── mod_registry.py            #   mod 物品注册缓存
│   ├── item_npc_dict.py           #   原版物品/NPC ID 映射
│   │
│   ├── task_brain.py              #   复杂任务大脑 (想→处理→做)
│   ├── task_chain.py              #   任务链引擎 (Goal → 多步执行)
│   ├── world_model.py             #   虚拟背包世界推演
│   ├── reasoner.py                #   缺东西时的补救推理
│   ├── recipe_book.py             #   mod 真实配方书
│   ├── planner.py                 #   分段路径/垂直攀爬规划
│   ├── executor.py                #   单槽位任务执行器
│   ├── coordinator.py             #   任务协调中枢
│   ├── intent.py                  #   意图识别 (长期 vs 有限)
│   ├── longterm.py                #   长期任务管理器
│   ├── standing_jobs.py           #   长期任务行为库
│   │
│   ├── mining.py                  #   挖矿引擎
│   ├── combat.py                  #   真人级战斗引擎
│   ├── equipment.py               #   装备管理
│   ├── inventory_ops.py           #   物品/箱子操作
│   ├── capability.py              #   能力评估 (钩锁/垫土/镐子)
│   └── __init__.py                #   bridge 包统一导出
│
├── ⚙️ core/                       # 核心服务 (3 文件)
│   ├── client.py                  #   进程内 Agent 轻量客户端
│   ├── service.py                 #   状态快照 + nudge 推送
│   └── vision.py                  #   截图节流推 LLM
│
├── 🧠 autonomous/                 # 自主行为大脑 v2 (4 文件)
│   ├── brain.py                   #   三层思考 + 自主决策
│   ├── internal_state.py          #   能量/无聊/情绪状态
│   ├── motivation.py              #   5 种动机竞争
│   └── event_bus.py               #   模块间事件总线
│
├── 👁️ perception/                 # 感知模块 (2 文件)
│   ├── game_state.py              #   游戏态势快照
│   └── vision.py                  #   视觉感知入口
│
├── 💾 state/                      # 状态缓存 (1 文件)
│   └── store.py                   #   UI 可读的状态缓存
│
├── ⚡ executor/                   # 执行增强 v2 (2 文件)
│   ├── chain_engine.py            #   行为链引擎
│   └── parallel.py                #   多层并行执行器
│
├── ✨ polish/                     # 人性化打磨 v2 (4 文件)
│   ├── human_timing.py            #   人类化时序
│   ├── imperfections.py           #   瑕疵注入
│   ├── attention.py               #   注意力漂移
│   └── habits.py                  #   个人习惯/性格种子
│
├── 🎮 mod/                        # tModLoader 服务端 mod
│   └── NekoTerrariaLink/
│       ├── NekoTerrariaLink.cs    #   mod 主逻辑 (状态/动作/配方/导航)
│       ├── NekoTerrariaLink.csproj
│       └── Json.cs                #   轻量 JSON 解析器
│
├── 🖥️ surfaces/                   # Hosted UI 面板入口
│   ├── quickstart.tsx             #   快速开始面板
│   └── guide.tsx                  #   使用指南面板
│
├── 🎨 ui/                         # UI 组件实现
│   ├── quickstart.tsx             #   快速开始完整组件
│   └── panel.tsx                  #   状态子面板组件
│
├── 📚 docs/                       # 用户文档
│   └── quickstart.md              #   前端 UI 帮助文档
│
├── 🌍 i18n/                       # 国际化
│   └── zh-CN.json                 #   中文语言包
│
├── 📁 data/                       # 运行时数据
│   ├── config/settings.json       #   配置占位文件 (当前未生效)
│   └── mod_items/                 #   mod 物品缓存目录
│
└── 📄 README.md                   # 项目概览 (待补充)
```

</details>

---

## `__init__.py` — 主插件类

**职责**: N.E.K.O SDK 入口，通过 Mixin 多重继承注入全部功能，初始化核心服务与属性。

```python
@neko_plugin                           # ← 无参数装饰器
class NTerrariaPlugin(
    NekoPluginBase,                    # ★ 必须是第一个基类

    # 生命周期 & UI
    LifecycleMixin,                    # on_load / on_unload / 核心服务初始化
    UiActionsMixin,                    # 6 个 @ui.action 面板按钮
    UiContextMixin,                    # 2 个 @ui.context 状态上下文

    # LLM 工具层 (2 Mixin, ~26 个 @llm_tool)
    GoalToolsMixin,
    ActionToolsMixin,
):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.logger = self.enable_file_logging(log_level="INFO")

        # 所有自定义属性在主 __init__ 初始化 (Mixin 的 __init__ 不会被调用)
        self._agent = None
        self._autonomous_brain = None
        self._config: Dict[str, Any] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._init_core_services()       # 初始化 Agent / 自主大脑 / Service
```

**关键属性**:

| 属性 | 类型 | 初始化位置 | 说明 |
|:-----|:-----|:-----------|:-----|
| `_agent` | `TerrariaAgent \| None` | `__init__` | 游戏交互中枢 |
| `_autonomous_brain` | `AutonomousBrain \| None` | `__init__` | 自主行为大脑 |
| `_config` | `dict` | `_init_core_services()` | 运行时配置 |
| `_loop` | `EventLoop \| None` | `__init__` | 事件循环引用 |
| `_service` | `TerrariaService` | `_init_core_services()` | 状态快照 + nudge 服务 |

---

## `entries/` — 入口点层

N.E.K.O SDK 入口点集中声明处。所有 Mixin 只含方法 + 类常量，**不含 `__init__`**。

| 文件 | Mixin 类 | 入口点 | 职责 |
|:-----|:---------|:------:|:-----|
| **lifecycle_mixin.py** | `LifecycleMixin` | - | 生命周期钩子 + 核心服务初始化 (`_init_core_services` / `_load_config`) |
| **ui_actions.py** | `UiActionsMixin` | **6** `@ui.action` | 前端面板按钮：连接 / 状态 / 背包 / 箱子 / 日志 / 断开 |
| **ui_context.py** | `UiContextMixin` | **2** `@ui.context` | 状态上下文：`quickstart` (运行态大全) / `guide` (引导+mod列表) |

### `ui_actions.py` 按钮列表

| ID | 按钮文本 | 对应方法 | 说明 |
|:--:|:---------|:---------|:-----|
| `nt_connect` | 连接游戏 | `act_connect` | 登录泰拉瑞亚世界 |
| `nt_status` | 猫娘状态 | `act_status` | 刷新 HP/MP/位置等状态 |
| `nt_inventory` | 查看背包 | `act_inventory` | 读取手持栏/装备栏/主背包 |
| `nt_chests` | 箱子清单 | `act_chests` | 枚举世界箱子坐标与内容物 |
| `nt_log` | 行为日志 | `act_log` | 读取近期行为记录 |
| `nt_stop` | 断开 | `act_stop` | 让猫娘退出世界 |

---

## `llm/` — LLM 工具层

供 AI 自然语言调用的工具集合，约 **26 个 `@llm_tool`**。

| 文件 | Mixin 类 | 工具数 | 工具列表 |
|:-----|:---------|:------:|:---------|
| **goal_tools.py** | `GoalToolsMixin` | **3** | `terraria_set_goal` / `terraria_interrupt` / `terraria_chat` |
| **action_tools.py** | `ActionToolsMixin` | **~23** | `terraria_warp` / `terraria_mine` / `terraria_craft` / `terraria_give` / `terraria_use_item` / `terraria_list_inventory` / `terraria_where_is` / `terraria_find_items` / `terraria_store` / `terraria_take` / `terraria_task` / `terraria_assess` / `terraria_recipe` / `terraria_why` / `terraria_task_status` / `terraria_keep_doing` / `terraria_stop_doing` / `terraria_climb` / `terraria_plan_climb` / `terraria_capabilities` |
| **prompts.py** | - | - | `TERRARIA_PROMPT` / `COMMON_RULES` 猫娘人格提示词 |

### 工具功能域

| 域 | 代表工具 | 说明 |
|---|:---------|:-----|
| 目标管理 | `terraria_set_goal` / `terraria_interrupt` | 下达目标、随时打断 |
| 物品交互 | `terraria_give` / `terraria_store` / `terraria_take` / `terraria_where_is` | 给玩家、存箱子、取箱子、定位 |
| 动作执行 | `terraria_mine` / `terraria_craft` / `terraria_warp` / `terraria_climb` | 挖矿、合成、传送、攀爬 |
| 复杂任务 | `terraria_task` / `terraria_assess` | 多步任务执行 / 只评估不做 |
| 长期任务 | `terraria_keep_doing` / `terraria_stop_doing` | 跟着我 / 一直挖矿 / 停止 |
| 信息查询 | `terraria_recipe` / `terraria_find_items` / `terraria_capabilities` | 配方、物品、能力 |

---

## `bridge/` — 游戏交互桥

与泰拉瑞亚世界通信的核心层，按职责分为 **协议与连接**、**任务与大脑**、**专业引擎** 三组。

### 协议与连接

| 文件 | 类名 | 核心职责 |
|:-----|:-----|:---------|
| **connection.py** | `Connection` | Terraria-Bot TCP + tModLoader mod TCP 双通道；mod 请求原子化 (`asyncio.Lock`)；`req_id` 关联回执防串线 |
| **protocol.py** | `PacketManager` | Terraria 协议包构造 (长度/序号/类型/数据) |
| **raw_bot.py** | `RawBot` | 免客户端登录、游戏内聊天、传送、召唤物品、攻击 NPC |
| **mod_link.py** | `ModLink` | 封装 mod 命令：移动/放方块/挖方块/钩锁/合成/装备/背包/箱子/导航/扫描/配方/状态 |
| **mod_registry.py** | `ModItemRegistry` | 枚举 mod 物品并缓存到 `data/mod_items/`，按 mod 分组，中英对照 + tags |
| **item_npc_dict.py** | - | 原版物品/NPC ID 常量表 + `item_id()` / `npc_id()` 解析函数 |

### 任务与大脑

| 文件 | 类名 | 核心职责 |
|:-----|:-----|:---------|
| **agent.py** | `TerrariaAgent` | 双轨调度中枢：启动 Agent、状态轮询、复杂任务入口、导航/攀爬/物品操作代理 |
| **task_brain.py** | `TaskBrain` | 复杂任务大脑：想(评估) → 处理(规划) → 做(执行)；含 `Assessment` / `Plan` |
| **task_chain.py** | `TaskChain` | 任务链引擎：`Goal` 数据结构 + `run_loop` + `run_one` |
| **world_model.py** | `WorldModel` | 虚拟背包推演，让后续步骤看到前面步骤的产出 |
| **reasoner.py** | `Reasoner` | 缺东西时的补救推理：身上 → 箱子 → 合成 → 现挖 → 求助 |
| **recipe_book.py** | `RecipeBook` | mod 真实配方缓存、中英索引、可用性判断、反查用途 |
| **planner.py** | `Planner` | 分段路径规划，深坑/垂直移动拆成逐段落脚点 |
| **executor.py** | `TaskExecutor` | 单槽位任务执行器：优先级仲裁、取消、快照 |
| **coordinator.py** | `TaskCoordinator` | 一句话统一入口：判断是长期/有限/停止，派发双轨 |
| **intent.py** | - | 意图识别逻辑："挖10个铁" 是有限任务，"挖铁" 是长期任务 |
| **longterm.py** | `LongTermManager` | 长期任务生命周期、让路(yield)、停止 |
| **standing_jobs.py** | `StandingJobs` | 长期任务行为库：跟着我、一直挖、守着 |

### 专业引擎

| 文件 | 类名 | 核心职责 |
|:-----|:-----|:---------|
| **mining.py** | `MiningEngine` | 导航到矿点、循环挖掘、可被中断切换目标 |
| **combat.py** | `CombatEngine` | 走位拉扯、垫土、钩锁、黑名单、基于 mod 状态决策 |
| **equipment.py** | `EquipmentManager` | 自动穿戴、使用、转交（丢地上给玩家） |
| **inventory_ops.py** | `InventoryOps` | 物品/箱子操作：定位、存取、转交、使用；处理三大类背包 |
| **capability.py** | `Capability` | 能力评估：钩锁、垫土、镐子、绳梯；预判能否到达目标 |

---

## `core/` — 核心服务

| 文件 | 类名 | 构造函数 | 核心职责 |
|:-----|:-----|:---------|:---------|
| **client.py** | `AgentClient` | `AgentClient(agent)` | 进程内轻量客户端，不走网络 |
| **service.py** | `TerrariaService` | `TerrariaService(agent, cfg, push_message)` | 状态快照周期推 + 低血/待命 nudge |
| **vision.py** | `VisionBridge` | `VisionBridge(cfg, push_message)` | 截图采集节流 + 推 LLM (`ai_behavior=read`) |

---

## `autonomous/` — 自主行为大脑

| 文件 | 类名 | 核心功能 |
|:-----|:-----|:---------|
| **brain.py** | `AutonomousBrain` | 三层思考（状态 tick / 快速思考 / 深度思考）+ 事件驱动打断 + 自主执行 |
| **internal_state.py** | `InternalState` | 能量/无聊/情绪零 LLM 成本演变 |
| **motivation.py** | `MotivationSystem` | 5 种动机竞争：采集 / 战斗 / 探索 / 社交 / 舒适 |
| **event_bus.py** | `EventBus` | 模块间解耦通信，指令打断走这里 |

**启动流程**:

```
on_load() → _init_core_services() → AutonomousBrain(agent, cfg)
                                       ↓
                              autonomous_brain.start()
                                       ↓
                        ┌─────────────────────────────┐
                        │ _state_tick_task (每1s)     │ ← Layer 1
                        │ _fast_think_task (每5s)     │ ← Layer 2
                        │ _deep_think_task (30-90s)   │ ← Layer 3
                        └─────────────────────────────┘
```

---

## `perception/` / `state/` — 感知与状态

| 文件 | 类名 | 核心功能 |
|:-----|:-----|:---------|
| **perception/game_state.py** | `GameStatePerception` | 读 mod 状态快照，构建猫娘可理解的游戏态势 |
| **perception/vision.py** | `VisualPerception` | 视觉感知入口，接入 `core/vision` 节流后喂 LLM |
| **state/store.py** | `StateStore` | 插件自身状态缓存，供 UI context 读取 |

---

## `executor/` / `polish/` — 执行增强与人性化

### executor/

| 文件 | 类名 | 核心功能 |
|:-----|:-----|:---------|
| **chain_engine.py** | `ChainEngine` | 行为链引擎：序列动作编排与条件分支 |
| **parallel.py** | `ParallelExecutor` | 多层并行执行器：移动/攻击/垫土按优先级并行 |

### polish/

| 文件 | 类名 | 核心功能 |
|:-----|:-----|:---------|
| **human_timing.py** | `HumanTiming` | 反应延迟正态分布 + 动作时长变异 |
| **imperfections.py** | `ImperfectionInjector` | 微小抖动、不完美停顿，增强自然感 |
| **attention.py** | `AttentionDrift` | 注意力漂移：分心与重新聚焦 |
| **habits.py** | `PersonalHabits` | 个人习惯与性格种子 (`talkative` / `brave` / `curious`) |

---

## `mod/` — tModLoader 服务端 mod

| 文件 | 说明 |
|:-----|:-----|
| **NekoTerrariaLink/NekoTerrariaLink.cs** | mod 主逻辑：TCP 监听 9877 端口；处理移动/放方块/挖方块/钩锁/合成/装备/背包/箱子/导航/扫描/配方/状态；带坑洞规避、搭土、钩锁飞越、线程安全 `Send` |
| **NekoTerrariaLink/Json.cs** | 轻量 JSON 解析/序列化器，避免外部依赖 |
| **NekoTerrariaLink/NekoTerrariaLink.csproj** | tModLoader mod 项目文件 |

---

## `surfaces/` / `ui/` — 前端 UI

| 文件 | 说明 |
|:-----|:-----|
| **surfaces/quickstart.tsx** | `plugin.toml` 注册的快速开始面板入口，导出 `ui/quickstart.tsx` |
| **surfaces/guide.tsx** | `plugin.toml` 注册的使用指南面板入口，展示引导文本 + mod 列表 |
| **ui/quickstart.tsx** | 快速开始完整组件：HP/MP/目标/操作按钮/手持栏/装备栏/背包/箱子/日志/mod 列表 |
| **ui/panel.tsx** | 状态子面板组件：HP/MP/目标 + 三大类物品，被 quickstart 复用 |

---

## `data/` / `docs/` / `i18n/`

| 文件/目录 | 说明 |
|:----------|:-----|
| **docs/quickstart.md** | 前端 UI 帮助文档（快速开始、面板按钮、语音指令、配置说明、故障排查） |
| **i18n/zh-CN.json** | 中文语言包：面板标题、按钮文本、状态标签 |
| **data/config/settings.json** | 配置占位文件 (`auto_register_mods` / `stream_screenshots` 等)，**当前未被代码读取** |
| **data/mod_items/** | mod 物品缓存目录，按 mod 分 JSON 文件 |

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户 / AI 输入                                │
│            语音/聊天指令 / UI 按钮 / 自主大脑决策                      │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     NTerrariaPlugin (主类)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ llm/         │  │ entries/     │  │  _init_core_services()   │   │
│  │ @llm_tool    │  │ @ui.action   │  │  → TerrariaAgent         │   │
│  │ (~26个)      │  │ @ui.context  │  │  → AutonomousBrain       │   │
│  └──────┬───────┘  └──────┬───────┘  │  → TerrariaService       │   │
│         │                 │          └───────────┬──────────────┘   │
│         │                 │                      │                  │
│         ▼                 ▼                      ▼                  │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                   bridge/ 游戏交互桥                         │    │
│  │  agent → task_brain → task_chain → executor → mod_link     │    │
│  │  world_model → reasoner → recipe_book → planner            │    │
│  │  mining / combat / equipment / inventory_ops               │    │
│  └─────────────────────────┬───────────────────────────────────┘    │
└────────────────────────────┼────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        通信层                                        │
│   Terraria-Bot TCP 7777  ────────▶  独立玩家登录                      │
│   tModLoader mod TCP 9877 ───────▶  状态/移动/合成/装备/导航          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 入口点统计

| 类型 | 数量 | 分布位置 | 说明 |
|:----:|:----:|:---------|:-----|
| `@neko_plugin` | **1** | `__init__.py` | 主插件类 |
| `@lifecycle` | **2** | `entries/lifecycle_mixin.py` | `startup` / `shutdown` |
| `@ui.action` | **6** | `entries/ui_actions.py` | 前端面板按钮 |
| `@ui.context` | **2** | `entries/ui_context.py` | 状态上下文 |
| `@llm_tool` | **~26** | `llm/goal_tools.py` + `llm/action_tools.py` | AI 可调用工具 |
| **总计** | **~37** | **5 个 Mixin 文件** | |

---

## 开发规则

本插件遵循 N.E.K.O SDK Mixin 架构规范（详见 `archive/PLUGIN_ARCHITECTURE_GUIDE.md`）：

| 规则 | 说明 | ❌ 错误示例 |
|:-----|:-----|:-----------:|
| Mixin 不含 `__init__` | 所有属性在主类 `__init__` 初始化 | `class Mixin: def __init__():` |
| `@neko_plugin` 无参 | SDK 装饰器不接受参数 | `@neko_plugin(id="x")` |
| `@lifecycle` 用 `id=` | 有效值: `startup` / `shutdown` | `@lifecycle(event="load")` |
| 服务传 `self` | 统一传入 plugin 实例 | `Service(config)` |
| 变量名 `_streaming` 等 | 下划线前缀私有属性 | `self.is_streaming` |
| 修改后删 `__pycache__` | 旧字节码会导致改动不生效 | 直接重启 |

### 添加新的 LLM 工具

```python
# 1. 在 llm/ 创建或编辑 Mixin
from plugin.sdk.plugin import llm_tool, Ok

class MyToolsMixin:
    @llm_tool(name="terraria_my_action", description="我的自定义动作", parameters={
        "type": "object",
        "properties": {"param": {"type": "string", "description": "参数说明"}},
        "required": ["param"]
    })
    async def llm_my_action(self, param: str, **_):
        return Ok({"output": f"已执行 {param}"})

# 2. 在 __init__.py 导入并加入 NTerrariaPlugin 继承列表
# 3. 删除 __pycache__ 后重启 N.E.K.O
```

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|:----:|:----:|:---------|
| **v0.1.0** | 2026-07-31 | 入口点合规审查；mod 通信 req_id 关联防串线；UI 帮助文档重写；FILES.md 补全 |
| **v0.0.x** | 2026-07-30 | 双轨任务调度；复杂任务大脑 (world_model + reasoner + recipe_book)；mod 物品合成推演；自主行为 v2 |

---

> **🐱 泰拉瑞亚猫娘** — 让 AI 成为会思考、会动手、会撒娇的队友
>
> [📘 N.E.K.O 文档](https://project-neko.online/plugins/) ·
> [🛠️ 插件开发指南](https://project-neko.online/plugins/quick-start) ·
> [📐 架构规范](./archive/PLUGIN_ARCHITECTURE_GUIDE.md)
>
> *Made with ❤️ by N.E.K.O Community*
