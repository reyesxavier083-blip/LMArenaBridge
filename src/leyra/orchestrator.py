"""Permission-aware coordinator for LEYRA agents."""
from __future__ import annotations

from typing import Any

from .agents import Agent, AgentResult
from .storage import Storage


class Orchestrator:
    def __init__(self, agents: dict[str, Agent], storage: Storage) -> None:
        self.agents = agents
        self.storage = storage

    async def dispatch(self, agent_name: str, payload: dict[str, Any], actor: str = "api") -> AgentResult:
        agent = self.agents.get(agent_name)
        if agent is None:
            self.storage.audit("agent.dispatch", actor, "unknown_agent")
            return AgentResult("orchestrator", "rejected", "Unknown agent.", {})
        result = await agent.run(payload)
        self.storage.audit("agent.dispatch", actor, f"{agent_name}:{result.status}")
        return result
