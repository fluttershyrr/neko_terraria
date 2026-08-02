"""长期任务的具体干法：跟着我、一直挖某种矿、守在这。

只放"怎么做"，生命周期/让路/停止都归 longterm.LongTermManager 管。
每个 job 的循环骨架统一为：
    while 没被叫停:
        await lt.wait_turn(kind)   # 前台忙就让路
        干一小步
        task.beat(进度人话)
这样任何一步都能被立刻打断，也不会和前台任务抢操作权。
"""

import asyncio
import time
from typing import Any, Dict, Optional, Tuple

from .longterm import StandingTask

# 跟随参数
FOLLOW_NEAR = 4        # 这么近就不动了，免得贴脸抖
FOLLOW_TICK = 0.6
MINE_BATCH = 1         # 每轮只挖一点，保证能被及时打断


class StandingJobs:
    """长期任务的行为库。"""

    def __init__(self, agent) -> None:
        self.agent = agent

    @property
    def lt(self):
        return self.agent.longterm

    # ---------------- 小工具 ----------------
    def _me(self) -> Tuple[int, int]:
        st = self.agent.get_state()
        return st.get("tile_x", 0), st.get("tile_y", 0)

    def _owner(self) -> Optional[Tuple[int, int]]:
        # 主人 = 附近玩家里的第一个（与自主大脑口径一致）
        st = self.agent.get_state()
        players = st.get("nearby_players") or []
        if not players:
            return None
        p = players[0]
        return p.get("tile_x", 0), p.get("tile_y", 0)

    # ---------------- 跟着我 ----------------
    async def follow_loop(self, task: StandingTask) -> None:
        """一直跟着主人，直到被叫停。近了就待着，远了就追。"""
        lt = self.lt
        lost = 0
        while not lt.should_stop(task.kind):
            if not await lt.wait_turn(task.kind):
                break

            owner = self._owner()
            if owner is None:
                lost += 1
                if lost == 5:
                    task.beat("找不到主人了，先待在原地")
                await asyncio.sleep(FOLLOW_TICK)
                continue
            lost = 0

            mx, my = self._me()
            ox, oy = owner
            dx, dy = ox - mx, oy - my
            dist = (dx * dx + dy * dy) ** 0.5
            task.progress = int(time.time() - task.started_at)

            if dist <= FOLLOW_NEAR:
                task.beat("就在主人旁边")
                await asyncio.sleep(FOLLOW_TICK)
                continue

            task.beat(f"离主人 {int(dist)} 格，追上去")
            try:
                # 落差大交给爬升逻辑，别傻乎乎撞墙
                if (my - oy) > 3:
                    await self.agent.climb_to(ox, oy)
                else:
                    await self.agent.navigate_to(ox, oy, timeout=8)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(FOLLOW_TICK)

    # ---------------- 一直挖某种矿 ----------------
    async def mine_loop(self, task: StandingTask) -> None:
        """没说挖多少就一直挖，挖满 goal_amount（若有）或被叫停才停。"""
        lt = self.lt
        ore = task.target or "铁矿"
        mining = self.agent.mining
        while not lt.should_stop(task.kind):
            if not await lt.wait_turn(task.kind):
                break

            if task.goal_amount and task.progress >= task.goal_amount:
                task.beat(f"{ore} 够了，一共 {task.progress} 个")
                break

            try:
                mining.reset()
                _iid, got = await mining.mine_target(
                    ore, MINE_BATCH, self.agent.get_state())
            except asyncio.CancelledError:
                raise
            except Exception as e:
                task.beat(f"挖不动：{e}")
                await asyncio.sleep(1.5)
                continue

            if got:
                task.progress += int(got)
                task.beat(f"又挖到 {ore}，一共 {task.progress} 个")
            else:
                task.beat(f"这附近没{ore}了")
                await asyncio.sleep(1.0)
            await asyncio.sleep(0.3)

    # ---------------- 守在这 ----------------
    async def guard_loop(self, task: StandingTask) -> None:
        """守在某点附近，走远了自己回来。"""
        lt = self.lt
        hx, hy = self._me()
        task.note = "守着这里"
        while not lt.should_stop(task.kind):
            if not await lt.wait_turn(task.kind):
                break
            try:
                mx, my = self._me()
                if abs(mx - hx) + abs(my - hy) > 30:
                    task.beat("走远了，回守点")
                    await self.agent.navigate_to(hx, hy, timeout=15)
                else:
                    task.beat("守着呢")
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            task.progress = int(time.time() - task.started_at)
            await asyncio.sleep(1.2)

    # ---------------- 统一入口 ----------------
    async def start(self, kind: str, target: str = "", amount: int = 0,
                    reason: str = "") -> Dict[str, Any]:
        """按 kind 起一个长期任务。"""
        table = {
            "follow": ("跟着主人", self.follow_loop),
            "mine": (f"一直挖{target or '矿'}", self.mine_loop),
            "guard": ("守在这里", self.guard_loop),
        }
        if kind not in table:
            return {"ok": False, "output": f"我不会长期做「{kind}」这件事"}
        name, fn = table[kind]
        task = StandingTask(name=name, kind=kind, target=target,
                            goal_amount=amount, reason=reason)
        return await self.lt.start(task, fn)
