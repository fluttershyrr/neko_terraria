"""生命周期：启动 Agent + 自主大脑，关闭时清理。"""

import asyncio
from typing import Any, Dict, Optional

from plugin.sdk.plugin import lifecycle

from ..bridge.agent import TerrariaAgent
from ..autonomous.brain import AutonomousBrain
from ..core.service import TerrariaService


class LifecycleMixin:
    _agent: Any
    _autonomous_brain: Any
    _service: Any
    _config: Dict[str, Any]

    def _init_core_services(self) -> None:
        self._config = {
            "server_host": "127.0.0.1", "server_port": 7777,
            "mod_host": "127.0.0.1", "mod_port": 9877,
            "bot_name": "Neko", "bot_password": "",
            "state_tick_interval_seconds": 1.0,
            "fast_think_interval_seconds": 5.0,
            "deep_think_min_seconds": 30,
            "deep_think_max_seconds": 90,
            "system_prompt_interval_seconds": 15.0,
        }
        self._agent = TerrariaAgent(self._config)
        self._autonomous_brain = AutonomousBrain(self._agent, self._config)
        self._service = TerrariaService(self._agent, self._config,
                                        push_message=self.push_message)

    async def _load_config(self) -> None:
        # 1) 读取 plugin.toml 的 [neko_terraria] 段，覆盖默认值
        try:
            cfg = await self.config.dump(timeout=5.0)
            neko = cfg.get("neko_terraria") if isinstance(cfg, dict) else None
            if isinstance(neko, dict):
                for key in ("server_host", "server_port", "mod_host", "mod_port",
                            "bot_name", "bot_password", "state_tick_interval_seconds",
                            "fast_think_interval_seconds", "deep_think_min_seconds",
                            "deep_think_max_seconds"):
                    if key in neko:
                        self._config[key] = neko[key]
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("读取配置失败，使用默认值: {}", exc)

        # 2) 用户独立配置文件 data/config/user_config.json 优先级最高（长久存储，更新插件不丢）
        try:
            from ..core.config_store import load_user_config
            user_cfg = load_user_config()
            for key in ("server_host", "server_port", "mod_host", "mod_port",
                        "bot_name", "bot_password"):
                if key in user_cfg:
                    # bot_password 允许空串（无密码），其他字段过滤空值
                    if key == "bot_password" or user_cfg[key] not in (None, ""):
                        self._config[key] = user_cfg[key]
            self.logger.info("已从 data/config/user_config.json 载入用户配置")
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("读取用户配置文件失败: {}", exc)

        # 同步配置到 agent（注意 agent 使用 cfg，不是 _config）
        self._agent.cfg = self._config
        self._autonomous_brain._config = self._config

    @lifecycle(id="startup")
    async def on_load(self) -> None:
        self.logger.info("neko_terraria 加载")
        # 静态 UI 必须在 on_load 同步段注册，不能在后台 task，否则宿主路由报 no static directory
        ui_registered = self.register_static_ui(
            "static",
            index_file="index.html",
            cache_control="no-cache, no-store, must-revalidate",
        )
        if ui_registered:
            self.logger.info("已注册泰拉瑞亚控制面板: /plugin/neko_terraria/ui/")
        else:
            self.logger.warning("注册静态 UI 失败，请检查 static/index.html 是否存在")

        # 对齐 vr 插件：注册列表入口动作，确保宿主识别到插件入口点
        self.set_list_actions([{
            "id": "open_ui",
            "label": "打开控制面板",
            "kind": "ui",
            "target": f"/plugin/{self.plugin_id}/ui/",
            "open_in": "new_tab",
        }])

        # startup 在常驻事件循环中调度，create_task 启动的长任务可存活
        async def _boot() -> None:
            await self._load_config()
            ok = await self._agent.start()
            if not ok:
                self.logger.warning("Agent 启动失败，检查 Terraria 服务端/mod")
                return
            await self._autonomous_brain.start()
            await self._service.start()
            self.logger.info("猫娘已进入泰拉瑞亚世界")
        asyncio.create_task(_boot())

    @lifecycle(id="shutdown")
    async def on_unload(self) -> None:
        await self._service.stop()
        await self._autonomous_brain.stop()
        await self._agent.stop()
        self.logger.info("neko_terraria 卸载")
