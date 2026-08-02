"""世界推演：在脑子里把任务先跑一遍，再决定要不要动手。

原来的评估是"逐步独立检查"，会犯一个很蠢的错：
    ["挖10个铁", "合成铁镐"]
    → 检查第2步时问"现在有铁吗"，答"没有"，于是拒绝。
    可第1步明明就会挖到铁。

所以要有一份"虚拟背包"：从现在的真实背包出发，
一步步推演每步的产出与消耗，让后面的步骤看得到前面的成果。
这样才谈得上"会想"。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class VirtualInventory:
    """推演用的虚拟背包：真实库存的一份可涂改的副本。"""

    counts: Dict[str, int] = field(default_factory=dict)
    has_pickaxe: bool = False
    has_hook: bool = False
    rope: int = 0
    dirt: int = 0

    def copy(self) -> "VirtualInventory":
        return VirtualInventory(dict(self.counts), self.has_pickaxe,
                                self.has_hook, self.rope, self.dirt)

    def count(self, item: str) -> int:
        return int(self.counts.get(item, 0))

    def add(self, item: str, n: int) -> None:
        if not item or n <= 0:
            return
        self.counts[item] = self.count(item) + n
        # 拿到镐子/钩爪，能力也跟着变，后续步骤要看得到
        if "镐" in item:
            self.has_pickaxe = True
        if "钩" in item:
            self.has_hook = True
        if "绳" in item or "梯" in item:
            self.rope += n
        if item in ("土块", "泥土"):
            self.dirt += n

    def take(self, item: str, n: int) -> bool:
        """扣减；不够则返回 False 且不改动。"""
        if self.count(item) < n:
            return False
        self.counts[item] = self.count(item) - n
        if item in ("土块", "泥土"):
            self.dirt = max(0, self.dirt - n)
        return True


@dataclass
class SimStep:
    """一步推演的结果。"""

    index: int
    desc: str
    ok: bool = True
    gap: str = ""            # 缺什么（人话）
    need_item: str = ""      # 缺的物品，供补救用
    need_amount: int = 0
    produces: str = ""       # 这步会产出什么
    note: str = ""


@dataclass
class SimResult:
    """整段推演结果。"""

    steps: List[SimStep] = field(default_factory=list)
    final: Optional[VirtualInventory] = None
    ok: bool = True

    def first_gap(self) -> Optional[SimStep]:
        for s in self.steps:
            if not s.ok:
                return s
        return None

    def gaps(self) -> List[SimStep]:
        return [s for s in self.steps if not s.ok]


# 简易配方表：合成物 -> (材料, 每份数量)
# mod 能给出真实配方时以 mod 为准，这里只作兜底常识。
FALLBACK_RECIPE: Dict[str, List[Tuple[str, int]]] = {
    "铁镐": [("铁锭", 12), ("木材", 3)],
    "铁锭": [("铁矿", 3)],
    "铜镐": [("铜锭", 10), ("木材", 3)],
    "铜锭": [("铜矿", 3)],
    "金镐": [("金锭", 12), ("木材", 3)],
    "金锭": [("金矿", 4)],
    "银锭": [("银矿", 4)],
    "火把": [("木材", 1)],
    "木台": [("木材", 10)],
}

# 挖矿类动作默认产出自身
MINE_ACTIONS = ("mine", "gather")


class WorldModel:
    """从真实状态出发，推演一串步骤能不能顺利做完。"""

    def __init__(self, agent, book=None) -> None:
        self.agent = agent
        self._recipes: Dict[str, List[Tuple[str, int]]] = {}
        # 配方书：mod 真实配方的来源。没有它就只能靠常识表，
        # mod 物品会全军覆没。
        self.book = book if book is not None else getattr(
            agent, "recipe_book", None)

    # ---------- 快照 ----------
    async def snapshot(self) -> VirtualInventory:
        """把当前真实背包与能力拍成虚拟背包。"""
        vi = VirtualInventory()
        cap = self.agent.capability
        try:
            await cap.refresh()
            vi.has_pickaxe = cap.has_pickaxe()
            vi.has_hook = cap.has_hook()
            vi.rope = cap.rope_count()
            vi.dirt = cap.dirt_count()
        except Exception:
            pass

        try:
            inv = self.agent.get_inventory_sync() or {}
            for kind in ("inventory", "hotbar", "equipped"):
                for it in inv.get(kind, []):
                    name = it.get("name") or ""
                    if name:
                        vi.counts[name] = vi.counts.get(name, 0) + int(
                            it.get("stack", 0) or 0)
        except Exception:
            pass
        return vi

    # ---------- 配方 ----------
    async def recipe_of(self, item: str) -> List[Tuple[str, int]]:
        """查配方：先问配方书（含 mod 真实配方），再退到常识表。"""
        if item in self._recipes:
            return self._recipes[item]
        mats: List[Tuple[str, int]] = []
        if self.book is not None:
            try:
                await self.book.refresh()
                mats = self.book.materials_of(item)
            except Exception:
                mats = []
        if not mats:
            mats = list(FALLBACK_RECIPE.get(item, []))
        self._recipes[item] = mats
        return mats

    async def stations_of(self, item: str) -> List[str]:
        """这件东西要在哪个合成站做。"""
        if self.book is None:
            return []
        try:
            await self.book.refresh()
            return self.book.stations_of(item)
        except Exception:
            return []

    async def station_ready(self, item: str) -> Tuple[bool, str]:
        """合成站够不够得着。mod 配方常要专属站台，缺了就白规划。"""
        stations = await self.stations_of(item)
        if not stations:
            return True, ""
        try:
            near = set(self.agent.capability.nearby_stations())
        except Exception:
            near = set()
        if not near:
            # mod 没上报站台信息就不拦，留给实际合成时反馈
            return True, ""
        missing = [s for s in stations if s not in near]
        if missing:
            from .recipe_book import station_cn
            return False, "、".join(station_cn(s) for s in missing)
        return True, ""

    # ---------- 推演 ----------
    async def simulate(self, steps: List[Dict[str, Any]],
                       start: Optional[VirtualInventory] = None) -> SimResult:
        """按顺序推演每一步，让后面的步骤看得到前面的产出。"""
        vi = (start or await self.snapshot()).copy()
        res = SimResult(steps=[], final=vi)

        for i, s in enumerate(steps):
            action = str(s.get("action", "")).lower()
            item = str(s.get("item", "") or "")
            amt = int(s.get("amount", 1) or 1)
            st = SimStep(index=i + 1, desc=self._desc(action, item, amt))

            if action in MINE_ACTIONS:
                if not vi.has_pickaxe:
                    st.ok = False
                    st.gap = "没有镐子，挖不了"
                    st.need_item = "镐"
                else:
                    have = vi.count(item)
                    if have >= amt:
                        # 已经够了，这步其实可以省掉
                        st.note = f"背包里已经有 {have} 个{item}，够了"
                    vi.add(item, amt)
                    st.produces = item

            elif action == "craft":
                mats = await self.recipe_of(item)
                if not mats:
                    # 配方书里查不到：可能是 mod 物品但配方没同步
                    st.ok = False
                    st.gap = f"我不知道{item}怎么做"
                    st.need_item = item
                    st.need_amount = amt
                    res.steps.append(st)
                    continue

                ok_station, lack_station = await self.station_ready(item)
                missing = []
                for mname, mstack in mats:
                    need = mstack * amt
                    if vi.count(mname) < need:
                        missing.append((mname, need - vi.count(mname)))
                if missing:
                    st.ok = False
                    mn, mneed = missing[0]
                    st.gap = "、".join(f"缺 {n} 个{m}" for m, n in missing)
                    st.need_item = mn
                    st.need_amount = mneed
                elif not ok_station:
                    st.ok = False
                    st.gap = f"没有{lack_station}，做不了"
                    st.need_item = lack_station
                    st.need_amount = 1
                else:
                    for mname, mstack in mats:
                        vi.take(mname, mstack * amt)
                    vi.add(item, amt)
                    st.produces = item
                    if self.book is not None:
                        r = self.book.find(item)
                        if r is not None and r.is_modded():
                            st.note = f"{r.mod} 的配方：{r.say()}"

            elif action == "fetch":
                # 取箱子里的东西：能不能取到得问真实世界
                chest = None
                try:
                    chest = await self.agent.nearest_chest_with(item)
                except Exception:
                    chest = None
                if chest is None:
                    st.ok = False
                    st.gap = f"附近箱子里没有 {item}"
                    st.need_item = item
                    st.need_amount = amt
                else:
                    vi.add(item, amt)
                    st.produces = item
                    st.note = f"在箱子({chest.get('x')},{chest.get('y')})"

            elif action == "give":
                if vi.count(item) < amt:
                    st.ok = False
                    st.gap = f"身上只有 {vi.count(item)} 个{item}，不够给"
                    st.need_item = item
                    st.need_amount = amt - vi.count(item)
                else:
                    vi.take(item, amt)

            elif action in ("climb", "goto"):
                tx, ty = int(s.get("x", 0) or 0), int(s.get("y", 0) or 0)
                try:
                    plan = await self.agent.planner.plan_climb(tx, ty)
                    if plan.feasible:
                        st.note = f"要{len(plan.legs)}段：{plan.describe()}"
                    else:
                        st.ok = False
                        st.gap = plan.blocked_reason or "上不去"
                        st.need_item = "钩爪"
                except Exception:
                    st.note = "路线待定"

            res.steps.append(st)

        res.final = vi
        res.ok = all(s.ok for s in res.steps)
        return res

    @staticmethod
    def _desc(action: str, item: str, amt: int) -> str:
        table = {"mine": "挖", "gather": "挖", "craft": "合成",
                 "fetch": "取", "give": "给主人", "climb": "爬到",
                 "goto": "走到", "follow": "回到主人身边"}
        head = table.get(action, action)
        if action in ("climb", "goto", "follow"):
            return head
        return f"{head}{item}x{amt}" if item else head
