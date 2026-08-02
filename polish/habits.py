"""个人习惯：性格种子与行为偏好。"""

from typing import Dict


class PersonalHabits:
    def __init__(self, seed: str = "neko") -> None:
        self.seed = seed
        self.prefs: Dict[str, float] = {
            "talkative": 0.7, "brave": 0.6, "curious": 0.8,
        }

    def trait(self, name: str) -> float:
        return self.prefs.get(name, 0.5)
