"""物品与箱子相关操作：定位、存取、转交、使用。

从 TerrariaAgent 里拆出来，让 agent 专注"调度"，这里专注"物品"。
物品分三大类：hotbar(手持栏) / equipped(装备栏) / inventory(主背包)，
再加上世界里的箱子，一共四个来源。
"""

from typing import Any, Dict, List, Optional


class InventoryOps:
    """背包/箱子操作集合。依赖 agent 提供 mod、缓存与导航。"""

    def __init__(self, agent) -> None:
        self.agent = agent

    @property
    def mod(self):
        return self.agent.mod

    def _log(self, msg: str, kind: str = "item") -> None:
        self.agent.log(msg, kind)

    # ---------------- 查询 ----------------
    async def get_inventory(self) -> Dict[str, Any]:
        # 返回三大类：hotbar(手持栏) / equipped(装备栏) / inventory(主背包)
        return await self.mod.get_inventory()

    def locate_item(self, name: str) -> Dict[str, Any]:
        # 定位物品在：背包/装备/手持/某个箱子。返回第一类命中的位置
        iid = self.agent.resolve_item(name)
        if iid < 0:
            return {"found": False}
        inv_full = self.agent.get_inventory_sync()
        for kind in ("inventory", "hotbar", "equipped"):
            for it in inv_full.get(kind, []):
                if it.get("id") == iid:
                    return {"found": True, "where": kind,
                            "inv_slot": it.get("inv_slot"),
                            "stack": it.get("stack", 0)}
        for c in self.agent.get_chests_sync():
            for it in c.get("items", []):
                if it.get("id") == iid:
                    return {"found": True, "where": "chest", "chest": c,
                            "stack": it.get("stack", 0)}
        return {"found": False}

    def count_item(self, name: str) -> int:
        """身上一共有多少个（不含箱子），长期任务判断"够了没"要用。"""
        iid = self.agent.resolve_item(name)
        if iid < 0:
            return 0
        inv_full = self.agent.get_inventory_sync()
        total = 0
        for kind in ("inventory", "hotbar", "equipped"):
            for it in inv_full.get(kind, []):
                if it.get("id") == iid:
                    total += int(it.get("stack", 0) or 0)
        return total

    async def nearest_chest_with(self, name: str) -> Optional[Dict[str, Any]]:
        # 找最近且含有该物品的箱子
        iid = self.agent.resolve_item(name)
        if iid < 0:
            return None
        best = None
        for c in self.agent.get_chests_sync():
            has = any(it.get("id") == iid for it in c.get("items", []))
            if has and (best is None or c.get("dist", 1e9) < best.get("dist", 1e9)):
                best = c
        return best

    # ---------------- 存取 ----------------
    async def store_to_chest(self, name: str, chest: Dict[str, Any],
                             stack: int = 1) -> bool:
        # 先走到箱子旁，再开箱放入
        loc = self.locate_item(name)
        if not loc.get("found") or loc.get("where") == "chest":
            return False
        if not await self.agent.navigate_to(chest["x"], chest["y"]):
            return False
        ok = await self.mod.store_item(
            chest["x"], chest["y"], loc["inv_slot"], stack)
        if ok:
            self._log(f"把 {name}×{stack} 放进了箱子({chest['x']},{chest['y']})")
        return ok

    async def take_from_chest(self, name: str, chest: Dict[str, Any],
                              stack: int = 1) -> bool:
        iid = self.agent.resolve_item(name)
        if iid < 0:
            return False
        if not await self.agent.navigate_to(chest["x"], chest["y"]):
            return False
        ok = await self.mod.take_from_chest(chest["x"], chest["y"], iid, stack)
        if ok:
            self._log(f"从箱子({chest['x']},{chest['y']})取了 {name}×{stack}")
        return ok

    # ---------------- 交互 ----------------
    async def hand_to_player(self, name: str, stack: int = 1) -> bool:
        # 猫娘把物品丢到脚下，玩家拾取（转交）
        iid = self.agent.resolve_item(name)
        if iid < 0:
            return False
        ok = await self.agent.equip.drop_for_player(iid, stack)
        if ok:
            self._log(f"给了玩家 {name}×{stack}（丢地上）")
        return ok

    async def use_item_by_name(self, name: str) -> bool:
        # 猫娘使用指定物品（喝药/手持等）
        ok = await self.agent.equip.use_by_name(name, self.agent.resolve_item)
        if ok:
            self._log(f"使用了 {name}")
        return ok
