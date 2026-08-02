"""任务协调中枢：一句话进来，决定谁去做、要不要让路、怎么回话。

双轨模型
    前台轨（executor）：有限任务，同一时刻只有一个，做完就释放。
    后台轨（longterm）：长期任务，可多个并存（跟随+守点），
                        前台一忙就自动让路，前台一完自动恢复。

好处是"跟着我"和"帮我挖10个铁"可以同时成立：
    跟着走 → 收到挖矿指令 → 跟随让路 → 挖完 → 自动继续跟着。
"""

import asyncio
from typing import Any, Dict, List, Optional

from . import intent as intent_mod
from .executor import SRC_OWNER, SRC_AUTO


class TaskCoordinator:
    """统一入口：主人说什么，这里决定怎么落地。"""

    def __init__(self, agent) -> None:
        self.agent = agent

    @property
    def lt(self):
        return self.agent.longterm

    @property
    def jobs(self):
        return self.agent.jobs

    @property
    def executor(self):
        return self.agent.executor

    # ---------------- 主入口 ----------------
    async def handle(self, text: str, source: str = SRC_OWNER) -> Dict[str, Any]:
        """解析并派发一句指令。"""
        it = intent_mod.parse(text)

        if it.mode == "stop":
            return await self._do_stop(it)
        if it.mode == "longterm":
            return await self._do_longterm(it)
        if it.mode == "finite":
            return await self._do_finite(it, source)
        # 认不出来：说清楚我没懂，别假装在做（步骤为空只会空转）
        return {"ok": False, "status": "not_understood", "mode": "unknown",
                "output": "主人这个我没太听懂，能说得具体点吗？"
                          "比如「挖10个铁」「跟着我」「去箱子拿把镐子」~"}

    # ---------------- 停止 ----------------
    async def _do_stop(self, it) -> Dict[str, Any]:
        if it.kind:
            t = self.lt.get(it.kind)
            if t is None:
                # 也可能主人想停的是前台任务
                cur = self.executor.current()
                if cur:
                    await self.agent.interrupt_current("主人喊停")
                    return {"ok": True, "output": "好的，我不做了~"}
                return {"ok": True, "output": "我本来就没在做这个呀~"}
            name = t.name
            await self.lt.stop(it.kind, "主人喊停")
            return {"ok": True, "output": f"好的，不{name}了~"}
        # 没指明停什么：全停
        names = await self.lt.stop_all("主人喊停")
        if self.executor.current():
            await self.agent.interrupt_current("主人喊停")
        if names:
            return {"ok": True, "output": "好的，" + "、".join(names) + " 都停下了~"}
        return {"ok": True, "output": "我现在什么都没在做哦~"}

    # ---------------- 长期任务 ----------------
    async def _do_longterm(self, it) -> Dict[str, Any]:
        res = await self.jobs.start(it.kind, target=it.target,
                                    amount=it.amount, reason=it.reason)
        res["mode"] = "longterm"
        res["intent"] = it.snapshot()
        return res

    # ---------------- 有限任务 ----------------
    async def _do_finite(self, it, source: str) -> Dict[str, Any]:
        if not it.steps:
            return {"ok": False, "status": "not_understood",
                    "output": "主人这个我没太听懂，能说得具体点吗？"}
        return await self.run_foreground(it.steps, it.reason or it.raw, source)

    async def run_foreground(self, steps: List[str], goal_text: str = "",
                             source: str = SRC_OWNER,
                             dry_run: bool = False) -> Dict[str, Any]:
        """跑前台有限任务。让路/恢复由执行器统一负责，这里不重复处理。"""
        return await self.agent.run_complex_task(
            steps, goal_text, source, dry_run=dry_run)

    # ---------------- 状态汇报 ----------------
    def status(self) -> Dict[str, Any]:
        cur = self.executor.current()
        longs = self.lt.active()
        return {
            "foreground": cur,
            "longterm": longs,
            "busy": bool(cur) or bool(longs),
            "say": self.say(),
        }

    def say(self) -> str:
        """一句话说清"我在干嘛"。"""
        cur = self.executor.current()
        longs = self.lt.say_all()
        if cur and longs:
            return f"正在{cur.get('name', '做任务')}，同时{longs}"
        if cur:
            return f"正在{cur.get('name', '做任务')}"
        if longs:
            return longs
        return "我现在闲着呢，主人有什么要我做的吗~"
