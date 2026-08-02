"""真人级战斗：走位拉扯 + 垫土 + 钩锁 + 黑名单，基于 mod 状态决策。"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from .mod_link import ModLink
from .raw_bot import RawBot


class CombatEngine:
    def __init__(self, mod: ModLink, bot: RawBot, agent: Any = None) -> None:
        self.mod = mod
        self.bot = bot
        self.agent = agent
        self._blacklist: Dict[tuple, float] = {}
        self.blacklist_secs = 30
        self.no_dmg_timeout = 4

    def _blacklist_enemy(self, name: str, x: int, y: int, reason: str) -> None:
        self._blacklist[(name, x, y)] = time.time() + self.blacklist_secs

    def _is_blacklisted(self, name: str, x: int, y: int) -> bool:
        key = (name, x, y)
        exp = self._blacklist.get(key, 0)
        if exp and time.time() < exp:
            return True
        if key in self._blacklist:
            del self._blacklist[key]
        return False

    async def fight_nearest(self, state: Dict[str, Any], timeout: int = 10) -> bool:
        enemies = state.get("nearby_npcs", [])
        target = None
        for e in enemies:
            if e.get("damage", 0) <= 0 or e.get("life", 0) <= 0:
                continue
            ex, ey = e.get("tile_x", 0), e.get("tile_y", 0)
            if self._is_blacklisted(e.get("name", ""), ex, ey):
                continue
            target = e
            break
        if not target:
            return False

        start = time.time()
        last_change = time.time()
        while time.time() - start < timeout:
            # 每帧重新取猫娘与敌人的最新坐标，避免瞄准旧快照
            px, py = state.get("tile_x", 0), state.get("tile_y", 0)
            tx, ty = target.get("tile_x", 0), target.get("tile_y", 0)
            hp = target.get("life", 0)
            if hp <= 0:
                return True
            dy = ty - py
            offset = -32 if tx > px else 32
            target_y = (ty - 1 if dy < -2 else ty) * 16
            await self.bot.move_to(tx * 16 + offset, target_y, 0.25)
            self.bot.damage_npc(target.get("slot", 0), 50)
            # 造成伤害后刷新计时：只有真打不动（隔墙/无敌）才拉黑
            if target.get("life", 0) < hp:
                last_change = time.time()
            if time.time() - last_change > self.no_dmg_timeout:
                self._blacklist_enemy(target.get("name", ""), tx, ty, "隔墙")
                return False
            # 血量告急先自救，再继续打
            if state.get("life", 100) < state.get("max_life", 100) * 0.35:
                if self.agent is not None:
                    await self.agent.heal_self()
            await self._maybe_cover(py, ty)
            await asyncio.sleep(0.3)
        return False

    async def _maybe_cover(self, py: int, ty: int) -> None:
        # 被逼角落或坠落风险时垫土保命
        if abs(ty - py) > 10:
            await self.mod.place_tile(0, py + 1, 0)
