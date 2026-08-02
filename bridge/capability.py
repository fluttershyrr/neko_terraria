"""能力评估：猫娘当前能做什么（钩锁/垫土/挖掘/梯绳），以及能否到达目标。

所有判断基于 mod 上报的 capabilities + 背包三大类，供导航/任务前预判，
无能力时及时制止并汇报主人，而非硬冲导致卡死或掉坑。
"""

from typing import Any, Dict, Optional


class Capability:
    def __init__(self, agent) -> None:
        self.agent = agent
        self._cache: Dict[str, Any] = {}

    async def refresh(self) -> Dict[str, Any]:
        caps = await self.agent.mod.get_capabilities()
        if caps:
            self._cache = caps
        return self._cache

    def get(self, key: str, default=None):
        return self._cache.get(key, default)

    def has_hook(self) -> bool:
        return bool(self._cache.get("has_hook", False))

    def hook_range(self) -> int:
        return int(self._cache.get("hook_range", 0))

    def dirt_count(self) -> int:
        return int(self._cache.get("dirt_count", 0))

    def has_pickaxe(self) -> bool:
        return bool(self._cache.get("has_pickaxe", False))

    def pickaxe_power(self) -> int:
        return int(self._cache.get("pickaxe_power", 0))

    def rope_count(self) -> int:
        return int(self._cache.get("rope_count", 0))

    def nearby_stations(self) -> list:
        # 身边的合成站（工作台/熔炉/铁砧…），供合成推演判断做不做得了
        return list(self._cache.get("nearby_stations", []) or [])

    def can_bridge(self, needed: int = 1) -> bool:
        # 有土块才能搭土/垫脚
        return self.dirt_count() >= needed

    def can_dig(self) -> bool:
        return self.has_pickaxe()

    def can_climb(self, height_diff: int) -> str:
        """判断能否上到目标高度（深坑/矿井回地面）。

        返回可用手段：'hook' / 'rope' / 'dirt' / ''（无能力）
        """
        if self.has_hook() and height_diff <= self.hook_range():
            return "hook"
        if self.rope_count() > 0:
            return "rope"
        if self.can_bridge() and height_diff <= 25:
            return "dirt"
        return ""

    def reason(self, height_diff: int) -> str:
        how = self.can_climb(height_diff)
        if how == "hook":
            return "可以用钩锁上去"
        if how == "rope":
            return "有绳/梯可以爬上去"
        if how == "dirt":
            return "可以用土块垫上去"
        # 无能力：给出原因，便于向主人汇报
        lacks = []
        if not self.has_hook():
            lacks.append("没有钩锁")
        if self.rope_count() <= 0:
            lacks.append("没有绳/梯")
        if not self.can_bridge():
            lacks.append("没有土块可垫")
        return "上不去：" + "、".join(lacks) + "（请给我或指明路线）"
