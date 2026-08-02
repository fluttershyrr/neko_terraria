"""TerrariaAgent：双轨调度，指令抢占与自主行为并行。"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from .combat import CombatEngine
from .connection import Connection
from .equipment import EquipmentManager
from .mining import MiningEngine
from .mod_link import ModLink
from .mod_registry import ModItemRegistry
from .capability import Capability
from .planner import Planner
from .executor import TaskExecutor, SRC_OWNER, SRC_AUTO
from .task_brain import TaskBrain
from .longterm import LongTermManager
from .standing_jobs import StandingJobs
from .coordinator import TaskCoordinator
from .inventory_ops import InventoryOps
from .recipe_book import RecipeBook
from .raw_bot import RawBot
from .task_chain import Goal, TaskChain


class TerrariaAgent:
    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.cfg = cfg
        self.conn = Connection(
            cfg["server_host"], cfg["server_port"],
            cfg["mod_host"], cfg["mod_port"])
        self.bot = RawBot(self.conn)
        self.mod = ModLink(self.conn)
        self.combat = CombatEngine(self.mod, self.bot, self)
        self.mining = MiningEngine(self.mod, self.bot, self)
        self.equip = EquipmentManager(self.mod)
        self.tasks = TaskChain(self.mining, self.mod, self.equip, self)
        self.registry = ModItemRegistry(Path(__file__).resolve().parent.parent)
        self.capability = Capability(self)
        self.planner = Planner(self)
        self.executor = TaskExecutor(self)
        # 配方书要先于大脑建好：大脑推演合成时直接用它（含 mod 配方）
        self.recipe_book = RecipeBook(self)
        self.brain = TaskBrain(self)
        # 后台常驻轨：跟随/一直挖矿这类没有终点的长期任务
        self.longterm = LongTermManager(self)
        self.jobs = StandingJobs(self)
        self.coordinator = TaskCoordinator(self)
        self.items = InventoryOps(self)
        self._state: Dict[str, Any] = {}
        self._inv_full: Dict[str, Any] = {"hotbar": [], "equipped": [], "inventory": []}
        self._chests: List[Dict[str, Any]] = []
        self._log: List[Dict[str, Any]] = []
        self._running = False

    async def start(self) -> bool:
        ok = await self.bot.login(
            self.cfg["bot_name"], self.cfg.get("bot_password", ""))
        if not ok:
            return False
        self._running = True
        asyncio.create_task(self.tasks.run_loop())
        asyncio.create_task(self._state_loop())
        asyncio.create_task(self._auto_register())
        return True

    async def refresh_state(self) -> Dict[str, Any]:
        # 立即拉一次状态（不等 _state_loop 周期），供分段执行后重新评估
        st = await self.mod.get_state(self.bot.player_name)
        if st:
            self._state = st
            self.bot.sync_position(st.get("x", 0), st.get("y", 0))
        return self._state

    def log(self, msg: str, kind: str = "info") -> None:
        # 内存环形日志，供前端静默刷新展示
        from time import time
        self._log.append({"t": time(), "msg": msg, "kind": kind})
        if len(self._log) > 100:
            self._log = self._log[-100:]

    async def _auto_register(self) -> None:
        # 进游戏时增量同步 mod 物品：新写入、消失删除，保持目录整洁
        try:
            mods = await self.mod.enum_items()
            diff = self.registry.sync_from_enum(mods)
            if diff["added"]:
                self.bot.send_msg(f"认识了新 mod：{', '.join(diff['added'])}")
            if diff["removed"]:
                self.bot.send_msg(f"这些 mod 不见了：{', '.join(diff['removed'])}")
        except Exception:
            pass
        # mod 换了配方也会变，强制重拉一次配方书
        try:
            n = await self.recipe_book.refresh(force=True)
            if n:
                self.log(f"学会了 {n} 条配方", "item")
        except Exception:
            pass

    async def stop(self) -> None:
        self._running = False
        self.conn.close()

    async def _state_loop(self) -> None:
        while self._running:
            try:
                self._state = await self.mod.get_state(self.bot.player_name)
                if self._state:
                    self.bot.sync_position(
                        self._state.get("x", 0), self._state.get("y", 0))
                else:
                    # 查询失败，记录日志
                    self.log("Mod 状态查询失败: 未找到玩家", "warn")
            except Exception as e:
                self._state = {}
                self.log(f"Mod 状态查询异常: {e}", "error")
            # 顺带缓存背包三大类与箱子，供 UI 同步读取
            try:
                self._inv_full = await self.mod.get_inventory()
            except Exception:
                pass
            if len(self._chests) == 0:
                try:
                    self._chests = await self.mod.enum_chests()
                except Exception:
                    pass
            await asyncio.sleep(self.cfg.get("state_tick_interval_seconds", 1.0))

    async def submit_goal(self, goal: Goal) -> None:
        await self.tasks.submit(goal)

    async def run_complex_task(self, steps: List[Dict[str, Any]], goal_text: str = "",
                               source: str = SRC_OWNER,
                               dry_run: bool = False) -> Dict[str, Any]:
        """收到任务 → 想(评估) → 处理(规划) → 做(执行)。主人的任务可打断自主行为。"""
        # 想：推演整串步骤，缺东西就自己想补救办法
        assess = await self.brain.think(steps)
        self.log(f"想：{assess.say()}", "task")
        for t in assess.thoughts:
            self.log(f"  思考：{t}", "task")
        if not assess.doable:
            await self.send_chat(f"主人，{assess.say()}~")
            return {"ok": False, "status": "not_doable", "phase": "think",
                    "output": assess.say(), "why": assess.explain(),
                    "need": assess.need_from_owner}
        # 想到了补救办法就先说一声，让主人知道我在动脑子
        if assess.fixes:
            await self.send_chat(f"主人，{assess.say()}~")

        # 处理：用补全前置后的步骤编译，顺手合并冗余
        plan = self.brain.plan(steps, goal_text, assess)
        self.log(f"处理：{plan.say()}", "task")
        if not plan.goals:
            return {"ok": False, "status": "empty_plan", "phase": "plan",
                    "output": "没解析出可执行步骤"}
        if dry_run:
            return {"ok": True, "status": "planned", "phase": "plan",
                    "output": f"我会这样做：{plan.say()}",
                    "why": assess.explain(), "fixes": assess.fixes,
                    "skipped": plan.skipped}

        # 做：交给执行器（单槽位 + 可被主人打断）
        async def _work(info):
            info.phase = "act"
            for i, g in enumerate(plan.goals):
                if self.executor.should_stop():
                    return {"ok": False, "status": "cancelled",
                            "output": f"做到第{i+1}步被叫停了"}
                info.step_index = i + 1
                info.note = plan.outline[i] if i < len(plan.outline) else g.goal_type
                self.log(f"做：第{i+1}/{len(plan.goals)}步 {info.note}", "task")
                ok = await self.tasks.run_one(g)
                if not ok:
                    msg = g.report_fail or f"第{i+1}步没做成"
                    await self.send_chat(f"主人，{msg}，我停下来等你~")
                    return {"ok": False, "status": "step_failed", "phase": "act",
                            "output": f"在第{i+1}步「{info.note}」停下：{msg}"}
            return {"ok": True, "status": "ok", "phase": "act",
                    "output": f"做完啦：{plan.say()}"}

        return await self.executor.run(goal_text or "多步任务", _work,
                                       source=source, steps=plan.outline)

    async def command(self, text: str, source: str = SRC_OWNER) -> Dict[str, Any]:
        """自然语言统一入口：自动判断长期任务/有限任务/喊停并派发。"""
        return await self.coordinator.handle(text, source)

    async def start_longterm(self, kind: str, target: str = "",
                             amount: int = 0, reason: str = "") -> Dict[str, Any]:
        """直接起一个长期任务（跟随/挖矿/守点）。"""
        return await self.jobs.start(kind, target=target, amount=amount,
                                     reason=reason)

    async def stop_longterm(self, kind: str = "",
                            why: str = "主人喊停") -> Dict[str, Any]:
        """停某个或全部长期任务。"""
        if kind:
            ok = await self.longterm.stop(kind, why)
            return {"ok": ok, "output": "停下了~" if ok else "我没在做这个呀~"}
        names = await self.longterm.stop_all(why)
        return {"ok": bool(names),
                "output": ("、".join(names) + " 都停下了~") if names else "我现在闲着呢~"}

    def task_status(self) -> Dict[str, Any]:
        """我在干嘛：前台 + 后台一起报。"""
        return self.coordinator.status()

    async def interrupt_current(self, why: str = "主人有新指令") -> bool:
        # 主人随时可打断：停掉正在执行的前台任务（长期任务不受影响，继续跟着）
        return await self.executor.cancel_current(why)

    async def stop_everything(self, why: str = "主人喊停") -> Dict[str, Any]:
        """全停：前台任务 + 所有长期任务。"""
        fg = await self.executor.cancel_current(why)
        names = await self.longterm.stop_all(why)
        return {"ok": True, "foreground_cancelled": fg, "longterm_stopped": names}

    async def send_chat(self, text: str) -> None:
        self.bot.send_msg(text)

    def get_state(self) -> Dict[str, Any]:
        return self._state

    @property
    def current_goal(self) -> str:
        g = getattr(self.tasks, "_current", None)
        return g.goal_type if g else ""

    def resolve_item(self, name: str) -> int:
        from .item_npc_dict import item_id
        return item_id(name, self.registry)

    async def follow_player(self, player_pos: tuple) -> None:
        # 自动寻路走到玩家身边（能绕过障碍）
        px, py = player_pos
        await self.navigate_to(px, py, timeout=8)

    async def heal_self(self) -> bool:
        # 用注册表中标记为 heal（加血）的物品自愈
        heals = self.registry.find_by_tag("heal")
        for pid in heals:
            ok = await self.mod.give_item(pid, 1)
            if ok:
                self.log("喝了加血物品", "item")
                return True
        return False

    async def use_item_on_self(self, name: str) -> bool:
        iid = self.resolve_item(name)
        if iid < 0:
            return False
        return await self.mod.give_item(iid, 1)

    async def navigate_to(self, x: int, y: int, timeout: int = 25) -> bool:
        # 自动寻路走到坐标（mod 侧：坑洞规避/按住跳跃/搭土/钩锁）
        # 预判能力：目标在上方且自己无上攀手段时，及时汇报而非硬冲
        await self.capability.refresh()
        st = self._state
        cur_y = st.get("tile_y", 0)
        height_diff = cur_y - y  # 向上为正
        if height_diff > 3 and not self.capability.can_climb(height_diff):
            # 单次上不去：交给分段规划器找中途平台（如钩锁分两次上）
            self.log(f"落差{height_diff}格单次上不去，尝试分段爬升", "nav")
            return await self.climb_to(x, y)
        cur_x = float(st.get("x", x * 16))
        cur_y_px = float(st.get("y", y * 16))
        distance = abs(x * 16 - cur_x) + abs(y * 16 - cur_y_px)
        duration = min(float(timeout), max(0.25, distance / 160.0))
        ok = await self.bot.move_to(x * 16, y * 16, duration)
        self.log(f"走到 ({x},{y}) " + ("成功" if ok else "失败/超时"), "nav")
        if not ok:
            await self.send_chat(f"主人，我过不去 ({x},{y})，卡住了，等你想想办法~")
        return ok

    async def climb_to(self, x: int, y: int, _round: int = 1) -> bool:
        # 复杂垂直移动（深坑回地面）：先规划分段，再逐段执行，每段后重新评估
        if _round > 5:
            self.log("爬升重规划超过5轮，放弃", "warn")
            await self.send_chat("主人，我试了好几次都上不去，你来帮帮我吧~")
            return False
        start_y = self._state.get("tile_y", 0)
        plan = await self.planner.plan_climb(x, y)
        if not plan.legs:
            self.log("爬升规划失败：" + plan.blocked_reason, "warn")
            await self.send_chat(f"主人，{plan.blocked_reason}，我上不去，等你命令~")
            return False
        self.log(f"爬升计划（{len(plan.legs)}段）：{plan.describe()}", "nav")
        if not plan.feasible:
            await self.send_chat(
                f"主人，我先爬{len(plan.legs)}段试试，不过{plan.blocked_reason}，可能到不了顶~")

        for i, leg in enumerate(plan.legs):
            if self.executor.should_stop():
                self.log("爬升被打断", "warn")
                return False
            self.log(f"第{i+1}/{len(plan.legs)}段：{leg.method} → ({leg.tx},{leg.ty})", "nav")
            ok = await self.bot.move_to(
                leg.tx * 16, leg.ty * 16, duration=1.0)
            if not ok:
                await self.send_chat(
                    f"主人，我卡在第{i+1}段了（{leg.method}到 {leg.tx},{leg.ty}），上不去啦~")
                self.log(f"第{i+1}段失败，中止爬升", "warn")
                return False
            # 每段后重新评估：资源已消耗、地形可能变化，剩余路径重新规划
            await self.capability.refresh()

        if plan.feasible:
            self.log("爬升完成", "nav")
            return True
        # 只到中途平台：重新规划剩余路程（如第二次钩锁）；无高度进展则停止避免死循环
        await self.refresh_state()
        now_y = self._state.get("tile_y", 0)
        if start_y - now_y < 1:
            self.log("本轮没有上升，停止重规划", "warn")
            await self.send_chat("主人，我卡在这上不去了，等你想想办法~")
            return False
        return await self.climb_to(x, y, _round + 1)

    # --- 物品/箱子：实现在 InventoryOps，这里保留原有调用签名 ---
    async def get_inventory(self) -> Dict[str, Any]:
        return await self.items.get_inventory()

    def get_inventory_sync(self) -> Dict[str, Any]:
        # UI context 同步读缓存（由 _state_loop 定期刷新）
        return self._inv_full

    def locate_item(self, name: str) -> Dict[str, Any]:
        return self.items.locate_item(name)

    def count_item(self, name: str) -> int:
        return self.items.count_item(name)

    async def nearest_chest_with(self, name: str) -> Optional[Dict[str, Any]]:
        return await self.items.nearest_chest_with(name)

    async def store_to_chest(self, name: str, chest: Dict[str, Any],
                            stack: int = 1) -> bool:
        return await self.items.store_to_chest(name, chest, stack)

    async def take_from_chest(self, name: str, chest: Dict[str, Any],
                             stack: int = 1) -> bool:
        return await self.items.take_from_chest(name, chest, stack)

    async def hand_to_player(self, name: str, stack: int = 1) -> bool:
        return await self.items.hand_to_player(name, stack)

    async def use_item_by_name(self, name: str) -> bool:
        return await self.items.use_item_by_name(name)

    def get_log_sync(self) -> List[Dict[str, Any]]:
        return self._log

    def get_chests_sync(self) -> List[Dict[str, Any]]:
        return self._chests

    async def mine_then_fetch(self, ore: str, surface_item: str,
                             ore_amount: int = 10) -> bool:
        # 深坑挖矿场景：先挖矿，再回地面拿某物，最后回到坑底玩家身边
        # 第1步：挖矿（在坑底进行）
        await self.submit_goal(Goal(goal_type="gather", target=ore, amount=ore_amount,
                                    reason="坑底挖矿", report_fail="挖不到矿石，主人"))
        # 第2步：回地面取物（用 navigate_to 会自动预判能力并汇报）
        chest = await self.nearest_chest_with(surface_item)
        if chest is None:
            chests = await self.mod.enum_chests()
            chest = chests[0] if chests else None
        if chest:
            if not await self.navigate_to(chest["x"], chest["y"]):
                await self.send_chat("回地面拿东西上不去，等我拿到钩锁/土块再说~")
                return False
            await self.take_from_chest(surface_item, chest)
        else:
            await self.send_chat("附近没有箱子，不知道去哪拿" + surface_item)
            return False
        # 第3步：回到玩家身边（坑底）
        st = self._state
        players = st.get("nearby_players", [])
        if players:
            await self.navigate_to(players[0]["tile_x"], players[0]["tile_y"])
        return True

    @property
    def running(self) -> bool:
        return self._running
