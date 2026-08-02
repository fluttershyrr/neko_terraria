"""长期任务：没有明确终点的常驻任务（跟着我 / 挖铁 / 守着这里）。

与前台有限任务的区别：
  有限任务  —— "挖10个铁"，步骤跑完就结束，占用前台唯一槽位。
  长期任务  —— "跟着我"、"挖铁"（没说多少），只有主人喊停、
                条件达成或环境变化才结束，常驻后台不占前台槽位。

长期任务必须满足三点，否则会拖垮体验：
  1. 可随时被叫停（协作式取消，不留残留动作）
  2. 可被前台任务临时让路（yield），前台做完自己恢复
  3. 有心跳与进度，主人问"你在干嘛"时答得出来
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 长期任务状态
LT_RUNNING = "running"    # 正在跑
LT_YIELDED = "yielded"    # 为前台任务让路，暂停中
LT_STOPPED = "stopped"    # 已结束


@dataclass
class StandingTask:
    """一个常驻任务的运行档案。"""

    name: str                       # 人话名字，如 "跟着主人"
    kind: str                       # follow / mine / guard
    target: str = ""                # 目标物/目标人
    reason: str = ""                # 为什么做
    status: str = LT_RUNNING
    progress: int = 0               # 已完成量（挖到几个 / 跟了多久）
    goal_amount: int = 0            # 0 表示无上限（真·长期）
    started_at: float = field(default_factory=time.time)
    last_beat: float = field(default_factory=time.time)
    note: str = ""

    def beat(self, note: str = "") -> None:
        # 心跳：证明任务还活着，同时更新一句人话进度
        self.last_beat = time.time()
        if note:
            self.note = note

    def say(self) -> str:
        # 给主人听的人话进度
        el = int(time.time() - self.started_at)
        if self.goal_amount:
            head = f"{self.name}（{self.progress}/{self.goal_amount}）"
        elif self.progress:
            head = f"{self.name}（已经 {self.progress} 个）"
        else:
            head = self.name
        tail = "，让路等着呢" if self.status == LT_YIELDED else ""
        return f"{head}，做了 {el} 秒{tail}"

    def snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "target": self.target,
            "status": self.status, "progress": self.progress,
            "goal_amount": self.goal_amount, "note": self.note,
            "elapsed": round(time.time() - self.started_at, 1),
            "say": self.say(),
        }


class LongTermManager:
    """长期任务管理器：常驻后台，与前台任务并行且自动让路。

    同一 kind 只允许一个（不会既跟着又跟着），下达新的会顶掉旧的。
    """

    def __init__(self, agent=None) -> None:
        self.agent = agent
        self._tasks: Dict[str, StandingTask] = {}
        self._runners: Dict[str, asyncio.Task] = {}
        self._stop_flags: Dict[str, asyncio.Event] = {}
        self._yield_flag = asyncio.Event()   # 置位 = 前台在忙，长期任务集体让路

    # ---------- 让路控制 ----------
    def request_yield(self) -> None:
        # 前台任务开始：长期任务暂停实际动作，避免抢操作权
        self._yield_flag.set()
        for t in self._tasks.values():
            if t.status == LT_RUNNING:
                t.status = LT_YIELDED

    def release_yield(self) -> None:
        # 前台任务结束：长期任务自动恢复，无需主人重新下令
        self._yield_flag.clear()
        for t in self._tasks.values():
            if t.status == LT_YIELDED:
                t.status = LT_RUNNING

    def yielding(self) -> bool:
        return self._yield_flag.is_set()

    async def wait_turn(self, kind: str) -> bool:
        """长期任务每轮动作前调用：前台忙就等，被停就返回 False。"""
        while self._yield_flag.is_set():
            if self.should_stop(kind):
                return False
            await asyncio.sleep(0.3)
        return not self.should_stop(kind)

    # ---------- 状态 ----------
    def should_stop(self, kind: str) -> bool:
        ev = self._stop_flags.get(kind)
        return bool(ev and ev.is_set())

    def active(self) -> List[Dict[str, Any]]:
        return [t.snapshot() for t in self._tasks.values()
                if t.status != LT_STOPPED]

    def get(self, kind: str) -> Optional[StandingTask]:
        return self._tasks.get(kind)

    def busy_kinds(self) -> List[str]:
        return [k for k, t in self._tasks.items() if t.status != LT_STOPPED]

    def say_all(self) -> str:
        act = [t for t in self._tasks.values() if t.status != LT_STOPPED]
        if not act:
            return ""
        return "、".join(t.say() for t in act)

    def _log(self, msg: str, kind: str = "task") -> None:
        if self.agent:
            self.agent.log(msg, kind)

    # ---------- 生命周期 ----------
    async def start(self, task: StandingTask, loop_fn: Callable) -> Dict[str, Any]:
        """启动一个长期任务。loop_fn(task) 内部应循环并调用 wait_turn。"""
        await self.stop(task.kind, why="换新的长期任务")
        ev = asyncio.Event()
        self._stop_flags[task.kind] = ev
        self._tasks[task.kind] = task
        # 若前台正忙，新长期任务直接以让路状态起步，不抢操作权
        if self._yield_flag.is_set():
            task.status = LT_YIELDED

        async def _wrap() -> None:
            try:
                await loop_fn(task)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                self._log(f"长期任务出错：{task.name} → {e}", "warn")
            finally:
                task.status = LT_STOPPED

        self._runners[task.kind] = asyncio.ensure_future(_wrap())
        self._log(f"开始长期任务：{task.name}", "task")
        return {"ok": True, "status": "started", "output": f"好的，我{task.name}~"}

    async def stop(self, kind: str, why: str = "") -> bool:
        """停止某类长期任务（协作式，先置位再取消兜底）。"""
        t = self._tasks.get(kind)
        if t is None:
            return False
        ev = self._stop_flags.get(kind)
        if ev:
            ev.set()
        r = self._runners.get(kind)
        if r and not r.done():
            r.cancel()
            try:
                await asyncio.wait([r], timeout=3)
            except Exception:
                pass
        t.status = LT_STOPPED
        self._tasks.pop(kind, None)
        self._runners.pop(kind, None)
        self._stop_flags.pop(kind, None)
        if why:
            self._log(f"停止长期任务：{t.name}（{why}）", "task")
        return True

    async def stop_all(self, why: str = "主人喊停") -> List[str]:
        names = []
        for kind in list(self._tasks.keys()):
            n = self._tasks[kind].name
            if await self.stop(kind, why):
                names.append(n)
        return names
