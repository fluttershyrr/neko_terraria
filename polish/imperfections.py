"""瑕疵注入：微小抖动、不完美停顿，增强自然感。"""

import random


class ImperfectionInjector:
    def __init__(self) -> None:
        self.jitter_chance = 0.15
        self.pause_chance = 0.25

    def maybe_jitter(self) -> bool:
        return random.random() < self.jitter_chance

    def maybe_pause(self) -> bool:
        return random.random() < self.pause_chance
