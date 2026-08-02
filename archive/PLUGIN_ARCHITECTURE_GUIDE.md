# 泰拉瑞亚猫娘 (neko_terraria) 插件架构规范

> 本规范仅适用于 **neko_terraria** 插件（AI 猫娘作为独立玩家加入泰拉瑞亚世界）。
> 基于 N.E.K.O SDK v2 官方行为 + 本项目实际调试经验整理。
> **重要**：N.E.K.O. SDK 不原生支持 Mixin `__init__` 链式调用，需遵循本文规范。

---

## 一、项目总览

```
neko_terraria/
├── __init__.py              # 插件主类 NTerrariaPlugin (~36行) ★ 所有属性在此初始化
├── plugin.toml              # 插件配置（[neko_terraria] 段为唯一生效配置源）
├── pyproject.toml           # 构建/打包配置
│
├── entries/                 # N.E.K.O 入口点层（3 个 Mixin）
│   ├── __init__.py          # 统一导出
│   ├── lifecycle_mixin.py   # @lifecycle startup/shutdown + 核心服务初始化
│   ├── ui_actions.py        # 6 个 @ui.action（前端面板按钮）
│   └── ui_context.py        # 2 个 @ui.context（状态上下文推送）
│
├── llm/                     # LLM 工具层 + 猫娘人格
│   ├── __init__.py
│   ├── goal_tools.py        # @llm_tool：目标/评估/任务/攀爬（含多步任务）
│   ├── action_tools.py      # @llm_tool：挖矿/合成/给予/移动/背包/配方等
│   └── prompts.py           # 人格提示词
│
├── bridge/                  # 游戏交互桥（24 个 .py）
│   ├── agent.py             # TerrariaAgent：连接/启动/停止/状态
│   ├── connection.py        # TCP 通信（req_id 双向关联防串线）
│   ├── task_brain.py        # 任务大脑：想→处理→做
│   ├── task_chain.py        # 行为链串行执行
│   ├── recipe_book.py       # mod 配方书与合成推演
│   ├── world_model.py       # 世界模型
│   ├── reasoner.py          # 推理/补救
│   └── ...                  # 挖矿/战斗/装备/导航引擎
│
├── core/                    # 核心服务（状态快照、nudge、视觉）
├── autonomous/              # 自主行为大脑 v2：三层思考 + 动机 + 事件总线
├── perception/  state/      # 游戏态势感知 + 状态缓存
├── executor/    polish/     # 行为链/并行执行 + 人性化打磨
│
├── mod/                     # tModLoader 服务端 mod (C#)：NekoTerrariaLink
├── surfaces/    ui/         # 前端 Hosted UI 面板（quickstart / guide）
├── data/        i18n/       # 运行时缓存 / 语言包（注：data/config/settings.json 为死配置）
└── docs/        archive/    # 帮助文档 / 归档文档
```

---

## 二、`__init__.py` 标准写法

### 2.1 核心原则

| 规则 | 说明 |
|------|------|
| **所有属性在 `__init__` 初始化** | 不在 Mixin 的 `__init__` 中设置（Mixin 的 `__init__` 不会被调用） |
| **`@neko_plugin` 不带参数** | SDK 签名就是无参装饰器 |
| **不导入 `PluginContext`** | SDK 不导出此类 |
| **`@lifecycle` 用 `id=`** | 不是 `event=`，有效值: `startup` / `shutdown` |
| **服务统一传 `self`** | 所有服务/引擎构造函数接受 plugin 实例 |

### 2.2 本项目的真实写法

```python
"""neko_terraria：AI 猫娘作为独立玩家加入泰拉瑞亚世界的 N.E.K.O 插件。"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from plugin.sdk.plugin import NekoPluginBase, neko_plugin

from .entries.lifecycle_mixin import LifecycleMixin
from .entries.ui_actions import UiActionsMixin
from .entries.ui_context import UiContextMixin
from .llm.goal_tools import GoalToolsMixin
from .llm.action_tools import ActionToolsMixin


@neko_plugin  # ← 不带参数！
class NTerrariaPlugin(
    NekoPluginBase,
    LifecycleMixin,
    UiActionsMixin,
    UiContextMixin,
    GoalToolsMixin,
    ActionToolsMixin,
):
    def __init__(self, ctx):
        super().__init__(ctx)
        self.logger = self.enable_file_logging(log_level="INFO")

        # ★ 所有自定义属性在主 __init__ 初始化
        self._agent = None
        self._autonomous_brain = None
        self._config: Dict[str, Any] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        self._init_core_services()
```

---

## 三、Mixin 文件规范（★ 关键）

### 3.1 核心规则

```
❌ 错误：Mixin 中定义 __init__
✅ 正确：Mixin 只包含方法 + 类常量
```

**原因**：`NekoPluginBase.__init__` 不链式调用 Mixin 的 `__init__`，混合类的 `__init__` 永远不会被执行。

### 3.2 lifecycle_mixin.py（正确写法）

```python
"""生命周期 + 核心服务初始化"""

from plugin.sdk.plugin import lifecycle


class LifecycleMixin:
    """★ 只包含方法，不包含 __init__"""

    def _init_core_services(self):
        """核心服务初始化（由主 __init__ 调用）"""
        from ..bridge.agent import TerrariaAgent

        # ★ 服务统一传 self (plugin 实例)
        self._agent = TerrariaAgent(self)
        # 自主大脑等按需在此构造

    @lifecycle(id="startup")  # ★ 用 id= 不是 event=
    async def on_load(self) -> None:
        self._config = self._load_config()  # 读 plugin.toml 的 [neko_terraria]
        await self._agent.connect_if_needed()

    @lifecycle(id="shutdown")
    async def on_unload(self) -> None:
        if self._agent is not None:
            await self._agent.stop()
```

