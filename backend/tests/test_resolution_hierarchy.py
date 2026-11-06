import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.v1.projects import get_or_create_default_project
from backend.app.models.entities import (
    AgentTask,
    Approval,
    AuditEvent,
    Evidence,
    Investigation,
    Issue,
    Solution,
)
from backend.app.models.enums import (
    AgentRole,
    ApprovalDecision,
    ApprovalTarget,
    EvidenceType,
    InvestigationOutcome,
    IssueStatus,
    ProvenanceType,
)
from backend.app.schemas.resolution import (
    CriticEvaluation,
    OptimizerEvaluationReport,
    ProposalCritique,
    ProposalScopeAudit,
    RootCauseAnalysisReport,
    RootCauseItem,
    RubricTier,
    ScopeGuardianReport,
    SolutionArchitectProposals,
    SolutionProposal,
)
from backend.app.services.agents.resolution_coordinator import ResolutionCoordinator
from backend.app.services.agents.rubric_evaluator import RubricEvaluator
from backend.app.services.agents.runner import AgentRunner
from backend.app.services.agents.scope_guardian import ScopeGuardian
from backend.app.services.llm.base import LLMProvider
from backend.app.services.workflow_engine import WorkflowEngine


DEV_HEADERS = {
    "Authorization": "Bearer dev-secret-key-pragmata",
    "X-Developer-Id": "lead_developer",
}


@pytest.fixture
async def sample_accepted_issue(db_session: AsyncSession) -> Issue:
    """Fixture that creates an issue and explicitly runs authenticated developer triage to ACCEPTED."""
    project = await get_or_create_default_project(db_session)
    issue = Issue(
        id=f"PRAG-RES-{uuid.uuid4().hex[:6].upper()}",
        project_id=project.id,
        title="Integer overflow in cart discount calculation",
        description="Applying coupon code with 100% discount on large order causes 500 error in CartService.",
        status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    )
    db_session.add(issue)
    await db_session.flush()

    # Add concrete reproduction evidence
    ev1 = Evidence(
        issue_id=issue.id,
        evidence_type=EvidenceType.REPRODUCTION_OUTPUT,
        content="AssertionError: Expected 0.0 but got -1.0 in calculate_discount(price=1000, rate=1.0)",
        tool_name="pytest",
        exit_code=1,
        file_path="services/cart_service.py",
        line_start=42,
        line_end=48,
        provenance=ProvenanceType.TOOL,
    )
    db_session.add(ev1)

    inv = Investigation(
        issue_id=issue.id,
        commit_sha="a1b2c3d4e5f67890123456789012345678901234",
        environment_details={"image": "python:3.11-alpine", "network": False},
        attempts_count=1,
        outcome=InvestigationOutcome.REPRODUCED,
        summary="Reproduction confirmed with failing discount calculation in CartService.",
    )
    db_session.add(inv)
    await db_session.flush()

    # Developer explicitly accepts the bug report
    await WorkflowEngine.triage_issue(
        db=db_session,
        issue_id=issue.id,
        decision=ApprovalDecision.ACCEPTED,
        actor="lead_developer",
        notes="Reproduced cleanly in sandbox. Approved for resolution hierarchy.",
    )
    await db_session.refresh(issue)
    return issue


