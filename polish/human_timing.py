"""人类化时序：反应延迟正态分布 + 动作时长变异。"""

import random


class HumanTiming:
    def reaction_delay(self) -> float:
        return max(0.1, random.gauss(0.2, 0.08))

    def action_duration(self, base: float) -> float:
        return base * random.uniform(0.9, 1.15)