---

## 四、Decorator 正确用法速查

| 装饰器 | 正确写法 | 错误写法 |
|--------|---------|---------|
| `@neko_plugin` | `@neko_plugin` (无参) | `@neko_plugin(id="...")` ❌ |
| `@lifecycle` | `@lifecycle(id="startup")` | `@lifecycle(event="load")` ❌ |
| `@lifecycle` | `@lifecycle(id="shutdown")` | `@lifecycle(event="unload")` ❌ |
| `@ui.action` | `@ui.action(id="nt_connect", text="连接游戏")` | 正确 |
| `@ui.context` | `@ui.context(id="quickstart")` | 正确 |
| `@llm_tool` | `@llm_tool(name="terraria_mine", description="...", parameters={...})` | 正确 |
| 导入 | `from plugin.sdk.plugin import NekoPluginBase, neko_plugin` | `PluginContext` 不存在 ❌ |

### 本项目的入口点（真实统计）

| 类型 | 数量 | 位置 |
|------|------|------|
| `@neko_plugin` | 1 | `__init__.py` |
| `@lifecycle` | 2 | `entries/lifecycle_mixin.py` (`startup` / `shutdown`) |
| `@ui.action` | 6 | `entries/ui_actions.py`（连接游戏/猫娘状态/查看背包/箱子清单/行为日志/断开） |
| `@ui.context` | 2 | `entries/ui_context.py` (`quickstart` / `guide`) |
| `@llm_tool` | ~26 | `llm/goal_tools.py` + `llm/action_tools.py` |
| **总计** | **~37** | **5 个 Mixin 文件** |

---

## 五、服务 / 引擎初始化规则

| 组件 | 正确 | 错误 |
|------|------|------|
| TerrariaAgent | `TerrariaAgent(self)` | `TerrariaAgent()` / `TerrariaAgent(config)` ❌ |
| AutonomousBrain | `AutonomousBrain(self)` | `AutonomousBrain(self._config)` ❌ |
| 其它 bridge 引擎 | 统一传入 `self` 或 `self._agent` | 传 `config` / 多参 ❌ |

---

## 六、变量名规范

| 变量 | 正确命名 | 说明 |
|------|---------|------|
| 猫娘 Agent | `self._agent` | 主类中存储，UI 操作经它调用 |
| 自主大脑 | `self._autonomous_brain` | 长期行为决策 |
| 配置字典 | `self._config` | 来自 `plugin.toml` 的 `[neko_terraria]` |
| 事件循环 | `self._loop` | 异步任务调度 |

---

## 七、mod 通信规范（本项目特有）

- 通信分两条 TCP 通道：`Terraria-Bot` 服务端（默认 `127.0.0.1:7777`）与 tModLoader mod 接口（默认 `127.0.0.1:9877`）。
- `bridge/connection.py` 的 `request_mod` 必须注入自增 `req_id`，并校验回执中的 `req_id` 匹配，防止多线程/后台任务回执串线。
- C# 端 `NekoTerrariaLink` 的所有 `Send*` 方法透传 `req_id`，且 `Send` 写流需加 `lock(_lock)` 防止字节交错。
- **唯一生效配置在 `plugin.toml` 的 `[neko_terraria]` 段**；目录下的 `data/config/settings.json` 当前未被代码读取，属遗留死配置，改动无效。

---

## 八、新增功能适配流程

```
1. 创建 entries/ 或 llm/ 下的新 Mixin（只含方法，不含 __init__）
   ↓
2. 在对应包的 __init__.py 添加导入和 __all__
   ↓
3. 在主 __init__.py 添加 Mixin 导入和继承
   ↓
4. 如需新属性，在主 __init__.py 的 __init__ 中初始化
   ↓
5. 删除 __pycache__ 后重启 N.E.K.O 验证加载
```

### 添加一个新的 LLM 工具示例

```python
# llm/my_tools.py
from plugin.sdk.plugin import llm_tool, Ok

class MyToolsMixin:
    @llm_tool(name="terraria_my_action", description="我的自定义动作", parameters={
        "type": "object",
        "properties": {"param": {"type": "string", "description": "参数说明"}},
        "required": ["param"]
    })
    async def llm_my_action(self, param: str, **_):
        return Ok({"output": f"已执行 {param}"})
```

```python
# __init__.py：导入并加入 NTerrariaPlugin 继承列表后，删除 __pycache__ 重启
```

---

## 九、常见错误速查

| 错误 | 原因 | 修复 |
|------|------|------|
| `TypeError: lifecycle() got unexpected keyword 'event'` | 用了 `event=` | 改为 `id=` |
| `TypeError: neko_plugin() got unexpected keyword 'id'` | 传了参数 | 移除所有参数 |
| `AttributeError: '_agent'` | Mixin `__init__` 未执行 | 属性移到主 `__init__` |
| `ModuleNotFoundError` | 导入路径层级错误 | 检查相对导入 `..bridge.xxx` |
| `TypeError: __init__() missing 'plugin'` | 服务没传 self | 改为 `Xxx(self)` |
| `ImportError: cannot import 'PluginContext'` | SDK 不导出此类 | 移除导入 |
| mod 回执串线 / 状态错乱 | 无 req_id 关联 + 写流未加锁 | 注入并校验 `req_id`，`Send` 加 `lock` |
| 改动不生效 | 旧 `.pyc` 残留 | 删除 `__pycache__` 后重启 |

---

*最后更新: 2026-07-31 — 重写为 neko_terraria 专属规范（替换原 VR 指南内容）*