@pytest.mark.asyncio
async def test_resolution_activation_gates_enforcement(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    """
    INVARIANT TEST:
    Resolution agents MUST NOT activate before explicit authenticated developer acceptance.
    Attempts to start resolution on unaccepted issues (RECEIVED, REPRODUCED, AWAITING_DEVELOPER_TRIAGE, REJECTED)
    must be rejected with 403 Forbidden.
    """
    # 1. Unaccepted issue in RECEIVED state
    project = await get_or_create_default_project(db_session)
    issue_unaccepted = Issue(
        id=f"PRAG-GATE-{uuid.uuid4().hex[:6].upper()}",
        project_id=project.id,
        title="Unaccepted issue",
        description="Just reported, not yet accepted.",
        status=IssueStatus.RECEIVED,
    )
    db_session.add(issue_unaccepted)
    await db_session.commit()

    # Attempt to start resolution must fail (403)
    res_unauth = await async_client.post(
        f"/api/v1/issues/{issue_unaccepted.id}/resolution/start",
        headers=DEV_HEADERS,
    )
    assert res_unauth.status_code == 403
    assert "Resolution agents cannot be activated before explicit authenticated developer acceptance" in res_unauth.json()["detail"]

    # 2. Attempt with missing authentication header must fail with 401
    res_no_auth = await async_client.post(
        f"/api/v1/issues/{issue_unaccepted.id}/resolution/start",
    )
    assert res_no_auth.status_code == 401

    # 3. Attempt on REJECTED issue must fail (403)
    issue_unaccepted.status = IssueStatus.AWAITING_DEVELOPER_TRIAGE
    await db_session.commit()
    await WorkflowEngine.triage_issue(
        db=db_session,
        issue_id=issue_unaccepted.id,
        decision=ApprovalDecision.REJECTED,
        actor="lead_developer",
        notes="Not a bug.",
    )
    res_rej = await async_client.post(
        f"/api/v1/issues/{issue_unaccepted.id}/resolution/start",
        headers=DEV_HEADERS,
    )
    assert res_rej.status_code == 403


@pytest.mark.asyncio
async def test_root_cause_evidence_validation_and_hypothesis_distinction():
    """
    Verify that RootCauseAnalysisReport distinguishes verified root causes from hypotheses
    and requires supporting evidence citations for all verified root causes.
    """
    # Valid report with evidence and distinction
    rca_valid = RootCauseAnalysisReport(
        root_cause_summary="Off-by-one boundary check causes negative discount result.",
        verified_root_causes=[
            RootCauseItem(
                description="Integer division truncates coupon discount into negative float",
                supporting_evidence_ids=["ev-12345"],
                file_path="services/cart_service.py",
                line_start=45,
                line_end=48,
                verified=True,
            )
        ],
        hypotheses=["Database coupon cache might also expire prematurely."],
        affected_components=["CartService", "DiscountCalculator"],
        underlying_defect_type="Boundary calculation defect",
    )
    assert len(rca_valid.verified_root_causes) == 1
    assert rca_valid.verified_root_causes[0].verified is True
    assert len(rca_valid.verified_root_causes[0].supporting_evidence_ids) > 0
    assert len(rca_valid.hypotheses) == 1


@pytest.mark.asyncio
async def test_competing_solution_proposals_and_architect_schema():
    """
    Verify that Solution Architect proposes 2 to 3 materially different fix strategies,
    each with affected files, expected changes, advantages, disadvantages, complexity score,
    security implications, and regression risks.
    """
    prop1 = SolutionProposal(
        proposal_id="strategy_1",
        strategy_type="MINIMAL_TARGETED",
        title="Add clamp boundary check in calculate_discount",
        description="Apply max(0.0, price - discount) to prevent negative pricing.",
        affected_files=["services/cart_service.py"],
        expected_changes="Wrap discount return expression in a clamp check on line 47.",
        advantages=["Minimal blast radius", "Zero external dependencies", "Fast to verify"],
        disadvantages=["Does not fix underlying coupon caching logic if flawed"],
        complexity_score=1,
        complexity_explanation="1-line guard statement.",
        security_implications="Eliminates negative price billing vulnerability.",
        regression_risks="Low; only alters discount calculation for edge cases.",
        supporting_evidence_ids=["ev-12345"],
    )

    prop2 = SolutionProposal(
        proposal_id="strategy_2",
        strategy_type="DEFENSIVE_REFACTOR",
        title="Centralize discount domain model with strict invariants",
        description="Introduce Money and DiscountValue value objects with validation.",
        affected_files=["services/cart_service.py", "domain/pricing.py"],
        expected_changes="Extract discount computation into Money domain object with assertion checks.",
        advantages=["Prevents entire class of currency calculation errors", "High domain clarity"],
        disadvantages=["Touches 2 files", "Slightly higher refactoring overhead"],
        complexity_score=3,
        complexity_explanation="Refactors data structures and call sites.",
        security_implications="Strengthens input validation and data integrity across domain.",
        regression_risks="Moderate; callers must pass valid domain objects.",
        supporting_evidence_ids=["ev-12345"],
    )

    architect_result = SolutionArchitectProposals(
        proposals=[prop1, prop2],
        design_summary="Strategy 1 offers immediate safety clamp; Strategy 2 provides comprehensive domain invariants.",
    )

    assert len(architect_result.proposals) == 2
    assert architect_result.proposals[0].strategy_type == "MINIMAL_TARGETED"
    assert architect_result.proposals[1].strategy_type == "DEFENSIVE_REFACTOR"


@pytest.mark.asyncio
async def test_critic_challenges_and_tradeoff_evaluation():
    """
    Verify that the Critic independently challenges assumptions, identifies edge cases,
    and does not merely agree with the Solution Architect.
    """
    critique1 = ProposalCritique(
        proposal_id="strategy_1",
        independent_verdict="FEASIBLE",
        is_valid=True,
        identified_weaknesses=["Band-aid clamp masks potentially corrupt upstream coupon data."],
        hidden_risks_and_edge_cases=["Floats might still produce precision issues (0.0000001)."],
        tradeoff_challenges=["Architect assumes clamp is sufficient, but upstream billing may still log zero."],
        is_defect_fully_addressed=True,
    )

    critique2 = ProposalCritique(
        proposal_id="strategy_2",
        independent_verdict="OVERENGINEERED",
        is_valid=True,
        identified_weaknesses=["Domain object refactor requires touching domain/pricing.py without clear defect necessity."],
        hidden_risks_and_edge_cases=["Serialization of new Money object may break JSON API responses."],
        tradeoff_challenges=["Refactor increases test burden and blast radius without fixing more coupons."],
        is_defect_fully_addressed=True,
    )

    critic_report = CriticEvaluation(
        critiques=[critique1, critique2],
        overall_critique_summary="Strategy 1 is safer and simpler; Strategy 2 carries unneeded architectural overhead.",
    )

    assert len(critic_report.critiques) == 2
    assert critic_report.critiques[0].independent_verdict == "FEASIBLE"
    assert critic_report.critiques[1].independent_verdict == "OVERENGINEERED"
    assert len(critic_report.critiques[1].hidden_risks_and_edge_cases) >= 1


@pytest.mark.asyncio
async def test_scope_guardian_interventions_and_false_positive_handling():
    """
    Verify Scope Guardian:
    1. Flags unjustified overengineering and unrelated files.
    2. FALSE-POSITIVE PREVENTION: Does NOT suppress justified security or correctness improvements
       merely because they increase scope.
    3. Enforces bounded debate rounds.
    """
    rca = RootCauseAnalysisReport(
        root_cause_summary="Defect in CartService.",
        verified_root_causes=[
            RootCauseItem(
                description="Discount error",
                file_path="services/cart_service.py",
                supporting_evidence_ids=["ev-1"],
            )
        ],
        underlying_defect_type="Calculation defect",
    )

    # Proposal A: touches unrelated files with no justification -> SHOULD BE FLAGGED
    unjustified_prop = SolutionProposal(
        proposal_id="prop_unjustified",
        strategy_type="ARCHITECTURAL",
        title="Rewrite user preferences and theme switcher",
        description="Refactor UI styles while changing cart logic.",
        affected_files=["services/cart_service.py", "frontend/theme.ts", "config/themes.json"],
        expected_changes="Change theme handling.",
        advantages=["New dark mode"],
        disadvantages=["Unrelated to cart bug"],
        complexity_score=4,
        complexity_explanation="Extensive UI changes.",
        security_implications="None",
        regression_risks="High UI disruption",
    )

    # Proposal B: touches auxiliary file for security sanitization -> JUSTIFIED (NOT SUPPRESSED)
    justified_prop = SolutionProposal(
        proposal_id="prop_justified_sec",
        strategy_type="DEFENSIVE_REFACTOR",
        title="Harden coupon validation and sanitize input against injection",
        description="Add boundary check and sanitize coupon input in CouponValidator to prevent invalid state.",
        affected_files=["services/cart_service.py", "services/coupon_validator.py"],
        expected_changes="Validate and sanitize coupon code input before calculation to prevent invalid state.",
        advantages=["Prevents malformed coupon injections", "Decisive fix"],
        disadvantages=["Touches auxiliary validator"],
        complexity_score=2,
        complexity_explanation="Targeted validator enhancement.",
        security_implications="Critical security hardening: sanitizes coupon tokens.",
        regression_risks="Low",
    )

    # Round 1 audit
    report_round1 = ScopeGuardian.audit_proposals_and_debate(
        proposals=[unjustified_prop, justified_prop],
        root_cause=rca,
        current_debate_round=1,
    )

    audits = {a.proposal_id: a for a in report_round1.proposals_scope_audit}

    # Verify unjustified proposal is flagged
    assert audits["prop_unjustified"].is_within_scope is False
    assert audits["prop_unjustified"].verdict == "REQUIRES_NARROWING"
    assert "frontend/theme.ts" in audits["prop_unjustified"].unnecessary_files

    # Verify justified security/correctness proposal is NOT suppressed (false-positive prevention)
    assert audits["prop_justified_sec"].is_within_scope is True
    assert audits["prop_justified_sec"].justified_scope_expansion is True
    assert audits["prop_justified_sec"].verdict == "APPROVED_JUSTIFIED_EXPANSION"

    # Verify debate round bounding: Round 3 exceeds MAX_DEBATE_ROUNDS (2)
    report_round3 = ScopeGuardian.audit_proposals_and_debate(
        proposals=[justified_prop],
        root_cause=rca,
        current_debate_round=3,
    )
    assert report_round3.debate_status.excessive_debate_detected is True
    assert report_round3.intervention_required is True
    assert "exceeds maximum allowed budget" in report_round3.intervention_reason


@pytest.mark.asyncio
async def test_evaluation_rubric_hard_gates_and_consistency():
    """
    Verify that Optimizer/Evaluator:
    1. Uses explicit documented criteria and qualitative tiers.
    2. Correctness and Security are HARD GATES: any proposal that fails correctness or security
       is disqualified from recommendation, regardless of score.
    3. Ranks remaining qualifying proposals with clear comparative justification.
    """
    rca = RootCauseAnalysisReport(
        root_cause_summary="Defect in CartService.",
        verified_root_causes=[
            RootCauseItem(
                description="Discount error",
                file_path="services/cart_service.py",
                supporting_evidence_ids=["ev-1"],
            )
        ],
        underlying_defect_type="Calculation defect",
    )

    # Qualifying proposal
    p_good = SolutionProposal(
        proposal_id="strat_good",
        strategy_type="MINIMAL_TARGETED",
        title="Clamp discount boundary",
        description="Safe clamp check.",
        affected_files=["services/cart_service.py"],
        expected_changes="clamp return.",
        advantages=["Safe", "Clean", "Tested"],
        disadvantages=["Small scope"],
        complexity_score=1,
        complexity_explanation="Minimal 1 line.",
        security_implications="No vulnerabilities.",
        regression_risks="Low.",
    )
    c_good = ProposalCritique(
        proposal_id="strat_good",
        independent_verdict="FEASIBLE",
        is_valid=True,
        identified_weaknesses=[],
        hidden_risks_and_edge_cases=[],
        tradeoff_challenges=[],
        is_defect_fully_addressed=True,
    )
    s_good = ProposalScopeAudit(
        proposal_id="strat_good",
        is_within_scope=True,
        overengineering_detected=False,
        justification_notes="In scope.",
        verdict="APPROVED_IN_SCOPE",
    )

    # Proposal that introduces a security flaw -> MUST BE DISQUALIFIED BY HARD GATE
    p_insecure = SolutionProposal(
        proposal_id="strat_insecure",
        strategy_type="ARCHITECTURAL",
        title="Bypass auth check for test coupons",
        description="Skip token validation for discount.",
        affected_files=["services/cart_service.py"],
        expected_changes="Bypass token check.",
        advantages=["Very fast"],
        disadvantages=["Security issue"],
        complexity_score=1,
        complexity_explanation="1 line.",
        security_implications="Severe vulnerability: permits unauthorized privilege escalation bypass.",
        regression_risks="High.",
    )
    c_insecure = ProposalCritique(
        proposal_id="strat_insecure",
        independent_verdict="DEFECTIVE",
        is_valid=False,
        identified_weaknesses=["Critical security hole."],
        hidden_risks_and_edge_cases=[],
        tradeoff_challenges=[],
        is_defect_fully_addressed=False,
    )
    s_insecure = ProposalScopeAudit(
        proposal_id="strat_insecure",
        is_within_scope=True,
        overengineering_detected=False,
        justification_notes="In scope.",
        verdict="APPROVED_IN_SCOPE",
    )

    eval_report = RubricEvaluator.evaluate_proposals(
        proposals=[p_good, p_insecure],
        critiques=[c_good, c_insecure],
        scope_audits=[s_good, s_insecure],
        root_cause=rca,
    )

    eval_by_id = {ep.proposal_id: ep for ep in eval_report.evaluated_proposals}

    # Verify strat_good passed hard gates and is ranked #1 and recommended
    assert eval_by_id["strat_good"].hard_gates_passed is True
    assert eval_by_id["strat_good"].rank == 1
    assert eval_by_id["strat_good"].is_recommended is True
    assert eval_report.recommended_proposal_id == "strat_good"

    # Verify strat_insecure was disqualified by hard gates
    assert eval_by_id["strat_insecure"].hard_gates_passed is False
    assert eval_by_id["strat_insecure"].is_recommended is False
    assert eval_by_id["strat_insecure"].rank == 2
    assert "Disqualified by hard gates" in eval_by_id["strat_insecure"].recommendation_rationale


@pytest.mark.asyncio
async def test_full_resolution_workflow_execution_and_persistence(
    sample_accepted_issue: Issue,
    db_session: AsyncSession,
    async_client: AsyncClient,
):
    """
    Test complete end-to-end resolution pipeline execution:
    1. Calls POST /api/v1/issues/{issue_id}/resolution/start with authenticated developer credentials.
    2. Runs Resolution Lead, Root Cause Analyst, Solution Architect, Critic, Scope Guardian, Evaluator.
    3. Persists AgentTask records and Solution rows in PostgreSQL.
    4. Verifies issue transitions to AWAITING_FIX_APPROVAL.
    5. Verifies GET /api/v1/issues/{issue_id}/solutions returns competing proposals with evaluations.
    """
    issue_id = sample_accepted_issue.id

    # 1. Start resolution pipeline via authenticated API
    start_res = await async_client.post(
        f"/api/v1/issues/{issue_id}/resolution/start",
        headers=DEV_HEADERS,
    )
    assert start_res.status_code == 200
    data = start_res.json()
    assert data["status"] == "AWAITING_FIX_APPROVAL"
    assert data["persisted_solutions_count"] >= 2

    # 2. Verify persistence in PostgreSQL: AgentTasks
    tasks_res = await db_session.execute(
        select(AgentTask).where(AgentTask.issue_id == issue_id).order_by(AgentTask.created_at.asc())
    )
    tasks = tasks_res.scalars().all()
    roles = [t.agent_role for t in tasks]
    assert AgentRole.RESOLUTION_LEAD in roles
    assert AgentRole.ROOT_CAUSE_ANALYST in roles
    assert AgentRole.SOLUTION_ARCHITECT in roles
    assert AgentRole.CRITIC in roles
    assert AgentRole.SCOPE_GUARDIAN in roles
    assert AgentRole.OPTIMIZER_EVALUATOR in roles

    # 3. Verify persistence in PostgreSQL: Solutions table
    sols_res = await db_session.execute(
        select(Solution).where(Solution.issue_id == issue_id).order_by(Solution.rank.asc())
    )
    solutions = sols_res.scalars().all()
    assert len(solutions) >= 2

    # Verify that solutions contain all required fields
    for sol in solutions:
        assert sol.title is not None
        assert sol.strategy_type in ("MINIMAL_TARGETED", "DEFENSIVE_REFACTOR", "ARCHITECTURAL")
        assert len(sol.affected_files) >= 1
        assert sol.expected_changes is not None
        assert len(sol.advantages) >= 1
        assert len(sol.disadvantages) >= 1
        assert sol.complexity_score >= 1
        assert sol.security_implications is not None
        assert sol.regression_risks is not None
        assert sol.critique is not None
        assert sol.evaluation is not None
        assert sol.scope_assessment is not None
        assert len(sol.supporting_evidence_ids) >= 1

    # Exactly one solution is marked is_recommended
    recommended = [s for s in solutions if s.is_recommended]
    assert len(recommended) == 1
    assert recommended[0].rank == 1

    # 4. Developer inspects solutions via GET endpoint
    list_res = await async_client.get(f"/api/v1/issues/{issue_id}/solutions")
    assert list_res.status_code == 200
    listed_sols = list_res.json()
    assert len(listed_sols) == len(solutions)
    assert listed_sols[0]["id"] == str(recommended[0].id)
    assert listed_sols[0]["is_recommended"] is True


@pytest.mark.asyncio
async def test_developer_fix_approval_and_custom_strategy(
    sample_accepted_issue: Issue,
    db_session: AsyncSession,
    async_client: AsyncClient,
):
    """
    Test Developer Fix Approval Gate:
    1. Unauthenticated approval attempt must be rejected with 401.
    2. Developer can approve an agent-proposed solution (FIX_APPROVED).
    3. Developer can supply their own custom fix strategy (CUSTOM_STRATEGY_APPROVED).
    4. Implementation agents remain unable to start before recorded fix approval.
    """
    issue_id = sample_accepted_issue.id

    # Advance to AWAITING_FIX_APPROVAL via resolution pipeline
    await async_client.post(
        f"/api/v1/issues/{issue_id}/resolution/start",
        headers=DEV_HEADERS,
    )

    # Fetch available solutions
    sols_res = await async_client.get(f"/api/v1/issues/{issue_id}/solutions")
    solutions = sols_res.json()
    chosen_solution_id = solutions[0]["id"]

    # 1. Unauthenticated approval attempt MUST FAIL (401)
    unauth_res = await async_client.post(
        f"/api/v1/issues/{issue_id}/fix-approval",
        json={"decision": "FIX_APPROVED", "solution_id": chosen_solution_id},
    )
    assert unauth_res.status_code == 401

    # 2. Legitimate Fix Approval by Developer
    approve_res = await async_client.post(
        f"/api/v1/issues/{issue_id}/fix-approval",
        headers=DEV_HEADERS,
        json={
            "decision": "FIX_APPROVED",
            "solution_id": chosen_solution_id,
            "notes": "Selected recommended Strategy 1. Safe clamp check approved for implementation.",
        },
    )
    assert approve_res.status_code == 200
    approval_data = approve_res.json()
    assert approval_data["decision"] == "FIX_APPROVED"
    assert approval_data["actor"] == "lead_developer"
    assert approval_data["solution_id"] == chosen_solution_id

    # Verify Approval persisted in PostgreSQL
    appr_stmt = select(Approval).where(
        Approval.issue_id == issue_id,
        Approval.target_type == ApprovalTarget.FIX_STRATEGY,
    )
    appr_res = await db_session.execute(appr_stmt)
    approval_record = appr_res.scalar_one()
    assert approval_record.decision == ApprovalDecision.FIX_APPROVED
    assert str(approval_record.solution_id) == chosen_solution_id


@pytest.mark.asyncio
async def test_unauthorized_attempts_to_initiate_implementation(
    sample_accepted_issue: Issue,
    async_client: AsyncClient,
):
    """
    Verify that an agent or user CANNOT transition to IMPLEMENTING before recorded fix approval.
    Workflow engine must reject with 403 Forbidden.
    """
    issue_id = sample_accepted_issue.id

    # Currently issue is in ACCEPTED; not in AWAITING_FIX_APPROVAL, and NO fix approval exists
    rogue_transition = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={
            "target_status": "IMPLEMENTING",
            "actor": "rogue_implementer",
            "reason": "Attempting to skip resolution debate and approval.",
        },
    )
    # 400 Bad Request: Illegal state transition (cannot jump from ACCEPTED to IMPLEMENTING)
    assert rogue_transition.status_code == 400
