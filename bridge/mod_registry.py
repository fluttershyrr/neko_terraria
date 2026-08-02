"""mod 物品注册缓存：枚举已加载 mod 物品，按 mod 分文件存于 data/mod_items/。

data/ 统一存放运行时数据（配置、缓存等），按分类建子文件夹。此缓存属游戏数据，
进游戏时对比当前 mod 列表与已有文件：新增写入、消失删除，保持目录整洁。
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Set


class ModItemRegistry:
    def __init__(self, base_dir: str) -> None:
        self.dir = Path(base_dir) / "data" / "mod_items"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.mods: Dict[str, Dict[str, int]] = {}
        self.uses: Dict[str, Dict[str, str]] = {}
        self.tags: Dict[str, Dict[str, List[str]]] = {}
        self.load_cached()

    def load_cached(self) -> None:
        if not self.dir.exists():
            return
        for f in self.dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                self.mods[data.get("mod", f.stem)] = {
                    i["name"]: i["id"] for i in data.get("items", [])
                }
                self.uses[data.get("mod", f.stem)] = {
                    i["name"]: i.get("use", "misc") for i in data.get("items", [])
                }
                self.tags[data.get("mod", f.stem)] = {
                    i["name"]: i.get("tags", ["misc"]) for i in data.get("items", [])
                }
            except Exception:
                pass

    def sync_from_enum(self, mods: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        # 增量同步：新增/更新写入，消失的 mod 删除对应文件，返回变更
        result: Dict[str, List[str]] = {"added": [], "updated": [], "removed": []}
        with self._lock:
            seen: Set[str] = set()
            for m in mods:
                name = m.get("mod", "Unknown")
                items = {i["name"]: i["id"] for i in m.get("items", [])}
                uses = {i["name"]: i.get("use", "misc") for i in m.get("items", [])}
                tags = {i["name"]: i.get("tags", ["misc"]) for i in m.get("items", [])}
                seen.add(name)
                if name not in self.mods:
                    result["added"].append(name)
                elif self.mods[name] != items:
                    result["updated"].append(name)
                self.mods[name] = items
                self.uses[name] = uses
                self.tags[name] = tags
                self._write_file(name, m.get("items", []))
            for old in list(self.mods.keys()):
                if old not in seen:
                    result["removed"].append(old)
                    self._remove_file(old)
                    del self.mods[old]
                    del self.uses[old]
                    del self.tags[old]
        return result

    def _write_file(self, mod: str, items: List[Dict[str, Any]]) -> None:
        path = self.dir / f"{mod}.json"
        try:
            path.write_text(
                json.dumps({"mod": mod, "items": items},
                           ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception:
            pass

    def _remove_file(self, mod: str) -> None:
        path = self.dir / f"{mod}.json"
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass

    def resolve(self, name: str) -> int:
        low = name.lower()
        for items in self.mods.values():
            if low in items:
                return items[low]
        return -1

    def use_of(self, name: str) -> str:
        low = name.lower()
        for uses in self.uses.values():
            if low in uses:
                return uses[low]
        return "misc"

    def find_by_use(self, use: str) -> List[int]:
        # 返回某用途的所有物品 id（如 "potion" 找所有药水）
        out: List[int] = []
        for mod, items in self.mods.items():
            u = self.uses.get(mod, {})
            for name, iid in items.items():
                if u.get(name, "misc") == use:
                    out.append(iid)
        return out

    def find_by_tag(self, tag: str) -> List[int]:
        # 按用途标签找物品 id（如 "heal" 找所有加血物品）
        out: List[int] = []
        for mod, items in self.mods.items():
            t = self.tags.get(mod, {})
            for name, iid in items.items():
                if tag in t.get(name, []):
                    out.append(iid)
        return out

    def describe(self, name: str) -> Dict[str, Any]:
        # 返回某物品的用途信息：id / use / tags
        low = name.lower()
        for mod, items in self.mods.items():
            if low in items:
                u = self.uses.get(mod, {})
                t = self.tags.get(mod, {})
                return {"id": items[low], "use": u.get(low, "misc"),
                        "tags": t.get(low, ["misc"])}
        return {"id": -1, "use": "misc", "tags": ["misc"]}

    def mod_list(self) -> List[Dict[str, Any]]:
        return [{"mod": k, "count": len(v)} for k, v in self.mods.items()]
