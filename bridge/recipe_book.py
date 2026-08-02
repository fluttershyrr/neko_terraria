"""配方书：把 mod 的真实配方收进来，供合成推演使用。

为什么需要它：
    mod 物品（灾厄/瑟银/各种整合包）的配方只有游戏里才知道，
    写死在 Python 里的常识表根本覆盖不到。没有真实配方，
    猫娘对着一件 mod 装备只会说"我搞不到"，推演就废了。

它负责三件事：
    1. 向 mod 要全量配方（含材料、合成站、来源 mod），落盘缓存
    2. 名字对得上：mod 回的是英文名，主人说的是中文，要能互相认
    3. 反查：某个材料能做出什么、某件东西缺哪一步

缓存放在 data/recipes/ 下，与 mod_items 同级，换整合包会自动重建。
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 常见原版物品中英对照，帮主人的中文对上 mod 回的英文名。
# mod 物品的中文名通常没有官方对照，靠原名/模糊匹配兜底。
CN_EN: Dict[str, str] = {
    "铁矿": "Iron Ore", "铜矿": "Copper Ore", "银矿": "Silver Ore",
    "金矿": "Gold Ore", "锡矿": "Tin Ore", "铅矿": "Lead Ore",
    "钨矿": "Tungsten Ore", "铂金矿": "Platinum Ore",
    "铁锭": "Iron Bar", "铜锭": "Copper Bar", "银锭": "Silver Bar",
    "金锭": "Gold Bar", "锡锭": "Tin Bar", "铅锭": "Lead Bar",
    "钨锭": "Tungsten Bar", "铂金锭": "Platinum Bar",
    "铁镐": "Iron Pickaxe", "铜镐": "Copper Pickaxe",
    "银镐": "Silver Pickaxe", "金镐": "Gold Pickaxe",
    "木材": "Wood", "石块": "Stone Block", "土块": "Dirt Block",
    "火把": "Torch", "工作台": "Work Bench", "熔炉": "Furnace",
    "铁砧": "Iron Anvil", "抓钩": "Grappling Hook", "绳": "Rope",
    "恶魔石": "Demonite Ore", "陨石": "Meteorite",
}
EN_CN: Dict[str, str] = {v: k for k, v in CN_EN.items()}

# 合成站中文名
STATION_CN: Dict[str, str] = {
    "Work Bench": "工作台", "Furnace": "熔炉", "Iron Anvil": "铁砧",
    "Mythril Anvil": "秘银砧", "Adamantite Forge": "精金熔炉",
    "Hellforge": "地狱熔炉", "Bottle": "瓶子", "Table": "桌子",
    "Cooking Pot": "锅", "Loom": "织布机", "Sawmill": "锯木机",
    "Tinkerer's Workshop": "工匠作坊", "Alchemy Table": "炼药桌",
}

CACHE_TTL = 3600.0     # 配方一小时内不重复拉取（换 mod 会手动刷新）


class Recipe:
    """一条配方。"""

    __slots__ = ("name", "item_id", "amount", "mod", "materials",
                 "stations", "available")

    def __init__(self, data: Dict[str, Any]) -> None:
        self.name: str = data.get("name", "")
        self.item_id: int = int(data.get("item_id", -1) or -1)
        self.amount: int = int(data.get("amount", 1) or 1)
        self.mod: str = data.get("mod", "Terraria")
        self.available: bool = bool(data.get("available", True))
        self.materials: List[Tuple[str, int]] = [
            (m.get("name", ""), int(m.get("stack", 1) or 1))
            for m in data.get("materials", []) or []
            if m.get("name")
        ]
        self.stations: List[str] = [
            st.get("name", "") for st in data.get("stations", []) or []
            if st.get("name")
        ]

    def is_modded(self) -> bool:
        return self.mod not in ("", "Terraria")

    def say(self) -> str:
        mats = "、".join(f"{cn_name(n)}x{s}" for n, s in self.materials)
        head = f"{cn_name(self.name)} = {mats}"
        if self.stations:
            head += "（要" + "、".join(station_cn(s) for s in self.stations) + "）"
        return head

    def snapshot(self) -> Dict[str, Any]:
        return {"name": self.name, "cn": cn_name(self.name),
                "mod": self.mod, "amount": self.amount,
                "materials": [{"name": n, "stack": s} for n, s in self.materials],
                "stations": self.stations, "available": self.available}


def cn_name(en: str) -> str:
    """英文名转中文，转不了就原样返回（mod 物品多半没中文名）。"""
    return EN_CN.get(en, en)


def station_cn(en: str) -> str:
    return STATION_CN.get(en, en)


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace("_", "")


class RecipeBook:
    """配方索引：按产物查配方、按材料反查用途。"""

    def __init__(self, agent, base_dir: str = "") -> None:
        self.agent = agent
        self._by_name: Dict[str, List[Recipe]] = {}   # 规范化名 -> 配方们
        self._by_material: Dict[str, List[Recipe]] = {}
        self._loaded_at: float = 0.0
        self._loading = False
        # 与 mod_items 缓存同级：<插件目录>/data/recipes/
        base = (Path(base_dir) if base_dir
                else Path(__file__).resolve().parent.parent)
        self.cache_file = base / "data" / "recipes" / "recipes.json"

    # ---------- 索引 ----------
    def _index(self, recipes: List[Recipe]) -> None:
        self._by_name.clear()
        self._by_material.clear()
        for r in recipes:
            if not r.name:
                continue
            self._by_name.setdefault(_norm(r.name), []).append(r)
            # 中文名也建索引，主人说中文时能命中
            cn = cn_name(r.name)
            if cn != r.name:
                self._by_name.setdefault(_norm(cn), []).append(r)
            for mname, _s in r.materials:
                self._by_material.setdefault(_norm(mname), []).append(r)

    def count(self) -> int:
        return sum(len(v) for v in self._by_name.values())

    def loaded(self) -> bool:
        return bool(self._by_name)

    # ---------- 加载 ----------
    async def refresh(self, force: bool = False) -> int:
        """向 mod 要全量配方；失败则退回磁盘缓存。返回配方条数。"""
        if self._loading:
            return self.count()
        if not force and self.loaded() and (
                time.time() - self._loaded_at) < CACHE_TTL:
            return self.count()

        self._loading = True
        try:
            raw: List[Dict[str, Any]] = []
            try:
                raw = await self.agent.mod.get_recipes("all")
            except Exception:
                raw = []

            if raw:
                recipes = [Recipe(d) for d in raw]
                # 只留有材料的，没材料的推演不了
                recipes = [r for r in recipes if r.materials]
                self._index(recipes)
                self._loaded_at = time.time()
                self._save(raw)
                modded = sum(1 for r in recipes if r.is_modded())
                self._log(f"配方书就绪：{len(recipes)} 条（其中 mod 配方 {modded} 条）")
                return len(recipes)

            # mod 没给：用磁盘缓存兜底
            cached = self._load()
            if cached:
                recipes = [Recipe(d) for d in cached]
                recipes = [r for r in recipes if r.materials]
                self._index(recipes)
                self._loaded_at = time.time()
                self._log(f"配方书用了本地缓存：{len(recipes)} 条")
                return len(recipes)
            return 0
        finally:
            self._loading = False

    def _save(self, raw: List[Dict[str, Any]]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(
                json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _load(self) -> List[Dict[str, Any]]:
        try:
            if self.cache_file.exists():
                return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _log(self, msg: str) -> None:
        try:
            self.agent.log(msg, "item")
        except Exception:
            pass

    # ---------- 查询 ----------
    def find(self, item: str) -> Optional[Recipe]:
        """按名字找配方，优先能立刻做的那条。中英文都能查。"""
        cands = self._lookup(item)
        if not cands:
            return None
        for r in cands:
            if r.available:
                return r
        return cands[0]

    def find_all(self, item: str) -> List[Recipe]:
        return list(self._lookup(item))

    def _lookup(self, item: str) -> List[Recipe]:
        key = _norm(item)
        if key in self._by_name:
            return self._by_name[key]
        # 中文 -> 英文再试
        en = CN_EN.get((item or "").strip())
        if en and _norm(en) in self._by_name:
            return self._by_name[_norm(en)]
        # 模糊：包含匹配（mod 物品名常带前缀）
        hits: List[Recipe] = []
        for k, v in self._by_name.items():
            if key and (key in k or k in key):
                hits.extend(v)
        return hits

    def materials_of(self, item: str) -> List[Tuple[str, int]]:
        r = self.find(item)
        return list(r.materials) if r else []

    def stations_of(self, item: str) -> List[str]:
        r = self.find(item)
        return list(r.stations) if r else []

    def used_in(self, material: str) -> List[Recipe]:
        """这个材料能做出什么，供"这东西有什么用"回答。"""
        key = _norm(material)
        if key in self._by_material:
            return self._by_material[key]
        en = CN_EN.get((material or "").strip())
        if en:
            return self._by_material.get(_norm(en), [])
        return []

    def is_craftable(self, item: str) -> bool:
        return self.find(item) is not None
