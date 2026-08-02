"""进程内调用 Agent 的轻量客户端（不走网络）。"""

from typing import Any, Dict

from ..bridge.agent import TerrariaAgent


class AgentClient:
    def __init__(self, agent: TerrariaAgent) -> None:
        self.agent = agent

    def state(self) -> Dict[str, Any]:
        return self.agent.get_state()

    def send_chat(self, text: str) -> None:
        self.agent.bot.send_msg(text)
