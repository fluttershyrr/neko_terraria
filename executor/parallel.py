"""并行执行器：多层动作优先级队列（移动/攻击/垫土可并行）。"""

import asyncio
from typing import Any, Callable, Dict, List


class ParallelExecutor:
    def __init__(self) -> None:
        # 优先级：0 最高（表情/微动作），3 最低（移动）
        self._layers: Dict[int, List[Callable[[], Any]]] = {i: [] for i in range(4)}

    def submit(self, layer: int, action: Callable[[], Any]) -> None:
        self._layers.setdefault(layer, []).append(action)

    async def run_all(self) -> None:
        for layer in sorted(self._layers):
            for action in self._layers[layer]:
                try:
                    if hasattr(action, "__await__"):
                        await action()
                except Exception:
                    pass
            self._layers[layer].clear()
