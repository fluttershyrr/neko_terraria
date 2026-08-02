"""UI 上下文：向 Hosted UI 提供只读 state。"""

from typing import Any, Dict

from plugin.sdk.plugin import ui


class UiContextMixin:
    _agent: Any
    _config: Dict[str, Any]

    @ui.context(id="dashboard")
    def ctx_dashboard(self) -> Dict[str, Any]:
        st = self._agent.get_state()
        return {
            "connected": self._agent.running,
            "bot_name": self._config.get("bot_name", "Neko"),
            "hp": st.get("hp", 0),
            "mp": st.get("mp", 0),
            "current_goal": self._agent.current_goal,
            "mods": self._agent.registry.mod_list(),
            "hotbar": self._agent.get_inventory_sync().get("hotbar", []),
            "equipped": self._agent.get_inventory_sync().get("equipped", []),
            "inventory": self._agent.get_inventory_sync().get("inventory", []),
            "chests": self._agent.get_chests_sync(),
            "log": self._agent.get_log_sync(),
            "task": self._agent.executor.current(),
            "task_last": self._agent.executor.last_result(),
            "longterm": self._agent.longterm.active(),
            "doing": self._agent.coordinator.say(),
            "thinking": self._thinking(),
        }

    def _thinking(self) -> Dict[str, Any]:
        # 最近一次思考过程，让主人看得见猫娘在想什么
        a = self._agent.brain.last_assessment()
        if a is None:
            return {}
        return {"doable": a.doable, "say": a.say(),
                "thoughts": a.thoughts, "fixes": a.fixes,
                "need": a.need_from_owner}

    @ui.context(id="guide")
    def ctx_guide(self) -> Dict[str, Any]:
        return {
            "guide_text": "用语音或聊天告诉猫娘：去挖铁矿、给我、穿上装备。",
            "connected": self._agent.running,
            "mods": self._agent.registry.mod_list(),
        }
