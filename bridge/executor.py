"""任务执行器：任务生命周期与占用仲裁的唯一权威（谁在做、能否打断、怎么停）。"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 来源优先级：主人命令 > 自主行为。低优先级不能打断高优先级
SRC_OWNER = "owner"
SRC_AUTO = "auto"
_PRIORITY = {SRC_OWNER: 10, SRC_AUTO: 1}


@dataclass
class TaskInfo:
    name: str
    source: str = SRC_AUTO
    phase: str = "think"          # think(想) / plan(处理) / act(做) / done
    steps: List[str] = field(default_factory=list)
    step_index: int = 0
    total_steps: int = 0
    started_at: float = field(default_factory=time.time)
    note: str = ""

    def snapshot(self) -> Dict[str, Any]:
        return {
            "name": self.name, "source": self.source, "phase": self.phase,
            "step": f"{self.step_index}/{self.total_steps}" if self.total_steps else "",
            "steps": list(self.steps), "note": self.note,
            "elapsed": round(time.time() - self.started_at, 1),
        }


class TaskExecutor:
    """单槽位执行器：同一时刻只有一个任务在跑。

    主人命令可抢占自主行为；自主行为遇到任何进行中的任务则让位不触发。
    """

    def __init__(self, agent=None) -> None:
        self.agent = agent
        self._current: Optional[TaskInfo] = None
        self._task: Optional[asyncio.Task] = None
        self._cancel = asyncio.Event()
        self._lock = asyncio.Lock()
        self._last: Optional[Dict[str, Any]] = None

    # --- 状态查询 ---
    def busy(self) -> bool:
        return self._current is not None

    def current(self) -> Optional[Dict[str, Any]]:
        return self._current.snapshot() if self._current else None

    def last_result(self) -> Optional[Dict[str, Any]]:
        return self._last

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _log(self, msg: str, kind: str = "task") -> None:
        if self.agent:
            self.agent.log(msg, kind)

    # --- 占用仲裁 ---
    def can_start(self, source: str) -> bool:
        if self._current is None:
            return True
        return _PRIORITY.get(source, 0) > _PRIORITY.get(self._current.source, 0)

    async def cancel_current(self, why: str = "") -> bool:
        # 真正取消：置取消位 + 取消协程 + 停下 mod 侧动作
        if self._current is None:
            return False
        name = self._current.name
        self._cancel.set()
        if self.agent and getattr(self.agent, "mining", None):
            self.agent.mining.cancel()
        if self._task and not self._task.done():
            self._task.cancel()
            # 只等它真正停下，异常由 run() 那侧接住，这里不重复消费
            try:
                await asyncio.wait([self._task], timeout=3)
            except Exception:
                pass
        self._current = None
        self._task = None
        self._log(f"任务被打断：{name}（{why}）", "warn")
        return True

    async def run(self, name: str, coro_fn: Callable, source: str = SRC_AUTO,
                  steps: Optional[List[str]] = None) -> Dict[str, Any]:
        """执行一个任务。coro_fn 接收本 TaskInfo，可用 should_stop() 协作式退出。"""
        async with self._lock:
            if not self.can_start(source):
                cur = self._current.name if self._current else ""
                return {"ok": False, "status": "busy", "output": f"正忙着「{cur}」，这条先不接"}
            if self._current is not None:
                await self.cancel_current(f"被{source}的「{name}」接管")
            self._cancel.clear()
            info = TaskInfo(name=name, source=source, steps=steps or [],
                            total_steps=len(steps or []))
            self._current = info
            # 把实际工作放进独立 task，这样打断时取消的是工作本身而非调用方
            inner = asyncio.ensure_future(coro_fn(info))
            self._task = inner

        self._log(f"开始任务：{name}", "task")
        # 前台一开工，长期任务（跟随/挖矿）自动让路，避免抢操作权
        lt = getattr(self.agent, "longterm", None) if self.agent else None
        if lt:
            lt.request_yield()
        try:
            result = await inner
            out = result if isinstance(result, dict) else {"ok": True, "output": str(result)}
        except asyncio.CancelledError:
            self._last = {"ok": False, "status": "cancelled", "output": f"「{name}」被打断了"}
            if self._current is info:
                self._current = None
                self._task = None
            if lt and not self.busy():
                lt.release_yield()
            return self._last
        except Exception as e:
            self._log(f"任务异常：{name} → {e}", "warn")
            out = {"ok": False, "status": "error", "output": f"「{name}」出错了：{e}"}
        finally:
            if self._current is info:
                info.phase = "done"
                self._current = None
                self._task = None
            # 前台空了才恢复长期任务，避免被接管时提前恢复
            if lt and not self.busy():
                lt.release_yield()

        out.setdefault("ok", True)
        out.setdefault("status", "ok" if out.get("ok") else "failed")
        self._last = out
        self._log(f"任务结束：{name} → {out.get('status')}", "task")
        return out

    def should_stop(self) -> bool:
        # 任务内部循环用它做协作式退出，保证能被主人随时叫停
        return self._cancel.is_set()
