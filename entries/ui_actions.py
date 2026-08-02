"""UI 操作：前端面板按钮绑定的 @ui.action + 宿主入口 @plugin_entry。"""

from typing import Any

from plugin.sdk.plugin import Ok, plugin_entry, ui


class UiActionsMixin:
    _agent: Any

    @ui.context(id="dashboard", title="泰拉瑞亚猫娘", icon="🐱")
    def build_dashboard_context(self) -> dict:
        """面板上下文（N.E.K.O 框架调用）"""
        if self._agent is None or not self._agent.running:
            return {"connected": False}
        return {"connected": self._agent.running}

    @plugin_entry(
        id="get_dashboard_state",
        name="获取面板状态",
        description="返回猫娘当前完整状态：连接/生命/魔力/位置/背包/箱子/日志等，供前端轮询刷新。",
        input_schema={"type": "object", "properties": {}},
    )
    async def act_get_dashboard_state(self, **_):
        """统一状态入口，供前端轮询"""
        from ..core.config_store import load_user_config

        # 连接配置
        cfg = load_user_config()
        connection = {
            "server_host": cfg.get("server_host", "127.0.0.1"),
            "server_port": cfg.get("server_port", 7777),
            "mod_host": cfg.get("mod_host", "127.0.0.1"),
            "mod_port": cfg.get("mod_port", 9877),
            "bot_name": cfg.get("bot_name", "Neko"),
            "bot_password": cfg.get("bot_password", ""),
        }

        # Agent 未初始化
        if self._agent is None:
            return Ok({
                "connected": False,
                "connection": connection,
                "player": {"hp": 0, "mp": 0, "max_life": 100, "max_mp": 20, "tile_x": 0, "tile_y": 0},
                "world": {"time": "未知", "grounded": False},
                "inventory": {"hotbar": [], "equipped": [], "inventory": []},
                "chests": [],
                "log": [],
                "current_goal": "",
            })

        # 连接状态
        connected = self._agent.running

        # 玩家状态
        st = self._agent.get_state() if connected else {}
        player = {
            "hp": st.get("hp", 0),
            "mp": st.get("mp", 0),
            "max_life": st.get("max_life", 100),
            "max_mp": st.get("max_mp", 20),
            "tile_x": st.get("tile_x", 0),
            "tile_y": st.get("tile_y", 0),
        }

        # 世界状态
        world = {
            "time": st.get("time_of_day", "未知"),
            "grounded": st.get("grounded", False),
        }

        # 背包
        inventory = {
            "hotbar": self._agent._inv_full.get("hotbar", []) if connected else [],
            "equipped": self._agent._inv_full.get("equipped", []) if connected else [],
            "inventory": self._agent._inv_full.get("inventory", []) if connected else [],
        }

        # 箱子（简化返回）
        chests = self._agent._chests[:10] if connected else []  # 最多返回10个箱子

        # 日志（最近20条）
        log = self._agent.get_log_sync()[-20:] if connected else []

        # 当前目标
        current_goal = self._agent.current_goal if connected else ""

        return Ok({
            "connected": connected,
            "connection": connection,
            "player": player,
            "world": world,
            "inventory": inventory,
            "chests": chests,
            "log": log,
            "current_goal": current_goal,
        })

    @ui.action(id="nt_connect", label="连接游戏", icon="🔗", group="connection", tone="success")
    @plugin_entry(
        id="nt_connect",
        name="连接游戏",
        description="启动猫娘并连接 Terraria 服务端/mod 接口。",
        input_schema={"type": "object", "properties": {}},
    )
    async def act_connect(self, **_):
        if self._agent is None:
            return Ok({"connected": False, "msg": "猫娘还没准备好，稍等"})
        ok = True
        if not self._agent.running:
            ok = await self._agent.start()
        return Ok({"connected": ok, "msg": "连接成功" if ok else "连接失败"})

    @ui.action(id="nt_stop", label="断开连接", icon="✂️", group="connection", tone="danger")
    @plugin_entry(
        id="nt_stop",
        name="断开连接",
        description="断开猫娘与 Terraria 世界的连接。",
        input_schema={"type": "object", "properties": {}},
    )
    async def act_stop(self, **_):
        if self._agent is not None:
            await self._agent.stop()
        return Ok({"stopped": True, "msg": "已断开连接"})

    @ui.action(id="nt_save_config", label="保存连接配置", icon="💾", group="config", tone="success")
    @plugin_entry(
        id="nt_save_config",
        name="保存连接配置",
        description="保存 Terraria 服务端与 mod 接口的连接配置。",
        input_schema={
            "type": "object",
            "properties": {
                "server_host": {"type": "string", "description": "Terraria 服务端 IP"},
                "server_port": {"type": "integer", "description": "Terraria-Bot 协议端口"},
                "mod_host": {"type": "string", "description": "tModLoader mod 接口 IP"},
                "mod_port": {"type": "integer", "description": "mod 接口端口"},
                "bot_name": {"type": "string", "description": "猫娘玩家名"},
                "bot_password": {"type": "string", "description": "房间密码（留空=不修改）"},
            },
            "required": ["server_host", "server_port", "mod_host", "mod_port", "bot_name"],
        },
    )
    async def act_save_config(self, **kwargs):
        from ..bridge.connection import Connection
        from ..core.config_store import load_user_config, save_user_config

        # 从文件加载当前配置
        current_cfg = load_user_config()

        # 合并新配置（留空字段保持原值）
        patch = {}
        for key in ("server_host", "server_port", "mod_host", "mod_port", "bot_name", "bot_password"):
            if key in kwargs and kwargs[key] not in (None, ""):
                patch[key] = kwargs[key]
            elif key in current_cfg:
                patch[key] = current_cfg[key]

        # 更新内存配置
        for k, v in patch.items():
            self._config[k] = v
        if self._agent is not None:
            self._agent.cfg = self._config

        # 重建连接对象
        try:
            if self._agent is not None and self._agent._running:
                await self._agent.stop()
            if self._agent is not None:
                self._agent.conn = Connection(
                    self._config["server_host"], self._config["server_port"],
                    self._config["mod_host"], self._config["mod_port"])
        except Exception as exc:
            self.logger.warning(f"重建连接对象失败: {exc}")

        # 持久化到文件
        try:
            save_user_config(patch)
        except Exception as exc:
            self.logger.warning(f"写入配置文件失败: {exc}")

        return Ok({"saved": True, "msg": "配置已保存"})
