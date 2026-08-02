"""猫娘目标指令工具：set_goal / interrupt / send_chat。"""

from typing import Any, Dict

from plugin.sdk.plugin import Ok, llm_tool

from ..bridge.task_chain import Goal


class GoalToolsMixin:
    _agent: Any
    _autonomous_brain: Any
    @llm_tool(
        name="terraria_set_goal",
        description="给猫娘下达泰拉瑞亚目标：采集/合成/探索，可选挖完给玩家或自己穿。",
        parameters={
            "type": "object",
            "properties": {
                "goal_type": {"type": "string",
                              "enum": ["gather", "craft", "explore", "boss_prep"]},
                "target": {"type": "string", "description": "目标物品/Boss英文名"},
                "reason": {"type": "string", "description": "1句话理由"},
                "amount": {"type": "integer", "description": "目标数量"},
                "deliver_to_player": {"type": "boolean",
                                      "description": "挖/做完后给玩家"},
                "equip_self": {"type": "boolean", "description": "自己穿上装备"},
            },
            "required": ["goal_type", "target"],
        },
    )
    async def llm_set_goal(self, goal_type: str, target: str, **kwargs) -> Dict[str, Any]:
        goal = Goal(
            goal_type=goal_type, target=target,
            reason=kwargs.get("reason", ""),
            amount=kwargs.get("amount", 10),
            deliver_to_player=kwargs.get("deliver_to_player", False),
            equip_self=kwargs.get("equip_self", False),
        )
        await self._agent.submit_goal(goal)
        return Ok({"output": f"已下达目标：{goal_type} {target}"})

    @llm_tool(
        name="terraria_interrupt",
        description="打断猫娘当前自主行为，立即执行新指令。",
        parameters={"type": "object",
                    "properties": {"reason": {"type": "string"}},
                    "required": []},
    )
    async def llm_interrupt(self, **kwargs) -> Dict[str, Any]:
        why = kwargs.get("reason", "") or "主人有新指令"
        cur = self._agent.executor.current()
        stopped = await self._agent.interrupt_current(why)
        # 同步清掉自主大脑的动机残留，避免刚打断又自己跑掉
        if self._autonomous_brain:
            await self._autonomous_brain.bus.publish("interrupt", kwargs)
        if stopped and cur:
            return Ok({"output": f"已停下「{cur['name']}」（做到 {cur['step']}），听你的~"})
        return Ok({"output": "现在没有在做的任务，随时听你安排~"})

    @llm_tool(
        name="terraria_chat",
        description="【仅限闲聊/角色扮演/情感表达】让猫娘在游戏内说一句符合人设的话。"
                    "注意：本工具只负责'说话'，不执行任何游戏内操作。"
                    "当主人的话包含游戏操作指令（如挖矿/采集/合成/给物品/传送/跟随/守点/探索等）时，"
                    "不要调用本工具，必须改用 terraria_command / terraria_task / terraria_set_goal 等执行类工具。",
        parameters={"type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"]},
    )
    async def llm_chat(self, text: str, **_) -> Dict[str, Any]:
        await self._agent.send_chat(text)
        return Ok({"output": "已发送"})

    @llm_tool(
        name="terraria_command",
        description="【主人下游戏指令的主入口】把主人用自然语言说的话（中文/英文均可）原样传入，"
                    "由猫娘内置指令解析器判断并执行：挖矿('挖10个铁')、跟随('跟着我')、"
                    "守点('守在这')、停止('别挖了')、以及任何多步任务。只要是游戏内操作指令就调本工具，"
                    "不要调用 terraria_chat。解析失败会返回'没听懂'，成功则开始执行。",
        parameters={"type": "object",
                    "properties": {"text": {"type": "string",
                                            "description": "主人下达的游戏指令原文"}},
                    "required": ["text"]},
    )
    async def llm_command(self, text: str, **_) -> Dict[str, Any]:
        # 自然语言直达执行：command -> coordinator.handle -> intent.parse
        # 这是确定性解析，不依赖 LLM 二次判断，确保"说出口就做"
        res = await self._agent.command(text, source="owner")
        return Ok({"output": res.get("output", str(res))})
