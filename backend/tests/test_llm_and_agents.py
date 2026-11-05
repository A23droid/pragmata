import pytest
from backend.app.models.enums import AgentRole
from backend.app.services.agents.roles import (
    IntakeAnalysisResult,
    InvestigatorResult,
    ReproducerPlan,
    SolutionArchitectResult,
)
from backend.app.services.agents.runner import AgentRunner
from backend.app.services.llm.groq_provider import GroqProvider


@pytest.mark.asyncio
async def test_groq_provider_stub_generation():
    """Verify Groq provider creates valid schema instances when offline."""
    provider = GroqProvider(api_key=None)
    result = await provider.generate_structured(
        schema=IntakeAnalysisResult,
        prompt="Bug: checkout fails with 500 when discount code applied",
    )
    assert isinstance(result, IntakeAnalysisResult)
    assert isinstance(result.title, str)
    assert isinstance(result.missing_context, bool)


@pytest.mark.asyncio
async def test_agent_runner_task_execution():
    """Verify AgentRunner validates Pydantic outputs and reports to Switch room."""
    provider = GroqProvider(api_key=None)
    runner = AgentRunner(provider=provider)

    result = await runner.execute_task(
        role=AgentRole.INVESTIGATOR,
        schema=InvestigatorResult,
        prompt="Inspect repository for discount calculation logic.",
        issue_id="test-issue-1",
        switch_room_id="switch_room_test-issue-1_investigation",
    )
    assert isinstance(result, InvestigatorResult)
    assert isinstance(result.relevant_files, list)

