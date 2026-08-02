"""视觉感知：截图理解（接入 core/vision 节流后喂 LLM）。"""

from typing import Any


class VisualPerception:
    def __init__(self, vision_bridge) -> None:
        self.vision = vision_bridge

    async def feed(self, b64: str, mime: str = "image/jpeg") -> None:
        await self.vision.on_frame(b64, mime)
