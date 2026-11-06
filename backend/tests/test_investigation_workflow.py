import asyncio
import os
import uuid
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.core.config import settings
from backend.app.models.entities import AgentTask, Approval, ConversationReference, Evidence, Investigation, Issue, Project
from backend.app.models.enums import (
    AgentRole,
    ApprovalDecision,
    ApprovalTarget,
    ChannelType,
    EvidenceType,
    InvestigationOutcome,
    IssueStatus,
    ProvenanceType,
    TaskStatus,
)
from backend.app.schemas.switch import SwitchMessagePayload
from backend.app.services.agents.investigation_coordinator import InvestigationCoordinator
from backend.app.services.agents.roles import (
    EvidenceCitation,
    EvidenceValidationResult,
    IntakeAnalysisResult,
    InvestigationLeadReport,
    InvestigatorResult,
    ReproducerPlan,
)
from backend.app.services.agents.runner import AgentRunner
from backend.app.services.llm.groq_provider import GroqProvider
from backend.app.services.sandbox.docker_runner import DockerSandbox, SandboxResult
from backend.app.services.switch_adapter import switch_adapter
from backend.app.services.workflow_engine import WorkflowEngine


@pytest.fixture
async def db_session():
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def sample_buggy_git_repo(tmp_path: Path):
    """Creates a real local Git repository containing a reproducible bug."""
    repo_dir = tmp_path / "buggy_repo"
    repo_dir.mkdir()

    (repo_dir / "README.md").write_text("# Buggy Project\nProject with reproducible defect.")
    (repo_dir / "pyproject.toml").write_text('[project]\nname = "buggy"\nversion = "0.1.0"\n')

    src_dir = repo_dir / "shop"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    (src_dir / "cart.py").write_text(
        "class ShoppingCart:\n"
        "    def __init__(self):\n"
        "        self.items = []\n"
        "    def add_item(self, name: str, price: float):\n"
        "        self.items.append({'name': name, 'price': price})\n"
        "    def get_total(self) -> float:\n"
        "        # Bug: hardcoded incorrect discount off-by-one\n"
        "        return sum(item['price'] for item in self.items) - 100.0\n"
    )

    tests_dir = repo_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    # Failing test reproducing the bug
    (tests_dir / "test_cart.py").write_text(
        "import unittest\n"
        "from shop.cart import ShoppingCart\n\n"
        "class CartTest(unittest.TestCase):\n"
        "    def test_cart_total(self):\n"
        "        cart = ShoppingCart()\n"
        "        cart.add_item('Book', 50.0)\n"
        "        self.assertEqual(cart.get_total(), 50.0)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )

    # Git init and commit
    os.system(f"git -C {repo_dir} init -b main >/dev/null 2>&1")
    os.system(f"git -C {repo_dir} config user.email 'dev@pragmata.internal'")
    os.system(f"git -C {repo_dir} config user.name 'Dev Pragmata'")
    os.system(f"git -C {repo_dir} add . >/dev/null 2>&1")
    os.system(f"git -C {repo_dir} commit -m 'Initial commit with cart bug' >/dev/null 2>&1")

    return repo_dir


@pytest.fixture
def sample_passing_git_repo(tmp_path: Path):
    """Creates a real local Git repository where tests pass."""
    repo_dir = tmp_path / "passing_repo"
    repo_dir.mkdir()

    (repo_dir / "README.md").write_text("# Passing Project\n")
    src_dir = repo_dir / "shop"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("")
    (src_dir / "cart.py").write_text(
        "class ShoppingCart:\n"
        "    def __init__(self):\n"
        "        self.items = []\n"
        "    def add_item(self, name: str, price: float):\n"
        "        self.items.append({'name': name, 'price': price})\n"
        "    def get_total(self) -> float:\n"
        "        return sum(item['price'] for item in self.items)\n"
    )

    tests_dir = repo_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_cart.py").write_text(
        "import unittest\n"
        "from shop.cart import ShoppingCart\n\n"
        "class CartTest(unittest.TestCase):\n"
        "    def test_cart_total(self):\n"
        "        cart = ShoppingCart()\n"
        "        cart.add_item('Book', 50.0)\n"
        "        self.assertEqual(cart.get_total(), 50.0)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    )

    os.system(f"git -C {repo_dir} init -b main >/dev/null 2>&1")
    os.system(f"git -C {repo_dir} config user.email 'dev@pragmata.internal'")
    os.system(f"git -C {repo_dir} config user.name 'Dev Pragmata'")
    os.system(f"git -C {repo_dir} add . >/dev/null 2>&1")
    os.system(f"git -C {repo_dir} commit -m 'Initial passing repo' >/dev/null 2>&1")

    return repo_dir


class MockAgentRunner:
    """Deterministic agent runner for testing workflow orchestration."""

    def __init__(
        self,
        intake_result: IntakeAnalysisResult,
        investigator_result: InvestigatorResult,
        reproducer_plan: ReproducerPlan,
        validator_result: EvidenceValidationResult,
    ):
        self.intake_result = intake_result
        self.investigator_result = investigator_result
        self.reproducer_plan = reproducer_plan
        self.validator_result = validator_result
        self.executed_roles = []

    async def execute_task(
        self,
        role: AgentRole,
        schema: Any,
        prompt: str,
        issue_id: str,
        switch_room_id: str = None,
        db=None,
        parent_task_id=None,
        timeout_seconds=30.0,
    ):
        self.executed_roles.append(role)

        # Persist task to database if db provided
        if db:
            task = AgentTask(
                issue_id=issue_id,
                agent_role=role,
                status=TaskStatus.COMPLETED,
                task_input={"prompt_sample": prompt[:150]},
                timeout_seconds=int(timeout_seconds),
                parent_task_id=parent_task_id,
            )
            db.add(task)
            await db.flush()

        if role == AgentRole.INTAKE_AGENT:
            return self.intake_result
        elif role == AgentRole.INVESTIGATOR:
            return self.investigator_result
        elif role == AgentRole.REPRODUCER:
            return self.reproducer_plan
        elif role == AgentRole.EVIDENCE_VALIDATOR:
            return self.validator_result
        raise ValueError(f"Unexpected role: {role}")


@pytest.mark.asyncio
async def test_full_investigation_workflow_reproduced(sample_buggy_git_repo: Path, db_session: AsyncSession):
    """
    Exit Criteria 1, 2, 3, 4, 5, 9:
    Full investigation workflow runs against a real repository,
    Docker sandbox executes the failing reproducer command,
    exit code != 0 matches failure pattern,
    outcome is REPRODUCED, evidence and agent tasks are recorded in PostgreSQL,
    and messages are posted to the Switch room.
    """
    db = db_session
    issue_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"

    # Create Project pointing to buggy repo
    project = Project(
        name="Cart App Buggy",
        repo_url=str(sample_buggy_git_repo),
        default_branch="main",
        config={},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # Create Issue
    issue = Issue(
        id=issue_id,
        project_id=project.id,
        title="Cart total gives negative value on checkout",
        description="When I add a 50 dollar book to my cart, the total shows -50 dollars.",
        expected_behavior="Total should be 50 dollars",
        steps_attempted="Added book and viewed cart",
        status=IssueStatus.RECEIVED,
    )
    db.add(issue)

    # Add Switch room reference
    conv = ConversationReference(
        issue_id=issue.id,
        room_id=f"switch_room_{issue_id}_investigation",
        channel_type=ChannelType.INVESTIGATION,
        metadata_json={"title": "Investigation Room"},
    )
    db.add(conv)
    await db.commit()

    # Configure deterministic agent outputs
    intake_res = IntakeAnalysisResult(
        title="Cart total calculated as negative balance",
        summary="Item added for $50 results in -$50 total",
        expected_behaviour="Cart total should equal sum of items ($50)",
        actual_behaviour="Cart total is -$50",
        missing_context=False,
        clarification_questions=[],
        tags=["cart", "pricing", "calculation"],
    )

    investigator_res = InvestigatorResult(
        relevant_files=["shop/cart.py"],
        suspected_symbols=["ShoppingCart.get_total"],
        citations=[
            EvidenceCitation(
                file_path="shop/cart.py",
                line_start=8,
                line_end=10,
                snippet="return sum(item['price'] for item in self.items) - 100.0",
                relevance_note="Direct subtraction of 100 causes negative total",
            )
        ],
        execution_path_summary="Cart initialization -> add_item -> get_total",
        suspected_root_cause_hypothesis="Hardcoded subtraction of 100 in get_total",
        confidence_score=0.98,
    )

    reproducer_plan = ReproducerPlan(
        reproduction_strategy="Execute unittest against ShoppingCart.get_total",
        command_to_run="python3 -m unittest tests/test_cart.py",
        expected_failure_pattern="AssertionError: -50.0 != 50.0",
        prerequisites_or_dependencies=[],
        can_run_offline=True,
    )

    validator_res = EvidenceValidationResult(
        outcome=InvestigationOutcome.REPRODUCED,
        is_valid_reproduction=True,
        evidence_summary="Unit test failed with AssertionError matching the reported defect",
        actual_failure_matches_expected=True,
        distinction_explanation="Defect confirmed by test failure; hypothesis is subtraction bug in get_total",
    )

    runner = MockAgentRunner(
        intake_result=intake_res,
        investigator_result=investigator_res,
        reproducer_plan=reproducer_plan,
        validator_result=validator_res,
    )

    coordinator = InvestigationCoordinator(runner=runner)

    # Track messages posted to Switch
    switch_messages = []
    async def mock_send(msg: SwitchMessagePayload):
        switch_messages.append(msg)
        return {"status": "sent", "id": "msg-123"}

    with patch.object(switch_adapter, "send_message", side_effect=mock_send):
        report: InvestigationLeadReport = await coordinator.run_investigation(
            db=db,
            issue_id=issue.id,
            timeout_per_agent=10.0,
        )

    # 1. Verify Report outcome
    assert report.outcome == InvestigationOutcome.REPRODUCED
    assert report.sandbox_execution_performed is True
    assert report.evidence_validation.is_valid_reproduction is True
    assert report.next_step == "AWAITING_DEVELOPER_TRIAGE"

    # 2. Verify Database Issue status
    await db.refresh(issue)
    assert issue.status == IssueStatus.AWAITING_DEVELOPER_TRIAGE

    # 3. Verify Investigation record
    inv_stmt = select(Investigation).where(Investigation.issue_id == issue.id)
    inv_res = await db.execute(inv_stmt)
    inv = inv_res.scalars().first()
    assert inv is not None
    assert inv.outcome == InvestigationOutcome.REPRODUCED
    assert len(inv.commit_sha) == 40
    assert inv.environment_details["exit_code"] != 0

    # 4. Verify Evidence recorded (citations + docker reproduction output)
    ev_stmt = select(Evidence).where(Evidence.issue_id == issue.id)
    ev_res = await db.execute(ev_stmt)
    ev_items = ev_res.scalars().all()
    assert len(ev_items) >= 2

    # Check for reproduction output evidence
    repro_ev = next((e for e in ev_items if e.evidence_type == EvidenceType.REPRODUCTION_OUTPUT), None)
    assert repro_ev is not None
    assert repro_ev.provenance == ProvenanceType.TOOL
    assert repro_ev.tool_name == "docker_sandbox"
    assert repro_ev.exit_code != 0
    assert "AssertionError" in repro_ev.content

    # Check for citation evidence
    citation_ev = next((e for e in ev_items if e.evidence_type == EvidenceType.FILE_REFERENCE), None)
    assert citation_ev is not None
    assert citation_ev.file_path == "shop/cart.py"
    assert citation_ev.line_start == 8

    # 5. Verify Agent Tasks persisted
    tasks_stmt = select(AgentTask).where(AgentTask.issue_id == issue.id)
    tasks_res = await db.execute(tasks_stmt)
    tasks = tasks_res.scalars().all()
    roles_recorded = [t.agent_role for t in tasks]
    assert AgentRole.INVESTIGATION_LEAD in roles_recorded
    assert AgentRole.INTAKE_AGENT in roles_recorded
    assert AgentRole.INVESTIGATOR in roles_recorded
    assert AgentRole.REPRODUCER in roles_recorded
    assert AgentRole.EVIDENCE_VALIDATOR in roles_recorded

    # 6. Verify Switch room received messages from agents
    assert len(switch_messages) >= 2
    lead_summary_msg = next((m for m in switch_messages if "Investigation Complete" in m.content), None)
    assert lead_summary_msg is not None
    assert "REPRODUCED" in lead_summary_msg.content


@pytest.mark.asyncio
async def test_investigation_outcome_not_reproduced_on_zero_exit_code(sample_passing_git_repo: Path, db_session: AsyncSession):
    """
    Exit Criteria 4, 5:
    When the sandbox execution succeeds (exit code 0), the deterministic rule
    MUST classify the outcome as NOT_REPRODUCED even if the LLM claimed REPRODUCED.
    """
    db = db_session
    issue_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"

    project = Project(
        name="Cart App Passing",
        repo_url=str(sample_passing_git_repo),
        default_branch="main",
        config={},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    issue = Issue(
        id=issue_id,
        project_id=project.id,
        title="False bug report: cart total wrong",
        description="User claims total is wrong",
        status=IssueStatus.RECEIVED,
    )
    db.add(issue)
    await db.commit()

    intake_res = IntakeAnalysisResult(
        title="Cart total inquiry",
        summary="Report claiming incorrect total",
        expected_behaviour="Correct total",
        actual_behaviour="Claimed wrong",
        missing_context=False,
        clarification_questions=[],
    )

    investigator_res = InvestigatorResult(
        relevant_files=["shop/cart.py"],
        suspected_symbols=["ShoppingCart.get_total"],
        citations=[],
        execution_path_summary="get_total execution",
        confidence_score=0.8,
    )

    reproducer_plan = ReproducerPlan(
        reproduction_strategy="Run tests",
        command_to_run="python3 -m unittest tests/test_cart.py",
        expected_failure_pattern="AssertionError",
        can_run_offline=True,
    )

    # Attempted hallucination by LLM claiming REPRODUCED despite passing tests
    hallucinating_validator_res = EvidenceValidationResult(
        outcome=InvestigationOutcome.REPRODUCED,
        is_valid_reproduction=True,
        evidence_summary="LLM mistakenly claims bug reproduced",
        actual_failure_matches_expected=True,
        distinction_explanation="Hallucination attempt",
    )

    runner = MockAgentRunner(
        intake_result=intake_res,
        investigator_result=investigator_res,
        reproducer_plan=reproducer_plan,
        validator_result=hallucinating_validator_res,
    )

    coordinator = InvestigationCoordinator(runner=runner)

    report = await coordinator.run_investigation(db=db, issue_id=issue.id)

    # Invariant enforced: Exit code 0 MUST force NOT_REPRODUCED
    assert report.outcome == InvestigationOutcome.NOT_REPRODUCED
    assert report.evidence_validation.is_valid_reproduction is False
    assert "Deterministic Rule Applied" in report.evidence_validation.distinction_explanation


@pytest.mark.asyncio
async def test_investigation_outcome_needs_information(db_session: AsyncSession):
    """
    Exit Criteria 5, 6:
    When the Intake Agent identifies missing critical context,
    the workflow halts, records NEEDS_INFORMATION, and requests clarification.
    """
    db = db_session
    issue_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"

    project = Project(
        name="Sample Project",
        repo_url="https://github.com/example/sample.git",
        default_branch="main",
        config={},
    )
    db.add(project)
    await db.commit()

    issue = Issue(
        id=issue_id,
        project_id=project.id,
        title="It crashed",
        description="App broke",
        status=IssueStatus.RECEIVED,
    )
    db.add(issue)
    await db.commit()

    intake_res = IntakeAnalysisResult(
        title="App broke",
        summary="Incomplete bug report without any steps, error message, or component name",
        expected_behaviour="Unknown",
        actual_behaviour="Crash",
        missing_context=True,
        clarification_questions=[
            "Which page or feature were you using when the crash occurred?",
            "What exact error message or screen did you see?",
        ],
        tags=["crash", "incomplete"],
    )

    runner = MockAgentRunner(
        intake_result=intake_res,
        investigator_result=InvestigatorResult(relevant_files=[], suspected_symbols=[], execution_path_summary="", confidence_score=0.0),
        reproducer_plan=ReproducerPlan(reproduction_strategy="", command_to_run="", expected_failure_pattern=""),
        validator_result=EvidenceValidationResult(
            outcome=InvestigationOutcome.NEEDS_INFORMATION,
            is_valid_reproduction=False,
            evidence_summary="",
            actual_failure_matches_expected=False,
            distinction_explanation="",
        ),
    )

    coordinator = InvestigationCoordinator(runner=runner)

    report = await coordinator.run_investigation(db=db, issue_id=issue.id)

    assert report.outcome == InvestigationOutcome.NEEDS_INFORMATION
    assert len(report.structured_report.clarification_questions) == 2
    assert report.sandbox_execution_performed is False

    await db.refresh(issue)
    assert issue.status == IssueStatus.NEEDS_INFORMATION


@pytest.mark.asyncio
async def test_investigation_outcome_blocked_on_clone_failure(db_session: AsyncSession):
    """
    Exit Criteria 5:
    When repository clone fails (e.g. invalid URL),
    investigation records outcome as BLOCKED and transitions issue appropriately.
    """
    db = db_session
    issue_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"

    project = Project(
        name="Nonexistent Repo Project",
        repo_url="/path/to/nonexistent/invalid_repo_dir",
        default_branch="main",
        config={},
    )
    db.add(project)
    await db.commit()

    issue = Issue(
        id=issue_id,
        project_id=project.id,
        title="Repo missing test",
        description="Testing clone failure handling",
        status=IssueStatus.RECEIVED,
    )
    db.add(issue)
    await db.commit()

    intake_res = IntakeAnalysisResult(
        title="Repo missing test",
        summary="Valid report format",
        expected_behaviour="Works",
        actual_behaviour="Broken",
        missing_context=False,
        clarification_questions=[],
    )

    runner = MockAgentRunner(
        intake_result=intake_res,
        investigator_result=InvestigatorResult(relevant_files=[], suspected_symbols=[], execution_path_summary="", confidence_score=0.0),
        reproducer_plan=ReproducerPlan(reproduction_strategy="", command_to_run="", expected_failure_pattern=""),
        validator_result=EvidenceValidationResult(
            outcome=InvestigationOutcome.BLOCKED,
            is_valid_reproduction=False,
            evidence_summary="",
            actual_failure_matches_expected=False,
            distinction_explanation="",
        ),
    )

    coordinator = InvestigationCoordinator(runner=runner)

    report = await coordinator.run_investigation(db=db, issue_id=issue.id)

    assert report.outcome == InvestigationOutcome.BLOCKED
    assert "Failed to clone repository" in report.summary

    await db.refresh(issue)
    assert issue.status == IssueStatus.VERIFICATION_BLOCKED


@pytest.mark.asyncio
async def test_developer_triage_actions_and_gate_enforcement(db_session: AsyncSession):
    """
    Exit Criteria 7, 8:
    Developer triage explicitly handles ACCEPTED, REJECTED, REQUEST_INFORMATION, DEFERRED.
    Resolution phase CANNOT start before explicit developer acceptance.
    """
    db = db_session
    issue_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"

    project = Project(
        name="Triage Test Project",
        repo_url="https://github.com/example/triage.git",
        default_branch="main",
        config={},
    )
    db.add(project)
    await db.commit()

    issue = Issue(
        id=issue_id,
        project_id=project.id,
        title="Triage gate issue",
        description="Investigated and reproduced bug",
        status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    )
    db.add(issue)
    await db.commit()

    # Invariant check: resolution CANNOT start before acceptance
    with pytest.raises(Exception) as excinfo:
        await WorkflowEngine.transition_issue(
            db=db,
            issue_id=issue.id,
            target_status=IssueStatus.ROOT_CAUSE_ANALYSIS,
            actor="agent_rogue",
        )
    assert "Illegal state transition" in str(excinfo.value.detail)

    with pytest.raises(Exception) as excinfo:
        await WorkflowEngine.transition_issue(
            db=db,
            issue_id=issue.id,
            target_status=IssueStatus.IMPLEMENTING,
            actor="agent_rogue",
        )
    assert "Illegal state transition" in str(excinfo.value.detail)

    # Developer triage action: ACCEPTED
    accepted_issue = await WorkflowEngine.triage_issue(
        db=db,
        issue_id=issue.id,
        decision=ApprovalDecision.ACCEPTED,
        actor="senior_dev@pragmata.internal",
        notes="Reproduction confirmed. Approved for resolution.",
    )
    assert accepted_issue.status == IssueStatus.ACCEPTED

    # Verify Approval record
    appr_stmt = select(Approval).where(Approval.issue_id == issue.id)
    appr_res = await db.execute(appr_stmt)
    appr = appr_res.scalars().first()
    assert appr is not None
    assert appr.decision == ApprovalDecision.ACCEPTED
    assert appr.actor == "senior_dev@pragmata.internal"
    assert appr.target_type == ApprovalTarget.ISSUE_TRIAGE

    # Now and ONLY now can ROOT_CAUSE_ANALYSIS begin
    rca_issue = await WorkflowEngine.transition_issue(
        db=db,
        issue_id=issue.id,
        target_status=IssueStatus.ROOT_CAUSE_ANALYSIS,
        actor="orchestrator",
    )
    assert rca_issue.status == IssueStatus.ROOT_CAUSE_ANALYSIS


@pytest.mark.asyncio
async def test_developer_triage_rejections_and_deferrals(db_session: AsyncSession):
    """Verify triage actions for REJECTED, REQUEST_INFORMATION, and DEFERRED."""
    db = db_session

    # 1. Reject
    rej_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"
    project = Project(
        name="Triage Test Project 2",
        repo_url="https://github.com/example/triage2.git",
        default_branch="main",
        config={},
    )
    db.add(project)
    await db.commit()

    issue_reject = Issue(
        id=rej_id,
        project_id=project.id,
        title="Reject me",
        description="Not a bug",
        status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    )
    db.add(issue_reject)
    await db.commit()

    res_rej = await WorkflowEngine.triage_issue(
        db=db,
        issue_id=issue_reject.id,
        decision=ApprovalDecision.REJECTED,
        actor="dev@pragmata.internal",
        notes="Working as intended",
    )
    assert res_rej.status == IssueStatus.REJECTED

    # 2. Request Information
    req_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"
    issue_req = Issue(
        id=req_id,
        project_id=project.id,
        title="Need info",
        description="Need more details",
        status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    )
    db.add(issue_req)
    await db.commit()

    res_req = await WorkflowEngine.triage_issue(
        db=db,
        issue_id=issue_req.id,
        decision=ApprovalDecision.REQUEST_INFORMATION,
        actor="dev@pragmata.internal",
        notes="Please provide browser console logs",
    )
    assert res_req.status == IssueStatus.NEEDS_INFORMATION

    # 3. Defer
    def_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"
    issue_def = Issue(
        id=def_id,
        project_id=project.id,
        title="Defer me",
        description="Low priority edge case",
        status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    )
    db.add(issue_def)
    await db.commit()

    res_def = await WorkflowEngine.triage_issue(
        db=db,
        issue_id=issue_def.id,
        decision=ApprovalDecision.DEFERRED,
        actor="dev@pragmata.internal",
        notes="Deferring to next milestone",
    )
    assert res_def.status == IssueStatus.DEFERRED


@pytest.mark.asyncio
async def test_investigation_api_endpoints(sample_buggy_git_repo: Path, async_client: AsyncClient, db_session: AsyncSession):
    """
    Test API endpoints POST /api/v1/issues/{issue_id}/investigate
    and GET /api/v1/issues/{issue_id}/tasks.
    """
    db = db_session
    issue_id = f"PRAG-{uuid.uuid4().hex[:6].upper()}"

    project = Project(
        name="API Cart App",
        repo_url=str(sample_buggy_git_repo),
        default_branch="main",
        config={},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    issue = Issue(
        id=issue_id,
        project_id=project.id,
        title="API Cart total bug",
        description="Testing investigation endpoint",
        status=IssueStatus.RECEIVED,
    )
    db.add(issue)
    await db.commit()

    # Trigger investigation via API
    resp = await async_client.post(f"/api/v1/issues/{issue_id}/investigate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["issue_id"] == issue_id
    assert "outcome" in data
    assert "structured_report" in data

    # Query agent tasks via API
    tasks_resp = await async_client.get(f"/api/v1/issues/{issue_id}/tasks")
    assert tasks_resp.status_code == 200
    tasks_data = tasks_resp.json()
    assert isinstance(tasks_data, list)
    assert len(tasks_data) >= 1
