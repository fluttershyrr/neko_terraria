"""tModLoader 服务端 mod 接口：状态回报 + 精细动作（移动/放方块/抓钩/合成/装备）。"""

from typing import Any, Dict, List, Optional

from .connection import Connection


class ModLink:
    """封装需要 mod 支持的精细动作与状态查询。"""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    # 注意：mod 对每条命令都会回 ACK，这些动作也必须把回执读走，
    # 否则残留回执会让后续请求读到上一条的答复（串线）
    async def move(self, directions: List[str]) -> None:
        await self.conn.request_mod({"cmd": "move", "dirs": directions})

    async def place_tile(self, x: int, y: int, tile_type: int) -> bool:
        resp = await self.conn.request_mod(
            {"cmd": "place_tile", "x": x, "y": y, "tile": tile_type})
        return bool(resp and resp.get("ok"))

    async def break_tile(self, x: int, y: int) -> bool:
        resp = await self.conn.request_mod(
            {"cmd": "break_tile", "x": x, "y": y})
        return bool(resp and resp.get("ok"))

    async def hook(self, x: int, y: int) -> None:
        await self.conn.request_mod({"cmd": "hook", "x": x, "y": y})

    async def use_item(self, x: int = -1, y: int = -1) -> None:
        await self.conn.request_mod({"cmd": "use_item", "x": x, "y": y})

    async def select_item(self, slot: int) -> None:
        await self.conn.request_mod({"cmd": "select_item", "slot": slot})

    async def craft(self, item_name: str = "", item_id: int = -1,
                    amount: int = 1) -> int:
        cmd = {"cmd": "craft", "amount": amount}
        if item_name:
            cmd["item_name"] = item_name
        if item_id > 0:
            cmd["item_id"] = item_id
        resp = await self.conn.request_mod(cmd, timeout=5.0)
        return int(resp.get("crafted", 0)) if resp else 0

    async def equip_item(self, inv_slot: int, equip_slot: int) -> bool:
        resp = await self.conn.request_mod(
            {"cmd": "equip", "inv": inv_slot, "equip": equip_slot})
        return bool(resp and resp.get("ok"))

    async def give_item(self, item_id: int, stack: int = 1) -> bool:
        resp = await self.conn.request_mod(
            {"cmd": "give_item", "item_id": item_id, "stack": stack})
        return bool(resp and resp.get("ok"))

    async def drop_item(self, inv_slot: int, stack: int = 1) -> bool:
        # 猫娘把背包某槽位物品丢到脚下，玩家拾取（转交）
        resp = await self.conn.request_mod(
            {"cmd": "drop_item", "slot": inv_slot, "stack": stack})
        return bool(resp and resp.get("ok"))

    async def use_item_slot(self, inv_slot: int) -> bool:
        # 选中并使用背包某槽位物品
        resp = await self.conn.request_mod(
            {"cmd": "use_item_slot", "slot": inv_slot})
        return bool(resp and resp.get("ok"))

    async def get_inventory(self) -> Dict[str, Any]:
        # 返回三大类：hotbar(手持栏) / equipped(装备栏) / inventory(主背包)
        resp = await self.conn.request_mod({"cmd": "get_inventory"})
        if not resp:
            return {"hotbar": [], "equipped": [], "inventory": []}
        return {
            "hotbar": resp.get("hotbar", []),
            "equipped": resp.get("equipped", []),
            "inventory": resp.get("inventory", []),
            "selected_slot": resp.get("selected_slot", 0),
        }

    async def enum_chests(self) -> List[Dict[str, Any]]:
        resp = await self.conn.request_mod({"cmd": "enum_chests"}, timeout=5.0)
        return resp.get("chests", []) if resp else []

    async def store_item(self, chest_x: int, chest_y: int,
                         inv_slot: int, stack: int = 1) -> bool:
        resp = await self.conn.request_mod({
            "cmd": "store_item", "x": chest_x, "y": chest_y,
            "slot": inv_slot, "stack": stack})
        return bool(resp and resp.get("ok"))

    async def take_from_chest(self, chest_x: int, chest_y: int,
                              item_id: int, stack: int = 1) -> bool:
        resp = await self.conn.request_mod({
            "cmd": "take_chest", "x": chest_x, "y": chest_y,
            "item_id": item_id, "stack": stack})
        return bool(resp and resp.get("ok"))

    async def navigate_to(self, x: int, y: int, timeout: int = 15) -> bool:
        # 寻路是长任务：整段占锁等回执，期间不允许别的请求插进来抢答复
        resp = await self.conn.request_mod(
            {"cmd": "navigate_to", "x": x, "y": y, "timeout": timeout},
            timeout=timeout + 2)
        return bool(resp and resp.get("ok"))

    async def get_capabilities(self) -> Dict[str, Any]:
        resp = await self.conn.request_mod({"cmd": "get_capabilities"})
        return resp if resp else {}

    async def scan_ledges(self, x0: int, y0: int, x1: int, y1: int) -> List[Dict[str, Any]]:
        # 扫描两点之间的可落脚平台，供分段爬升规划
        resp = await self.conn.request_mod({"cmd": "scan_ledges", "x0": x0, "y0": y0,
                                            "x1": x1, "y1": y1}, timeout=5.0)
        return resp.get("points", []) if resp else []

    async def get_recipes(self, category: str = "all") -> List[Dict[str, Any]]:
        resp = await self.conn.request_mod({"cmd": "get_recipes", "cat": category},
                                           timeout=5.0)
        return resp.get("recipes", []) if resp else []

    async def get_state(self, player_name: str = "") -> Dict[str, Any]:
        resp = await self.conn.request_mod(
            {"cmd": "get_state", "player_name": player_name})
        if not resp or resp.get("found") is False:
            return {}
        # 将 mod 原生字段映射为 Python 习惯字段，供大脑/战斗统一使用
        p = resp.get("player", {})
        npcs = resp.get("nearbyNpcs", [])
        out = {
            "hp": p.get("hp", 0), "mp": p.get("mana", 0),
            "max_life": p.get("maxLife", 0), "max_mp": p.get("maxMana", 0),
            "life": p.get("hp", 0),
            "x": p.get("x", 0), "y": p.get("y", 0),
            "tile_x": p.get("tileX", 0), "tile_y": p.get("tileY", 0),
            "velocity_x": p.get("velocityX", 0), "velocity_y": p.get("velocityY", 0),
            "grounded": p.get("grounded", True),
            "nearby_npcs": [
                {"name": n.get("name", ""), "slot": n.get("slot", 0),
                 "life": n.get("life", 0), "tile_x": n.get("tileX", 0),
                 "tile_y": n.get("tileY", 0), "damage": n.get("damage", 0)}
                for n in npcs
            ],
            "nearby_players": [
                {"name": pl.get("name", ""), "tile_x": pl.get("tileX", 0),
                 "tile_y": pl.get("tileY", 0)}
                for pl in resp.get("nearbyPlayers", [])
            ],
            "time_of_day": "白天" if resp.get("time", {}).get("dayTime", True) else "夜晚",
        }
        return out

    async def enum_items(self) -> List[Dict[str, Any]]:
        # 物品全表很大，给足超时
        resp = await self.conn.request_mod({"cmd": "enum_items"}, timeout=15.0)
        return resp.get("mods", []) if resp else []

    async def get_server_info(self) -> Dict[str, Any]:
        """查询 Mod 端的服务器环境信息：版本、难度、世界大小、邪恶类型等。
        返回 dict，字段:
          tmod_version_str  Packet 1 需要的完整版本字符串
          tmod_version      tML 版本号 (如 "2026.6.3.0")
          terraria_version  Terraria 版本号
          game_mode         世界难度 (0=Classic,1=Expert,2=Master,3=Journey)
          world_size        Small/Medium/Large
          evil_type         Corruption/Crimson
          world_name        世界名称
        """
        resp = await self.conn.request_mod({"cmd": "get_server_info"}, timeout=5.0)
        return resp if resp else {}
