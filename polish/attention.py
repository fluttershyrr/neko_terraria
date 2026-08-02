"""注意力漂移：分心与重新聚焦模型。"""

import random


class AttentionDrift:
    def __init__(self) -> None:
        self.drift_chance = 0.20

    def should_drift(self) -> bool:
        return random.random() < self.drift_chance
