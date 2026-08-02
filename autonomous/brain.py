"""AutonomousBrain：三层思考（状态演变/快速/深度）+ 事件驱动打断 + 自主执行。

大脑不是只发聊天，而是真正的玩家意识：基于状态与动机，直接对执行层下令
（战斗/用药/跟随/挖矿），或提交 Goal 给 TaskChain 跑任务链。用户语音指令
与自主决策走同一执行管道，共同决定猫娘行为。
"""

import asyncio
import random
from typing import Any, Dict, Optional

from .event_bus import EventBus
from .internal_state import InternalState
from .motivation import MotivationSystem
from ..bridge.task_chain import Goal
from ..bridge.executor import SRC_AUTO
from ..polish.human_timing import HumanTiming
from ..polish.attention import AttentionDrift


class AutonomousBrain:
    def __init__(self, agent, cfg: Dict[str, Any]) -> None:
        self.agent = agent
        self.cfg = cfg
        self.state = InternalState()
        self.motivation = MotivationSystem()
        self.bus = EventBus()
        self.timing = HumanTiming()
        self.attention = AttentionDrift()
        self.running = False
        self._tasks: list[asyncio.Task] = []
        self._busy = False

    async def start(self) -> None:
        self.running = True
        self._tasks = [
            asyncio.create_task(self._state_tick()),
            asyncio.create_task(self._fast_think()),
            asyncio.create_task(self._deep_think()),
        ]
        self.bus.subscribe("interrupt", self._on_interrupt)

    async def stop(self) -> None:
        self.running = False
        for t in self._tasks:
            t.cancel()

    def occupied(self) -> bool:
        """有任务在跑就算占用：自主行为必须让位，不打断正在执行的任务。

        包含两类：前台有限任务（executor）与后台长期任务（longterm）。
        主人说了"跟着我"，自主行为就别再自作主张乱跑。
        """
        if self._busy:
            return True
        ex = getattr(self.agent, "executor", None)
        if ex and ex.busy():
            return True
        lt = getattr(self.agent, "longterm", None)
        return bool(lt and lt.busy_kinds())

    async def _state_tick(self) -> None:
        interval = self.cfg.get("state_tick_interval_seconds", 1.0)
        while self.running:
            self.state.tick(has_stimulus=self.occupied())
            await asyncio.sleep(interval)

    async def _fast_think(self) -> None:
        interval = self.cfg.get("fast_think_interval_seconds", 5.0)
        while self.running:
            # 有任务在执行时完全不自主行动（含跟随/闲聊），避免抢控制权
            if self.occupied():
                await asyncio.sleep(interval)
                continue
            state = self.agent.get_state()
            drive = self.motivation.update(state, self.state.boredom)
            await self._act_on_drive(drive, state)
            await asyncio.sleep(interval)

    async def _act_on_drive(self, drive: str, state: Dict[str, Any]) -> None:
        # 拟人反应延迟，不瞬间响应
        await asyncio.sleep(self.timing.reaction_delay())
        # 延迟期间主人可能下了任务：再确认一次，绝不插队
        if self.occupied():
            return
        # 偶尔走神：本次不行动
        if self.attention.should_drift():
            return
        # 每个分支都是真实执行，而非只发聊天
        players = state.get("nearby_players", [])
        if players and drive != "combat":
            # 附近有玩家：主动靠近陪玩（真人级跟随）
            ppos = (players[0]["tile_x"], players[0]["tile_y"])
            await self.agent.follow_player(ppos)
            if self.occupied():
                return

        if drive == "combat":
            self._busy = True
            try:
                await self.agent.combat.fight_nearest(state)
            finally:
                self._busy = False
        elif drive == "comfort":
            hp = state.get("life", 100)
            max_hp = state.get("max_life", 100) or 100
            if hp < max_hp * 0.5:
                if await self.agent.heal_self():
                    self.agent.bot.send_msg("血量有点低，喝口药~")
                else:
                    self.agent.bot.send_msg("血量低，先躲一下")
        elif drive == "gather":
            # 自主挖矿走执行器：标记为 auto，主人任务可随时抢占
            await self._auto_task("自主储备材料",
                                  [{"action": "gather", "item": "wood", "amount": 15}])
        elif drive == "explore" and self.state.boredom > 0.7:
            self.agent.bot.send_msg("有点无聊，我去周围转转~")
            await self.agent.submit_goal(
                Goal(goal_type="explore", target="nearby", reason="无聊探索"))
        elif drive == "social" and players and random.random() < 0.2:
            self.agent.bot.send_msg("主人在这呀，我跟着你~")

    async def _auto_task(self, why: str, steps: list) -> None:
        # 自主任务统一走执行器，来源 auto：不会打断主人任务，且能被主人打断
        run = getattr(self.agent, "run_complex_task", None)
        if run is None:
            return
        await run(steps, why, source=SRC_AUTO)

    async def _deep_think(self) -> None:
        lo = self.cfg.get("deep_think_min_seconds", 30)
        hi = self.cfg.get("deep_think_max_seconds", 90)
        while self.running:
            await asyncio.sleep(random.uniform(lo, hi))
            if self.occupied():
                continue
            state = self.agent.get_state()
            # 深度决策：低装备则自主去挖矿合成，无需用户下令
            if state.get("nearby_players") and random.random() < 0.3:
                self.agent.bot.send_msg("主人，我在这呢，要我帮忙吗？")
            elif self.state.boredom > 0.8:
                await self._auto_task("储备材料",
                                      [{"action": "gather", "item": "wood", "amount": 20}])

    async def _on_interrupt(self, data: Any) -> None:
        # 主人下达新指令：停掉当前一切（自主行为 + 正在跑的任务）
        self._busy = False
        self.state.boredom = 0.0
        self.motivation.scores.clear()
        why = ""
        if isinstance(data, dict):
            why = str(data.get("reason", "") or data.get("why", ""))
        await self.agent.interrupt_current(why or "主人有新指令")
