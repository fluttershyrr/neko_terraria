"""补救推理：缺东西的时候自己想办法，而不是甩一句"我做不了"。

原来的大脑一遇到缺口就拒绝：
    "挖铁" + 没镐子 → "我没有镐子，挖不了矿" → 结束。
真正会想的猫娘应该继续往下推一层：
    没镐子 → 箱子里有吗？→ 有，那就先去取
                        → 没有，那能合成吗？→ 能，材料够吗？→ 够，先合成
                                                            → 不够，先挖材料

所以补救是一棵有深度的树，按代价从小到大试：
    身上已有 < 箱子里取 < 合成 < 现挖 < 求助主人
每找到一条路就生成"前置步骤"，插到原步骤前面。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 补救代价，越小越优先
COST_HAVE = 0
COST_FETCH = 1
COST_CRAFT = 2
COST_MINE = 3
COST_ASK = 9

# 镐子这类"能力物品"的候选，从最容易得到的开始
PICKAXE_CANDIDATES = ("铜镐", "铁镐", "银镐", "金镐")
# mod 候选上限：装了大型整合包时物品成千上万，不能逐个查箱子
MAX_MOD_CANDIDATES = 12
MAX_CRAFT_TRY = 4
# 矿 -> 锭
ORE_TO_BAR = {"铁矿": "铁锭", "铜矿": "铜锭", "银矿": "银锭",
              "金矿": "金锭", "锡矿": "锡锭", "铅矿": "铅锭"}


@dataclass
class Fix:
    """一条补救方案。"""

    how: str                                   # fetch / craft / mine / ask
    desc: str                                  # 人话
    cost: int = COST_ASK
    steps: List[Dict[str, Any]] = field(default_factory=list)  # 要插入的前置步骤

    def say(self) -> str:
        return self.desc


class Reasoner:
    """针对推演出来的缺口，递归找补救办法。"""

    def __init__(self, agent, world) -> None:
        self.agent = agent
        self.world = world

    async def fix_for(self, item: str, amount: int, vi,
                      depth: int = 0) -> Optional[Fix]:
        """给"缺 amount 个 item"找一条最省事的补救路。"""
        if depth > 3 or not item:
            return None

        # 能力物品（镐/钩）要先落成具体物品名
        if item in ("镐", "钩爪"):
            return await self._fix_capability(item, vi, depth)

        # 1) 身上其实就有
        if vi.count(item) >= amount:
            return Fix(how="have", desc=f"身上已经有{item}了", cost=COST_HAVE)

        # 2) 箱子里取
        try:
            chest = await self.agent.nearest_chest_with(item)
        except Exception:
            chest = None
        if chest is not None:
            return Fix(how="fetch",
                       desc=f"箱子({chest.get('x')},{chest.get('y')})里有{item}，先去取",
                       cost=COST_FETCH,
                       steps=[{"action": "fetch", "item": item,
                               "amount": amount}])

        # 3) 合成（材料不够就继续往下推；mod 配方也走这条）
        mats = await self.world.recipe_of(item)
        if mats:
            # 站台够不着就别白规划，直接说清楚缺哪个台子
            ok_station, lack = await self.world.station_ready(item)
            if not ok_station:
                return Fix(how="ask", desc=f"做{item}要{lack}，我这儿没有",
                           cost=COST_ASK)
            pre: List[Dict[str, Any]] = []
            feasible = True
            reasons = []
            for mname, mstack in mats:
                need = mstack * amount
                lack = need - vi.count(mname)
                if lack > 0:
                    sub = await self.fix_for(mname, lack, vi, depth + 1)
                    if sub is None:
                        feasible = False
                        reasons.append(f"缺{mname}又搞不到")
                        break
                    pre.extend(sub.steps)
                    reasons.append(sub.desc)
            if feasible:
                pre.append({"action": "craft", "item": item, "amount": amount})
                head = f"合成{item}"
                if reasons:
                    head += "（" + "、".join(r for r in reasons if r) + "）"
                return Fix(how="craft", desc=head, cost=COST_CRAFT, steps=pre)

        # 4) 自己挖（矿物类，mod 的英文名矿石也要认得）
        if self._is_mineable(item):
            if vi.has_pickaxe or self._is_wood(item):
                return Fix(how="mine", desc=f"自己去挖{amount}个{item}",
                           cost=COST_MINE,
                           steps=[{"action": "mine", "item": item,
                                   "amount": amount}])

        # 5) 实在没辙，求助主人
        return Fix(how="ask", desc=f"我搞不到{item}，主人能给我吗", cost=COST_ASK)

    def _is_wood(self, item: str) -> bool:
        low = (item or "").lower()
        return item == "木材" or "wood" in low

    def _is_mineable(self, item: str) -> bool:
        """这东西能不能自己挖出来。

        mod 矿石叫 "Aerialite Ore" 这种英文名，只判断中文"矿"结尾会漏掉，
        导致猫娘明明能挖却说搞不到。
        """
        if not item:
            return False
        low = item.lower()
        if item.endswith("矿") or item in ("木材", "石块", "土块"):
            return True
        # 英文常见矿物/可采集词缀（mod 物品普遍沿用这套命名）
        for kw in ("ore", "wood", "stone", "block", "gem", "bar ore",
                   "crystal", "shard", "dirt", "sand", "ingot ore"):
            if low.endswith(kw) or low.endswith(kw + "s"):
                return True
        # 注册表说它是材料/可放置的，多半也能采
        reg = getattr(self.agent, "registry", None)
        if reg is not None:
            try:
                info = reg.describe(item)
                if info.get("use") in ("material", "placeable"):
                    return True
                if "ore" in info.get("tags", []):
                    return True
            except Exception:
                pass
        return False

    def _candidates(self, kind: str) -> List[str]:
        """能力物品的候选名单：原版常见 + mod 里同类物品。

        只认死那几个原版镐子的话，装了 mod 的存档会漏掉一堆能用的工具。
        """
        base = list(PICKAXE_CANDIDATES) if kind == "镐" else ["抓钩", "Grappling Hook"]
        reg = getattr(self.agent, "registry", None)
        if reg is None:
            return base
        want = "tool" if kind == "镐" else "accessory"
        try:
            names: List[str] = []
            for mod, items in getattr(reg, "mods", {}).items():
                uses = reg.uses.get(mod, {})
                tags = reg.tags.get(mod, {})
                for name in items:
                    if uses.get(name) != want:
                        continue
                    tg = tags.get(name, [])
                    if kind == "镐" and ("pickaxe" in tg or "pick" in tg
                                         or "镐" in name or "pickaxe" in name):
                        names.append(name)
                    elif kind == "钩爪" and ("hook" in tg or "钩" in name
                                             or "hook" in name):
                        names.append(name)
            # mod 物品可能成百上千，逐个查箱子会把 mod 通信打爆，取前若干个
            return base + names[:MAX_MOD_CANDIDATES]
        except Exception:
            return base

    async def _fix_capability(self, kind: str, vi, depth: int) -> Optional[Fix]:
        """缺镐子/钩爪这类能力物品：挑一个最容易到手的具体物品。"""
        cands = self._candidates(kind)
        best: Optional[Fix] = None
        for name in cands:
            # 身上有就直接用
            if vi.count(name) > 0:
                return Fix(how="have", desc=f"身上有{name}", cost=COST_HAVE)
            try:
                chest = await self.agent.nearest_chest_with(name)
            except Exception:
                chest = None
            if chest is not None:
                return Fix(how="fetch",
                           desc=f"箱子里有{name}，先去拿上",
                           cost=COST_FETCH,
                           steps=[{"action": "fetch", "item": name,
                                   "amount": 1}])
        # 箱子里都没有，试试合成最便宜的那个（只在少量候选里找，别递归爆炸）
        for name in cands[:MAX_CRAFT_TRY]:
            f = await self.fix_for(name, 1, vi, depth + 1)
            if f and f.how in ("craft", "mine") and (best is None or f.cost < best.cost):
                best = f
        if best:
            return best
        return Fix(how="ask", desc=f"我没有{kind}，主人给我一个吧", cost=COST_ASK)
