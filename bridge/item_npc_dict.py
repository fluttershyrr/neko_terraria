"""泰拉瑞亚原版物品/NPC id 映射，并提供 mod 扩展物品加载。"""

from typing import Dict

ITEM_IDS: Dict[str, int] = {
    "dirt": 0, "stone": 1, "wood": 9, "gel": 23,
    "copper_ore": 7, "tin_ore": 8, "iron_ore": 9, "lead_ore": 10,
    "silver_ore": 11, "tungsten_ore": 12, "gold_ore": 13, "platinum_ore": 14,
    "copper_bar": 20, "tin_bar": 21, "iron_bar": 22, "lead_bar": 23,
    "silver_bar": 21, "tungsten_bar": 22, "gold_bar": 19, "platinum_bar": 1999,
    "demonite_ore": 57, "crimtane_ore": 58, "hellstone": 58,
    "obsidian": 58, "wood_sword": 1, "wood_pickaxe": 2, "wood_hammer": 3,
    "iron_pickaxe": 41, "iron_broadsword": 43, "iron_helmet": 44,
    "iron_chainmail": 45, "iron_greaves": 46, "iron_anvil": 35,
    "workbench": 18, "furnace": 17, "torch": 28, "magic_mirror": 50,
    "recall_potion": 2350, "ice_mirror": 3199, "hook": 84,
    "web_slinging_hook": 1236, "potion_healing": 58, "potion_mana": 59,
    "gold_coin": 72, "silver_coin": 71, "copper_coin": 70,
    "platinum_coin": 74,
}

NPC_IDS: Dict[str, int] = {
    "slime": 1, "blue_slime": 1, "green_slime": 2, "red_slime": 3,
    "skeleton": 21, "zombie": 22, "demon_eye": 23, "eye_of_cthulhu": 4,
    "king_slime": 50, "eater_of_worlds": 13, "brain_of_cthulhu": 266,
    "queen_bee": 222, "skeletron": 35, "wall_of_flesh": 113,
    "goblin_army": 100, "boss": 4,
}

NAME_TO_ITEM: Dict[str, int] = {v: k for k, v in ITEM_IDS.items()}


def item_id(name: str, registry=None) -> int:
    iid = ITEM_IDS.get(name.lower(), -1)
    if iid >= 0:
        return iid
    if registry is not None:
        return registry.resolve(name)
    return -1


def npc_id(name: str) -> int:
    return NPC_IDS.get(name.lower(), -1)


def item_name(iid: int) -> str:
    return NAME_TO_ITEM.get(iid, f"item_{iid}")


def load_mod_items(path: str) -> Dict[str, Dict[str, int]]:
    import json
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
