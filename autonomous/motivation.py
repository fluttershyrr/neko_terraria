"""5 种动机竞争驱动：采集/战斗/探索/社交/舒适。"""

from typing import Dict


class MotivationSystem:
    def __init__(self) -> None:
        self.scores: Dict[str, float] = {
            "gather": 0.0, "combat": 0.0, "explore": 0.0,
            "social": 0.0, "comfort": 0.0,
        }

    def update(self, state: Dict, boredom: float) -> str:
        # 每帧重算：先归零（避免上帧状态残留），再按当前状态打分
        self.scores = {k: 0.0 for k in self.scores}
        self.scores["boredom_driven"] = boredom
        if len(state.get("nearby_npcs", [])) > 0:
            self.scores["combat"] = 0.9
        if boredom > 0.7:
            self.scores["explore"] = 0.8
        if state.get("life", 100) < (state.get("max_life", 100) or 100) * 0.5:
            self.scores["comfort"] = 0.95
        if len(state.get("nearby_players", [])) > 0:
            self.scores["social"] = 0.85
        # gather 在中立状态给基础分，确保有活干（但不压过真实驱动）
        self.scores["gather"] = 0.4
        top = max(self.scores, key=self.scores.get)
        return top if self.scores[top] > 0.5 else "idle"
