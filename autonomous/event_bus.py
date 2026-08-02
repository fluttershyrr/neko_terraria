"""事件总线：模块间解耦通信，指令打断走这里。"""

import asyncio
from typing import Any, Callable, Dict, List


class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Callable[[Any], Any]]] = {}

    def subscribe(self, event: str, cb: Callable[[Any], Any]) -> None:
        self._subs.setdefault(event, []).append(cb)

    async def publish(self, event: str, data: Any) -> None:
        for cb in self._subs.get(event, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception:
                pass
