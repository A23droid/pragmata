import asyncio
import logging
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

from backend.app.models.enums import AgentRole
from backend.app.schemas.switch import SwitchHandoff, SwitchMessagePayload
from backend.app.services.llm.base import LLMProvider
from backend.app.services.llm.groq_provider import GroqProvider
from backend.app.services.switch_adapter import switch_adapter

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

ROLE_PROMPTS = {
    AgentRole.INTAKE_AGENT: (
        "You are the PRAGMATA Intake Agent. Your job is to analyze unstructured bug reports "
        "submitted by non-technical reporters, structure them into expected vs actual behaviour, "
        "and determine if essential information is missing without hallucinating."
    ),
    AgentRole.INVESTIGATOR: (
        "You are the PRAGMATA Repository Investigator. Given an issue and repository structure, "
        "identify the exact files, functions, and symbols involved. Do not speculate beyond evidence."
    ),
    AgentRole.REPRODUCER: (
        "You are the PRAGMATA Reproducer. Design a minimal reproduction procedure or test that can run "
        "in an isolated container to recreate the reported defect. Identify the exact failing command."
    ),
    AgentRole.ROOT_CAUSE_ANALYST: (
        "You are the PRAGMATA Root Cause Analyst. Identify the fundamental code defect causing the confirmed "
        "bug and cite concrete evidence lines."
    ),
    AgentRole.SOLUTION_ARCHITECT: (
        "You are the PRAGMATA Solution Architect. Propose 2 or 3 distinct, maintainable fix strategies. "
        "Target the root cause with the smallest complete change."
    ),
    AgentRole.CRITIC: (
        "You are the PRAGMATA Critic. Challenge the proposed fix strategies, uncover hidden regression risks, "
        "and point out if any proposal fails to solve the root cause."
    ),
    AgentRole.SCOPE_GUARDIAN: (
        "You are the independent PRAGMATA Scope Guardian. Guard against overengineering, scope creep, "
        "unnecessary refactoring, and unrelated file changes. Intervene with evidence."
    ),
}


class AgentRunner:
    """
    Deterministic Agent Runner.
    Enforces task budgets, timeouts, Pydantic schema validation,
    and dispatches visible events to Switch issue rooms.
    """

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or GroqProvider()

    async def execute_task(
        self,
        role: AgentRole,
        schema: Type[T],
        prompt: str,
        issue_id: Optional[str] = None,
        switch_room_id: Optional[str] = None,
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
    ) -> T:
        system_prompt = ROLE_PROMPTS.get(role, "You are a specialized PRAGMATA engineering agent.")
        logger.info(f"Starting agent task: {role.value} (timeout={timeout_seconds}s, retries={max_retries})")

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                # Enforce strict bounded timeout
                result = await asyncio.wait_for(
                    self.provider.generate_structured(
                        schema=schema,
                        prompt=prompt,
                        system_instruction=system_prompt,
                    ),
                    timeout=timeout_seconds,
                )

                # Report structured progress to Switch issue room
                if switch_room_id:
                    msg_content = f"**[{role.value}] Completed Task**:\n```json\n{result.model_dump_json(indent=2)}\n```"
                    await switch_adapter.send_message(
                        SwitchMessagePayload(
                            room_id=switch_room_id,
                            sender_id=role.value,
                            sender_role=role.value,
                            content=msg_content,
                            metadata={"role": role.value, "attempt": attempt},
                        )
                    )

                return result
            except (asyncio.TimeoutError, ValidationError, Exception) as ex:
                last_error = ex
                logger.warning(f"Task attempt {attempt} failed for {role.value}: {ex}")
                if attempt < max_retries:
                    await asyncio.sleep(1.0)

        raise RuntimeError(f"Agent {role.value} failed after {max_retries} attempts: {last_error}")


agent_runner = AgentRunner()

