"""读 mod 状态快照，构建猫娘可理解的游戏态势。"""

from typing import Any, Dict


class GameStatePerception:
    def __init__(self, agent) -> None:
        self.agent = agent

    def snapshot(self) -> Dict[str, Any]:
        s = self.agent.get_state()
        return {
            "hp": s.get("hp", 0), "mp": s.get("mp", 0),
            "pos": (s.get("tile_x", 0), s.get("tile_y", 0)),
            "nearby_enemies": s.get("nearby_npcs", []),
            "nearby_players": s.get("nearby_players", []),
            "time": s.get("time_of_day", "白天"),
        }
