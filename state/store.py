"""插件自身状态缓存，供 UI context 读取。"""

from typing import Any, Dict


class StateStore:
    def __init__(self) -> None:
        self.data: Dict[str, Any] = {
            "connected": False, "hp": 0, "mp": 0,
            "current_goal": "", "bot_name": "Neko",
        }

    def update(self, patch: Dict[str, Any]) -> None:
        self.data.update(patch)

    def get(self) -> Dict[str, Any]:
        return dict(self.data)
