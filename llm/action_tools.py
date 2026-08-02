"""猫娘动作工具：warp / summon / mine / craft / give / equip。"""

from typing import Any, Dict

from plugin.sdk.plugin import Ok, llm_tool


class ActionToolsMixin:
    _agent: Any
    @llm_tool(name="terraria_warp",
              description="传送猫娘到坐标。",
              parameters={"type": "object",
                          "properties": {"x": {"type": "integer"},
                                         "y": {"type": "integer"}},
                          "required": ["x", "y"]})
    async def llm_warp(self, x: int, y: int, **_) -> Dict[str, Any]:
        self._agent.bot.warp(x, y)
        return Ok({"output": f"已传送到 ({x},{y})"})

    @llm_tool(name="terraria_mine",
              description="让猫娘挖指定矿石若干。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"},
                                         "amount": {"type": "integer"}},
                          "required": ["item"]})
    async def llm_mine(self, item: str, amount: int = 10, **_) -> Dict[str, Any]:
        _, mined = await self._agent.mining.mine_target(item, amount)
        return Ok({"output": f"挖了 {mined} 个 {item}"})

    @llm_tool(name="terraria_craft",
              description="让猫娘合成物品。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"},
                                         "amount": {"type": "integer"}},
                          "required": ["item"]})
    async def llm_craft(self, item: str, amount: int = 1, **_) -> Dict[str, Any]:
        n = await self._agent.mod.craft(
            item_id=self._agent.resolve_item(item), amount=amount)
        return Ok({"output": f"合成 {n} 个 {item}"})

    @llm_tool(name="terraria_give",
              description="猫娘把物品给玩家。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"},
                                         "stack": {"type": "integer"}},
                          "required": ["item"]})
    async def llm_give(self, item: str, stack: int = 1, **_) -> Dict[str, Any]:
        ok = await self._agent.equip.give_to_player(
            self._agent.resolve_item(item), stack)
        return Ok({"output": "已给玩家" if ok else "给物品失败"})

    @llm_tool(name="terraria_give_to_me",
              description="猫娘把物品丢到脚下让你拾取（转交）。问她要几个时会用。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"},
                                         "stack": {"type": "integer"}},
                          "required": ["item"]})
    async def llm_give_to_me(self, item: str, stack: int = 1, **_) -> Dict[str, Any]:
        ok = await self._agent.hand_to_player(item, stack)
        return Ok({"output": f"已丢下 {stack} 个 {item}，快捡~" if ok
                   else "我背包里没有这个哦"})

    @llm_tool(name="terraria_use_item",
              description="让猫娘使用某物品（喝药水/手持工具等）。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"}},
                          "required": ["item"]})
    async def llm_use_item(self, item: str, **_) -> Dict[str, Any]:
        ok = await self._agent.use_item_by_name(item)
        return Ok({"output": f"用了 {item}" if ok else "用不了这个"})

    @llm_tool(name="terraria_list_inventory",
              description="列出猫娘当前背包(含手持/装备)里的物品与数量，用于回答玩家'你有什么'。",
              parameters={"type": "object",
                          "properties": {},
                          "required": []})
    async def llm_list_inventory(self, **_) -> Dict[str, Any]:
        inv = await self._agent.get_inventory()
        items = []
        for kind in ("hotbar", "equipped", "inventory"):
            for it in inv.get(kind, []):
                items.append(f"{it.get('name', '?')}x{it.get('stack', 0)}")
        return Ok({"output": "我的物品：" + "、".join(items) if items
                   else "我现在是空的~"})

    @llm_tool(name="terraria_where_is",
              description="查询某物品在哪里：猫娘背包/装备/手持，还是某个箱子里。回答'去哪拿'。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"}},
                          "required": ["item"]})
    async def llm_where_is(self, item: str, **_) -> Dict[str, Any]:
        loc = self._agent.locate_item(item)
        if not loc.get("found"):
            return Ok({"output": f"我哪里都没有 {item} 哦"})
        where = loc["where"]
        if where == "chest":
            c = loc["chest"]
            return Ok({"output": f"{item} 在箱子({c['x']},{c['y']})里，共 {loc['stack']} 个"})
        name_map = {"inventory": "背包", "hotbar": "手持栏", "equipped": "装备栏"}
        return Ok({"output": f"{item} 在我{name_map.get(where, where)}里，共 {loc['stack']} 个"})

    @llm_tool(name="terraria_find_items",
              description="按用途查猫娘认识的 mod 物品，如 heal(加血)/mana(回蓝)/buff/summon/armor/tool。用于'你有什么加血的'。",
              parameters={"type": "object",
                          "properties": {"tag": {"type": "string",
                                            "description": "用途标签: heal/mana/buff/summon/armor/tool/pickaxe/axe/material"}},
                          "required": ["tag"]})
    async def llm_find_items(self, tag: str, **_) -> Dict[str, Any]:
        out_names = []
        for mod, items in self._agent.registry.mods.items():
            t = self._agent.registry.tags.get(mod, {})
            for name, iid in items.items():
                if tag in t.get(name, []):
                    out_names.append(name)
        if not out_names:
            return Ok({"output": f"我不认识任何用于「{tag}」的物品哦"})
        return Ok({"output": f"用于「{tag}」的物品有：" + "、".join(out_names[:15])})

    @llm_tool(name="terraria_store",
              description="猫娘把某物品放进箱子。不指定箱子时自动选最近的。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"},
                                         "stack": {"type": "integer"},
                                         "chest_x": {"type": "integer"},
                                         "chest_y": {"type": "integer"}},
                          "required": ["item"]})
    async def llm_store(self, item: str, stack: int = 1,
                        chest_x: int = -1, chest_y: int = -1, **_) -> Dict[str, Any]:
        if chest_x >= 0 and chest_y >= 0:
            chest = {"x": chest_x, "y": chest_y}
        else:
            chest = await self._agent.nearest_chest_with(item)
            if chest is None:
                chests = await self._agent.mod.enum_chests()
                chest = chests[0] if chests else None
        if not chest:
            return Ok({"output": "附近没有箱子，先放不进去哦"})
        ok = await self._agent.store_to_chest(item, chest, stack)
        return Ok({"output": f"已放进箱子({chest['x']},{chest['y']})" if ok
                   else "放不进去（可能不在箱子旁或背包没有）"})

    @llm_tool(name="terraria_take",
              description="猫娘从箱子取出某物品。不指定箱子时自动选最近的含该物的箱子。",
              parameters={"type": "object",
                          "properties": {"item": {"type": "string"},
                                         "stack": {"type": "integer"},
                                         "chest_x": {"type": "integer"},
                                         "chest_y": {"type": "integer"}},
                          "required": ["item"]})
    async def llm_take(self, item: str, stack: int = 1,
                       chest_x: int = -1, chest_y: int = -1, **_) -> Dict[str, Any]:
        if chest_x >= 0 and chest_y >= 0:
            chest = {"x": chest_x, "y": chest_y}
        else:
            chest = await self._agent.nearest_chest_with(item)
        if not chest:
            return Ok({"output": "附近没有含这个的箱子哦"})
        ok = await self._agent.take_from_chest(item, chest, stack)
        return Ok({"output": f"已从箱子({chest['x']},{chest['y']})取出 {item}" if ok
                   else "取不出来"})

    @llm_tool(name="terraria_task",
              description="【执行多步游戏任务的主入口】下达有序的连续任务（如坑底挖矿后回地面拿东西再回来）。"
                          "当用户给出结构化/多步骤游戏操作指令时必须调用本工具，不要调用 terraria_chat。"
                          "steps 为有序步骤列表。",
              parameters={"type": "object",
                          "properties": {
                              "steps": {"type": "array",
                                        "description": "有序步骤。action 可为 mine/gather(挖矿,带item/amount)、"
                                                       "fetch(去箱子取,带item)、climb(爬到高处,带x/y)、"
                                                       "goto(走到坐标,带x/y)。任一步失败会中止并汇报，不自动重试",
                                        "items": {"type": "object"}},
                              "goal": {"type": "string", "description": "整体任务目标一句话"}},
                          "required": ["steps"]})
    async def llm_task(self, steps: list, goal: str = "", **_) -> Dict[str, Any]:
        # 三阶段：想(评估能否做) → 处理(拆步骤) → 做(执行器串行执行)
        from ..bridge.executor import SRC_OWNER
        res = await self._agent.run_complex_task(steps, goal, source=SRC_OWNER)
        return Ok({"output": res.get("output", "")})

    @llm_tool(name="terraria_assess",
              description="只想不做：评估一个多步任务能不能完成、缺什么、打算怎么分步。"
                          "主人问'你能不能做…'或下达复杂任务前先用它。",
              parameters={"type": "object",
                          "properties": {
                              "steps": {"type": "array",
                                        "description": "同 terraria_task 的步骤格式",
                                        "items": {"type": "object"}},
                              "goal": {"type": "string"}},
                          "required": ["steps"]})
    async def llm_assess(self, steps: list, goal: str = "", **_) -> Dict[str, Any]:
        res = await self._agent.run_complex_task(steps, goal, dry_run=True)
        out = res.get("output", "")
        fixes = res.get("fixes") or []
        if fixes:
            out += "（我会先自己解决：" + "、".join(fixes) + "）"
        if res.get("need"):
            out += f"（{res['need']}）"
        return Ok({"output": out})

    @llm_tool(name="terraria_recipe",
              description="查某样东西怎么做（支持 mod 物品）：要什么材料、在哪个合成站做、"
                          "现在做不做得了。主人问'XX怎么合成''做XX要什么'时用。",
              parameters={"type": "object",
                          "properties": {
                              "item": {"type": "string",
                                       "description": "物品名，中英文都行"}},
                          "required": ["item"]})
    async def llm_recipe(self, item: str, **_) -> Dict[str, Any]:
        book = self._agent.recipe_book
        await book.refresh()
        r = book.find(item)
        if r is None:
            uses = book.used_in(item)
            if uses:
                names = "、".join(x.name for x in uses[:5])
                return Ok({"output": f"{item}做不出来，不过它能用来做：{names}"})
            return Ok({"output": f"我不知道{item}怎么做，可能配方还没同步~"})
        src = f"（{r.mod} 的东西）" if r.is_modded() else ""
        tail = "，现在就能做" if r.available else "，不过现在还差点条件"
        return Ok({"output": f"{r.say()}{src}{tail}"})

    @llm_tool(name="terraria_why",
              description="解释猫娘上一次是怎么想的：为什么这么分步、卡在哪、想到了什么办法。"
                          "主人问'你怎么想的''为什么这么做'时用。",
              parameters={"type": "object", "properties": {}, "required": []})
    async def llm_why(self, **_) -> Dict[str, Any]:
        a = self._agent.brain.last_assessment()
        if a is None:
            return Ok({"output": "我还没想过什么复杂任务呢~"})
        body = a.explain() or a.say()
        return Ok({"output": f"我是这么想的：\n{body}"})

    @llm_tool(name="terraria_task_status",
              description="查询猫娘现在在做什么任务、到第几步了，包括正在持续做的长期任务"
                          "（跟随/一直挖矿）。主人问'你在干嘛'时用。",
              parameters={"type": "object", "properties": {}, "required": []})
    async def llm_task_status(self, **_) -> Dict[str, Any]:
        cur = self._agent.executor.current()
        longs = self._agent.longterm.active()
        parts = []
        if cur:
            src = "主人交代的" if cur["source"] == "owner" else "我自己找的活"
            parts.append(f"正在做「{cur['name']}」（{src}），进度 {cur['step']}，"
                         f"当前：{cur['note']}，已经 {cur['elapsed']} 秒了")
        for t in longs:
            parts.append(t["say"])
        if not parts:
            last = self._agent.executor.last_result()
            if last:
                return Ok({"output": f"现在空着呢~ 上一件事：{last.get('output', '')}"})
            return Ok({"output": "现在空着呢，随时可以派活给我~"})
        return Ok({"output": "；".join(parts)})

    @llm_tool(name="terraria_keep_doing",
              description="下达长期任务：一直做下去直到主人喊停。用于'跟着我'、'一直挖铁'、"
                          "'守在这'这类没有明确数量/终点的要求。若主人说了具体数量，"
                          "请改用 terraria_task。",
              parameters={"type": "object",
                          "properties": {
                              "kind": {"type": "string",
                                       "description": "follow(跟着主人)/mine(一直挖某种矿)/guard(守在原地)"},
                              "target": {"type": "string",
                                         "description": "kind=mine 时的矿物名，如 铁矿"},
                              "amount": {"type": "integer",
                                         "description": "可选上限，0 或不填表示一直做"}},
                          "required": ["kind"]})
    async def llm_keep_doing(self, kind: str, target: str = "",
                             amount: int = 0, **_) -> Dict[str, Any]:
        res = await self._agent.start_longterm(kind, target=target, amount=amount,
                                               reason="主人的长期要求")
        return Ok({"output": res.get("output", "")})

    @llm_tool(name="terraria_stop_doing",
              description="停止长期任务。主人说'别跟了'、'不用挖了'、'停下'时用。"
                          "不填 kind 表示把所有长期任务都停掉。",
              parameters={"type": "object",
                          "properties": {
                              "kind": {"type": "string",
                                       "description": "follow/mine/guard，留空表示全停"}},
                          "required": []})
    async def llm_stop_doing(self, kind: str = "", **_) -> Dict[str, Any]:
        res = await self._agent.stop_longterm(kind)
        return Ok({"output": res.get("output", "")})

    @llm_tool(name="terraria_climb",
              description="让猫娘爬到指定高处（深坑回地面等）。会自动找中途平台分几段上去，"
                          "上不去会告诉你卡在第几段。",
              parameters={"type": "object",
                          "properties": {"x": {"type": "integer"},
                                         "y": {"type": "integer"}},
                          "required": ["x", "y"]})
    async def llm_climb(self, x: int, y: int, **_) -> Dict[str, Any]:
        ok = await self._agent.climb_to(x, y)
        return Ok({"output": f"已经爬到 ({x},{y}) 啦~" if ok else "这次没爬上去，我停在原地了"})

    @llm_tool(name="terraria_plan_climb",
              description="只评估不执行：看看爬到某个高处要分几段、用钩锁还是垫土、能不能上去。"
                          "主人问'你上得来吗'时用。",
              parameters={"type": "object",
                          "properties": {"x": {"type": "integer"},
                                         "y": {"type": "integer"}},
                          "required": ["x", "y"]})
    async def llm_plan_climb(self, x: int, y: int, **_) -> Dict[str, Any]:
        plan = await self._agent.planner.plan_climb(x, y)
        head = "能上去" if plan.feasible else "上不去"
        return Ok({"output": f"{head}：{plan.describe()}"})

    @llm_tool(name="terraria_capabilities",
              description="报告猫娘当前能力：有无钩锁/土块/镐子/绳梯，供主人判断能否完成指令。",
              parameters={"type": "object", "properties": {}, "required": []})
    async def llm_capabilities(self, **_) -> Dict[str, Any]:
        caps = await self._agent.capability.refresh()
        if not caps:
            return Ok({"output": "我还不清楚自己能力，稍等"})
        parts = []
        parts.append("钩锁：" + ("有" if caps.get("has_hook") else "无"))
        parts.append(f"土块：{caps.get('dirt_count', 0)}")
        parts.append("镐子：" + ("有" if caps.get("has_pickaxe") else "无"))
        parts.append(f"绳/梯：{caps.get('rope_count', 0)}")
        return Ok({"output": "我当前能力 → " + "、".join(parts)})
