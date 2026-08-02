"""猫娘内部状态：能量/无聊/情绪，零 LLM 成本演变。"""

import random
from dataclasses import dataclass


@dataclass
class InternalState:
    energy: float = 1.0
    boredom: float = 0.0
    happiness: float = 0.5
    mood: str = "neutral"

    def tick(self, has_stimulus: bool) -> None:
        self.energy = max(0.0, min(1.0, self.energy + random.gauss(0, 0.02)))
        if not has_stimulus:
            self.boredom = min(1.0, self.boredom + 0.01)
        else:
            self.boredom = max(0.0, self.boredom - 0.02)
        self.happiness += (0.5 - self.happiness) * 0.01
