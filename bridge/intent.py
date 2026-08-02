"""意图识别：一句话到底是"做完就完"还是"一直做下去"。

这是长期任务体验的关键判断。同样是挖矿：
    "挖10个铁"   → 有限任务，挖够就停，走前台执行器
    "挖铁"       → 长期任务，一直挖到主人喊停，走后台常驻
    "跟着我"     → 天生的长期任务
    "别跟了"     → 停止某个长期任务

只做"是不是长期"这一件事，具体怎么干交给 standing_jobs，
复杂多步规划仍然交给 task_brain。
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# 天生长期的行为（没有自然终点）
FOLLOW_WORDS = ("跟着", "跟上", "跟我", "跟随", "别走丢", "一起走")
GUARD_WORDS = ("守着", "守在", "待在这", "别乱跑", "原地待命")
MINE_WORDS = ("挖", "采", "开采")

# 明确要求停止
STOP_WORDS = ("别跟", "不用跟", "停下", "别挖", "停止", "歇着", "不用挖",
              "别守", "结束任务", "停手")

# 表示"一直/持续"的强化词
FOREVER_WORDS = ("一直", "持续", "不停", "一路", "继续")

# 常见矿物/材料别名
ORE_ALIAS = {
    "铁": "铁矿", "铜": "铜矿", "银": "银矿", "金": "金矿",
    "锡": "锡矿", "铅": "铅矿", "钨": "钨矿", "铂金": "铂金矿",
    "陨石": "陨石矿", "恶魔石": "恶魔石", "石头": "石块", "木": "木材",
}

CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


@dataclass
class Intent:
    """一次意图解析结果。"""

    mode: str                       # longterm / finite / stop / unknown
    kind: str = ""                  # follow / mine / guard
    target: str = ""
    amount: int = 0                 # 0 = 不限量
    raw: str = ""
    reason: str = ""
    # 结构化步骤，直接喂给 TaskBrain（不能是纯字符串，否则规划不出东西）
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> Dict[str, Any]:
        return {"mode": self.mode, "kind": self.kind, "target": self.target,
                "amount": self.amount, "reason": self.reason}


def _parse_amount(text: str) -> int:
    """从话里抠出数量，没有就返回 0（= 不限量 = 长期）。"""
    m = re.search(r"(\d+)\s*(个|块|颗|组|次|只)?", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    for cn, n in CN_NUM.items():
        if re.search(cn + r"\s*(个|块|颗|组|次|只)", text):
            return n
    # "一组" 在泰拉瑞亚里通常是 999，但按常见理解给 99
    if "一组" in text:
        return 99
    return 0


def _parse_ore(text: str) -> str:
    """认出要挖什么。"""
    for alias, full in ORE_ALIAS.items():
        if alias in text:
            return full
    m = re.search(r"(?:挖|采|开采)\s*(?:点|些)?\s*([\u4e00-\u9fa5]{1,4}?)(?:矿)?",
                  text)
    if m:
        w = m.group(1).strip()
        if w and w not in ("点", "些", "一", "个"):
            return ORE_ALIAS.get(w, w if w.endswith("矿") else w + "矿")
    return ""


def parse(text: str) -> Intent:
    """把主人的一句话解析成意图。"""
    t = (text or "").strip()
    low = t.replace(" ", "")

    # 1) 先看是不是喊停
    if any(w in low for w in STOP_WORDS):
        kind = ""
        if any(w in low for w in ("跟", "跟着")):
            kind = "follow"
        elif any(w in low for w in MINE_WORDS):
            kind = "mine"
        elif any(w in low for w in ("守",)):
            kind = "guard"
        return Intent(mode="stop", kind=kind, raw=t, reason="主人喊停")

    # 2) 跟随：天生长期
    if any(w in low for w in FOLLOW_WORDS):
        return Intent(mode="longterm", kind="follow", raw=t,
                      reason="主人让我跟着")

    # 3) 守点：天生长期
    if any(w in low for w in GUARD_WORDS):
        return Intent(mode="longterm", kind="guard", raw=t,
                      reason="主人让我守着")

    # 4) 挖矿：看有没有数量决定长期还是有限
    if any(w in low for w in MINE_WORDS):
        ore = _parse_ore(low)
        amount = _parse_amount(low)
        forever = any(w in low for w in FOREVER_WORDS)
        if amount and not forever:
            # 说了数量 → 有限任务，交给前台执行器
            return Intent(mode="finite", kind="mine", target=ore,
                          amount=amount, raw=t,
                          reason=f"挖{amount}个{ore}",
                          steps=[{"action": "mine", "item": ore or "矿",
                                  "amount": amount}])
        # 没说数量 → 一直挖
        return Intent(mode="longterm", kind="mine", target=ore,
                      amount=0 if forever else amount, raw=t,
                      reason=f"一直挖{ore or '矿'}")

    return Intent(mode="unknown", raw=t)


def is_longterm(text: str) -> bool:
    return parse(text).mode == "longterm"
