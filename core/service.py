"""状态快照周期推 + 主动 nudge（低血/待命）+ 截图转 LLM。"""

import asyncio
from typing import Any, Dict, Optional

from ..bridge.agent import TerrariaAgent


class TerrariaService:
    def __init__(self, agent: TerrariaAgent, cfg: Dict[str, Any],
                 push_message=None) -> None:
        self.agent = agent
        self.cfg = cfg
        self.push = push_message
        self._running = False

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._nudge_loop())

    async def stop(self) -> None:
        self._running = False

    async def _nudge_loop(self) -> None:
        interval = self.cfg.get("system_prompt_interval_seconds", 15.0)
        while self._running:
            state = self.agent.get_state()
            if state.get("hp", 100) < 30:
                await self._push("我血量很低了，需要支援！", "respond")
            await asyncio.sleep(interval)

    async def _push(self, text: str, behavior: str) -> None:
        if self.push:
            try:
                await self.push(text, ai_behavior=behavior)
            except Exception:
                pass
