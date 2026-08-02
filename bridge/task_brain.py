"""复杂任务大脑：收到任务后按 想(评估)→处理(规划)→做(执行) 三阶段推进。

「想」不再是逐步孤立检查，而是三层递进：
    1. 推演：拿虚拟背包把整串步骤先跑一遍，让后面的步骤看得到前面的产出
    2. 补救：哪一步缺东西，就递归找最省事的办法（取/合成/挖），生成前置步骤
    3. 优化：去掉已经满足的步骤、合并重复、按依赖排好序
只有真的无路可走才回报"做不了"，并且要说清楚缺什么、想让主人怎么帮。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .task_chain import Goal
from .world_model import WorldModel
from .reasoner import Reasoner, COST_ASK

MAX_REPAIR_ROUND = 4     # 补救迭代上限，防止来回打转


@dataclass
class Assessment:
    """想：这件事能不能做、缺什么、打算怎么补。"""

    doable: bool = True
    blockers: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)      # 自己想到的补救办法
    thoughts: List[str] = field(default_factory=list)   # 思考过程（可解释）
    steps: List[Dict[str, Any]] = field(default_factory=list)  # 补救后的完整步骤
    need_from_owner: str = ""                           # 需要主人给什么

    def say(self) -> str:
        if self.doable:
            if self.fixes:
                return "、".join(self.fixes) + "，然后就能做了"
            return "、".join(self.notes) if self.notes else "这个我能做"
        head = "、".join(self.blockers) if self.blockers else "这个我做不了"
        if self.need_from_owner:
            head += f"，{self.need_from_owner}"
        return head

    def explain(self) -> str:
        """把思考过程讲成人话，供主人追问'你怎么想的'。"""
        return "\n".join(f"{i+1}. {t}" for i, t in enumerate(self.thoughts))


@dataclass
class StepPlan:
    """处理：拆成什么步骤、每步怎么做。"""

    goals: List[Goal] = field(default_factory=list)
    outline: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)   # 省掉的步骤及原因

    def say(self) -> str:
        return " → ".join(self.outline) if self.outline else "（无步骤）"


class TaskBrain:
    """把一句话任务变成「先想、再规划、后执行」的完整流程。"""

    def __init__(self, agent) -> None:
        self.agent = agent
        self.world = WorldModel(agent)
        self.reasoner = Reasoner(agent, self.world)
        self._last: Optional[Assessment] = None

    # ---------- 想 ----------
    async def think(self, steps: List[Dict[str, Any]]) -> Assessment:
        """推演 → 补救 → 定稿。返回的 steps 是补全前置后的完整步骤。"""
        a = Assessment()
        work = [dict(s) for s in steps]
        if not work:
            a.doable = False
            a.blockers.append("没告诉我要做什么")
            return a

        base = await self.world.snapshot()
        a.thoughts.append(f"先看看现在有什么：" + self._say_inv(base))

        for round_i in range(MAX_REPAIR_ROUND):
            sim = await self.world.simulate(work, base)

            # 记录推演心得
            for s in sim.steps:
                if s.note:
                    a.notes.append(f"{s.desc}：{s.note}")

            if sim.ok:
                a.thoughts.append(
                    f"推演第{round_i+1}遍：整串都能走通（共{len(work)}步）")
                a.doable = True
                a.steps = work
                self._last = a
                return a

            gap = sim.first_gap()
            a.thoughts.append(
                f"推演第{round_i+1}遍：卡在第{gap.index}步「{gap.desc}」——{gap.gap}")

            # 想办法补救
            fix = await self.reasoner.fix_for(
                gap.need_item or "", gap.need_amount or 1, base)
            if fix is None or fix.cost >= COST_ASK or not fix.steps:
                a.doable = False
                a.blockers.append(f"第{gap.index}步{gap.gap}")
                if fix is not None and fix.how == "ask":
                    a.need_from_owner = fix.desc
                a.thoughts.append("想不出办法了，得请主人帮忙")
                a.steps = work
                self._last = a
                return a

            # 把前置步骤插到卡住那步之前
            insert_at = gap.index - 1
            work = work[:insert_at] + fix.steps + work[insert_at:]
            a.fixes.append(fix.say())
            a.thoughts.append(f"想到办法：{fix.say()}（插到第{insert_at+1}步前）")

        a.doable = False
        a.blockers.append("这事绕来绕去理不清，我先停一下")
        a.steps = work
        self._last = a
        return a

    def last_assessment(self) -> Optional[Assessment]:
        return self._last

    @staticmethod
    def _say_inv(vi) -> str:
        bits = []
        if vi.has_pickaxe:
            bits.append("有镐子")
        else:
            bits.append("没镐子")
        if vi.has_hook:
            bits.append("有钩爪")
        top = sorted(vi.counts.items(), key=lambda kv: -kv[1])[:3]
        for name, n in top:
            if n > 0:
                bits.append(f"{name}x{n}")
        return "、".join(bits) if bits else "身上空空的"

    # ---------- 处理 ----------
    def plan(self, steps: List[Dict[str, Any]], goal_text: str = "",
             assess: Optional[Assessment] = None) -> StepPlan:
        """把步骤描述编译成可执行 Goal 序列，并顺手做几项优化。"""
        p = StepPlan()
        # 优先用「想」补全后的步骤
        src = (assess.steps if assess and assess.steps else steps)
        src = self._dedupe(src, p)

        for s in src:
            action = str(s.get("action", "")).lower()
            item = s.get("item", "")
            amt = int(s.get("amount", 1) or 1)

            if action in ("mine", "gather"):
                p.goals.append(Goal(goal_type="gather", target=item, amount=amt,
                                    reason=goal_text,
                                    report_fail=f"挖 {item} 没成功，主人"))
                p.outline.append(f"挖{item}x{amt}")
            elif action == "craft":
                p.goals.append(Goal(goal_type="gather", target=item, amount=amt,
                                    craft_first=True, reason=goal_text,
                                    report_fail=f"合成 {item} 失败了"))
                p.outline.append(f"合成{item}x{amt}")
            elif action == "fetch":
                p.goals.append(Goal(goal_type="fetch", target=item, amount=amt,
                                    reason=goal_text,
                                    report_fail=f"没能取到 {item}"))
                p.outline.append(f"取{item}x{amt}")
            elif action in ("climb", "goto"):
                tgt = f"{s.get('x', 0)},{s.get('y', 0)}"
                p.goals.append(Goal(goal_type=action, target=tgt, reason=goal_text,
                                    report_fail=f"我到不了 ({tgt})"))
                p.outline.append(("爬到" if action == "climb" else "走到") + f"({tgt})")
            elif action == "give":
                p.goals.append(Goal(goal_type="gather", target=item, amount=amt,
                                    deliver_to_player=True, reason=goal_text,
                                    report_fail=f"没能把 {item} 给你"))
                p.outline.append(f"给主人{item}x{amt}")
            elif action == "follow":
                p.goals.append(Goal(goal_type="follow", target="", reason=goal_text))
                p.outline.append("回到主人身边")
        return p

    @staticmethod
    def _dedupe(steps: List[Dict[str, Any]], p: StepPlan) -> List[Dict[str, Any]]:
        """合并相邻同类步骤：挖5个铁+挖3个铁 → 挖8个铁。"""
        out: List[Dict[str, Any]] = []
        for s in steps:
            if out:
                prev = out[-1]
                same = (str(prev.get("action", "")).lower()
                        == str(s.get("action", "")).lower()
                        and prev.get("item") == s.get("item")
                        and str(s.get("action", "")).lower() in
                        ("mine", "gather", "fetch"))
                if same:
                    merged = int(prev.get("amount", 1) or 1) + int(
                        s.get("amount", 1) or 1)
                    prev["amount"] = merged
                    p.skipped.append(
                        f"把两次{s.get('item')}合并成{merged}个，少跑一趟")
                    continue
            out.append(dict(s))
        return out
