"""分段路径规划：把"深坑回地面"等复杂垂直移动拆成逐段可执行的落脚点，每段执行后重评估。"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Leg:
    """一个路段：从当前位置到 (tx, ty)，用 method 手段完成。"""
    tx: int
    ty: int
    method: str            # 'walk' | 'hook' | 'rope' | 'dirt' | 'dig'
    height_diff: int = 0
    note: str = ""


@dataclass
class Plan:
    legs: List[Leg] = field(default_factory=list)
    feasible: bool = True
    blocked_reason: str = ""
    blocked_at: int = 0     # 第几段卡住（0 基）

    def describe(self) -> str:
        if not self.feasible and not self.legs:
            return self.blocked_reason
        parts = [f"{i+1}.{l.method}到({l.tx},{l.ty})" for i, l in enumerate(self.legs)]
        s = " → ".join(parts)
        if not self.feasible:
            s += f"，之后{self.blocked_reason}"
        return s


class Planner:
    """基于地形扫描 + 能力，把垂直落差拆成多段（中途平台作为中继点）。"""

    def __init__(self, agent) -> None:
        self.agent = agent

    async def plan_climb(self, tx: int, ty: int) -> Plan:
        """规划从当前位置爬到 (tx, ty)。ty 越小越高。"""
        st = await self.agent.refresh_state()
        if not st:
            return Plan(feasible=False, blocked_reason="拿不到位置信息")
        cx = int(st.get("tile_x", 0))
        cy = int(st.get("tile_y", 0))
        cap = self.agent.capability
        await cap.refresh()

        total = cy - ty
        if total <= 3:
            return Plan(legs=[Leg(tx, ty, "walk", total)])

        ledges = await self._scan_ledges(cx, cy, tx, ty)
        return self._build(cx, cy, tx, ty, ledges, cap)

    async def _scan_ledges(self, cx: int, cy: int, tx: int, ty: int) -> List[Dict[str, int]]:
        """向 mod 请求两点之间的可落脚平台，按由低到高排序。"""
        pts = await self.agent.mod.scan_ledges(cx, cy, tx, ty)
        out = []
        for p in pts or []:
            py = int(p.get("y", 0))
            if ty <= py < cy:
                out.append({"x": int(p.get("x", cx)), "y": py})
        out.sort(key=lambda p: -p["y"])
        return out

    def _build(self, cx: int, cy: int, tx: int, ty: int,
               ledges: List[Dict[str, int]], cap) -> Plan:
        plan = Plan()
        px, py = cx, cy
        stops = ledges + [{"x": tx, "y": ty}]
        budget_dirt = cap.dirt_count()
        budget_rope = cap.rope_count()

        for stop in stops:
            diff = py - stop["y"]
            if diff <= 0:
                continue
            method = self._pick(diff, cap, budget_dirt, budget_rope)
            if not method:
                plan.feasible = False
                plan.blocked_at = len(plan.legs)
                plan.blocked_reason = self._lack(diff, cap, budget_dirt, budget_rope)
                break
            if method == "dirt":
                budget_dirt -= diff
            elif method == "rope":
                budget_rope -= diff
            plan.legs.append(Leg(stop["x"], stop["y"], method, diff))
            px, py = stop["x"], stop["y"]

        if not plan.legs and plan.feasible:
            plan.feasible = False
            plan.blocked_reason = "找不到可以落脚的地方"
        return plan

    def _pick(self, diff: int, cap, dirt: int, rope: int) -> str:
        # 钩锁优先（最省资源），其次绳梯，最后垫土
        if cap.has_hook() and diff <= cap.hook_range():
            return "hook"
        if rope >= diff:
            return "rope"
        if dirt >= diff and diff <= 25:
            return "dirt"
        return ""

    def _lack(self, diff: int, cap, dirt: int, rope: int) -> str:
        lacks = []
        if not cap.has_hook():
            lacks.append("没有钩锁")
        elif diff > cap.hook_range():
            lacks.append(f"这段有{diff}格、钩锁只够{cap.hook_range()}格")
        if rope < diff:
            lacks.append("绳梯不够")
        if dirt < diff:
            lacks.append("土块不够")
        return "、".join(lacks)
