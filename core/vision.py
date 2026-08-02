"""截图采集 + 节流 + 推 LLM（ai_behavior=read）。"""

import asyncio
import time
from typing import Any, Optional


class VisionBridge:
    def __init__(self, cfg: dict, push_message=None) -> None:
        self.cfg = cfg
        self.push = push_message
        self.min_interval = cfg.get("screenshot_stream_min_interval_seconds", 6.0)
        self._last = 0.0

    async def on_frame(self, b64: str, mime: str) -> None:
        now = time.time()
        if now - self._last < self.min_interval:
            return
        self._last = now
        if self.push:
            try:
                await self.push(b64, ai_behavior="read", mime=mime)
            except Exception:
                pass
