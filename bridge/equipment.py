"""装备管理：自动穿戴、使用、转交（丢地上给玩家）。"""

from typing import Any, Dict, List, Optional

from .mod_link import ModLink


class EquipmentManager:
    def __init__(self, mod: ModLink) -> None:
        self.mod = mod

    async def _all_items(self) -> List[Dict[str, Any]]:
        # 三大类展平为单列表，便于统一查找
        inv = await self.mod.get_inventory()
        return (inv.get("hotbar", []) + inv.get("equipped", [])
                + inv.get("inventory", []))

    async def auto_equip(self) -> bool:
        # 契约：mod 的 SendInventory 需返回 inv_slot / equip_slot / defense
        inv = await self._all_items()
        best: Dict[int, int] = {}
        for item in inv:
            slot = item.get("equip_slot")
            if slot is None or item.get("defense", 0) <= 0:
                continue
            inv_slot = item.get("inv_slot", item.get("id"))
            if inv_slot is None:
                continue
            if slot not in best or item["defense"] > inv[best[slot]].get("defense", 0):
                best[slot] = inv_slot
        ok = True
        for equip_slot, inv_slot in best.items():
            if not await self.mod.equip_item(inv_slot, equip_slot):
                ok = False
        return ok

    async def give_to_player(self, item_id: int, stack: int = 1) -> bool:
        return await self.mod.give_item(item_id, stack)

    async def drop_for_player(self, item_id: int, stack: int = 1) -> bool:
        # 在背包里找到该物品，丢到脚下让玩家拾取
        inv = await self._all_items()
        for it in inv:
            if it.get("id") == item_id and it.get("stack", 0) > 0:
                return await self.mod.drop_item(it["inv_slot"], stack)
        return False

    async def use_by_name(self, name: str, resolve) -> bool:
        # resolve(name)->item_id；在背包里找到后选中并使用
        iid = resolve(name)
        if iid < 0:
            return False
        inv = await self._all_items()
        for it in inv:
            if it.get("id") == iid:
                return await self.mod.use_item_slot(it["inv_slot"])
        return False
