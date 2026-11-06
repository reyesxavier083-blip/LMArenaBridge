"""Agent contracts and honest capability adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .storage import Storage


@dataclass
class AgentResult:
    agent: str
    status: str
    message: str
    data: dict[str, Any]


class Agent(Protocol):
    name: str

    async def run(self, payload: dict[str, Any]) -> AgentResult: ...


class PlannerAgent:
    name = "planner"

    async def run(self, payload: dict[str, Any]) -> AgentResult:
        objective = str(payload.get("objective", "")).strip()
        if not objective:
            return AgentResult(self.name, "rejected", "An objective is required.", {})
        return AgentResult(
            self.name,
            "planned",
            "Objective converted into a reviewable plan; no external action was executed.",
            {
                "objective": objective,
                "steps": [
                    "Clarify the requested outcome",
                    "Select an authorized specialist",
                    "Validate permissions and required inputs",
                    "Execute only configured capabilities",
                    "Verify and audit the result",
                ],
            },
        )


class MemoryAgent:
    name = "memory"

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    async def run(self, payload: dict[str, Any]) -> AgentResult:
        content = str(payload.get("content", "")).strip()
        namespace = str(payload.get("namespace", "general")).strip() or "general"
        if not content:
            return AgentResult(self.name, "rejected", "Memory content is required.", {})
        memory_id = self.storage.save_memory(namespace, content)
        return AgentResult(self.name, "completed", "Memory saved.", {"memory_id": memory_id})


class NotConfiguredAgent:
    """Visible adapter for a planned subsystem whose provider is not connected yet."""

    def __init__(self, name: str, capability: str) -> None:
        self.name = name
        self.capability = capability

    async def run(self, payload: dict[str, Any]) -> AgentResult:
        return AgentResult(
            self.name,
            "not_configured",
            f"{self.capability} adapter is registered but has no provider implementation yet.",
            {"external_action_executed": False},
        )


def build_agents(storage: Storage) -> dict[str, Agent]:
    return {
        "planner": PlannerAgent(),
        "memory": MemoryAgent(storage),
        "research": NotConfiguredAgent("research", "Web research"),
        "code": NotConfiguredAgent("code", "Code execution"),
        "security": NotConfiguredAgent("security", "Security scanning"),
        "wordpress": NotConfiguredAgent("wordpress", "WordPress integration"),
        "vision": NotConfiguredAgent("vision", "Vision processing"),
        "voice": NotConfiguredAgent("voice", "Speech processing"),
        "creative": NotConfiguredAgent("creative", "Creative generation"),
        "automation": NotConfiguredAgent("automation", "Workflow automation"),
    }
