"""挖矿引擎：导航到矿点、循环挖掘、可被中断切换目标。"""

import asyncio
from typing import Any, Dict, Optional

from .mod_link import ModLink
from .raw_bot import RawBot
from .item_npc_dict import item_id


class MiningEngine:
    def __init__(self, mod: ModLink, bot: RawBot, agent=None) -> None:
        self.mod = mod
        self.bot = bot
        self.agent = agent
        self._cancel = asyncio.Event()

    def _stopped(self) -> bool:
        # 自身取消位，或执行器被主人打断
        if self._cancel.is_set():
            return True
        ex = getattr(self.agent, "executor", None) if self.agent else None
        return bool(ex and ex.should_stop())

    def cancel(self) -> None:
        self._cancel.set()

    def reset(self) -> None:
        self._cancel.clear()

    async def mine_target(self, target_item: str, amount: int = 10,
                          state: Optional[Dict[str, Any]] = None) -> tuple:
        # 返回 (物品id, 挖到数量)。优先用 mod 的 break_tile 真实破坏矿 tile，
        # 让游戏自然掉落进背包；矿点坐标需 mod 后续提供，这里用脚下前方近似。
        iid = item_id(target_item)
        mined = 0
        while mined < amount:
            if self._stopped():
                self._cancel.clear()
                return iid, mined
            if state:
                px, py = state.get("tile_x", 0), state.get("tile_y", 0)
                # 朝面前一格破坏：真挖矿（掉落由游戏决定）
                await self.mod.break_tile(px + 1, py)
            else:
                # 无状态兜底：召唤模拟（开发期）
                self.bot.summon_item(iid, 0, 0, 1)
            mined += 1
            await asyncio.sleep(0.5)
        return iid, mined
