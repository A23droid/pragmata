import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.app.models.entities import (
    Approval,
    Implementation,
    Investigation,
    Issue,
    Project,
    Solution,
    VerificationRun,
)
from backend.app.models.enums import (
    ApprovalDecision,
    ApprovalTarget,
    ImplementationStatus,
    IssueStatus,
    VerificationStatus,
)
from backend.app.schemas.implementation import (
    FilePatch,
    ImplementationPlanOutput,
    ImplementationRequest,
    VerificationRequest,
)
from backend.app.services.implementation.implementer import ImplementerService
from backend.app.services.verification.verifier import VerifierService
from backend.app.services.workflow_engine import WorkflowEngine


@pytest.fixture
def demo_cart_repo_path():
    p = Path("d:/pragmata/pragmata/demo/sample-node-cart").resolve()
    return str(p)


@pytest.mark.asyncio
async def test_end_to_end_hackathon_demo_pipeline(demo_cart_repo_path):
    """
    Complete Phase 9 Hackathon Demonstration Scenario:
    1. Consumer submits unstructured bug report: 'Coupon SAVE20 does not work on $100 cart'.
    2. Workflow state starts at RECEIVED.
    3. Investigation reproduces the bug in the sandbox (100 !== 80).
    4. Developer Triage Gate: Resolution cannot start without acceptance.
    5. Developer accepts the issue.
    6. Multi-agent debate produces fix strategies under Scope Guardian.
    7. Developer approves fix strategy.
    8. Negative path: Unapproved code modification is blocked.
    9. Implementer creates isolated branch and modifies src/cart.js.
    10. Verifier re-runs reproduction check and tests; fix confirmed.
    11. Issue transitions to RESOLVED.
    """
    mock_db = AsyncMock()

    proj_id = uuid.uuid4()
    project = Project(
        id=proj_id,
        name="Shopping Cart Demo",
        repo_url=demo_cart_repo_path,
        default_branch="master",
    )

    issue_id = "demo-issue-100"
    issue = Issue(
        id=issue_id,
        project_id=proj_id,
        title="Coupon SAVE20 does not work on my $100 cart",
        description="I applied the promo code SAVE20 for orders of $100 or more, but my $100 cart still charged me $100 instead of $80.",
        status=IssueStatus.RECEIVED,
        project=project,
        approvals=[],
        investigations=[],
        solutions=[],
        implementations=[],
        verification_runs=[],
    )

    # 1. Verify Workflow transitions to INVESTIGATING
    allowed_from_received = WorkflowEngine.can_transition(IssueStatus.RECEIVED, IssueStatus.INVESTIGATING)
    assert allowed_from_received is True

    # 2. Reproduction in sandbox reveals the bug
    from backend.app.services.sandbox.docker_runner import DockerSandbox
    sandbox = DockerSandbox(workspace_path=Path(demo_cart_repo_path), timeout_seconds=30)
    repro_result = await sandbox.run_command("node --test tests/cart.test.js")
    
    # Confirms reproduction failure: 100 !== 80 (AssertionError)
    assert repro_result.exit_code != 0
    assert "100 !== 80" in (repro_result.stdout + repro_result.stderr)

    # 3. Negative Path Check: Resolution hierarchy CANNOT start while awaiting triage
    issue.status = IssueStatus.AWAITING_DEVELOPER_TRIAGE
    assert WorkflowEngine.can_transition(IssueStatus.AWAITING_DEVELOPER_TRIAGE, IssueStatus.ROOT_CAUSE_ANALYSIS) is False

    # 4. Developer Triage Gate: Human developer accepts the issue
    assert WorkflowEngine.can_transition(IssueStatus.AWAITING_DEVELOPER_TRIAGE, IssueStatus.ACCEPTED) is True
    issue.status = IssueStatus.ACCEPTED
    triage_approval = Approval(
        id=uuid.uuid4(),
        issue_id=issue_id,
        decision=ApprovalDecision.ACCEPTED,
        target_type=ApprovalTarget.ISSUE_TRIAGE,
        actor="lead_developer",
        notes="Bug verified with reproduction output 100 !== 80",
    )
    issue.approvals.append(triage_approval)

    # 5. Resolution & Fix Strategy Debate
    sol_id = uuid.uuid4()
    solution = Solution(
        id=sol_id,
        issue_id=issue_id,
        title="Correct Boundary Comparison in ShoppingCart.getTotal()",
        description="Update condition from 'subtotal > 100' to 'subtotal >= 100' so $100 orders qualify.",
        rationale="Fixes boundary defect cleanly with zero impact on other cart methods.",
        affected_files=["src/cart.js"],
        advantages=["One-line fix", "Zero regression risk"],
        disadvantages=[],
        complexity_score=1,
        is_recommended=True,
    )
    issue.solutions.append(solution)
    issue.status = IssueStatus.AWAITING_FIX_APPROVAL

    # 6. Negative Path Check: Implementation CANNOT start before fix approval is recorded
    implementer = ImplementerService()
    mock_db_fail = AsyncMock()
    mock_res_fail = MagicMock()
    mock_res_fail.scalar_one_or_none.return_value = issue
    mock_db_fail.execute.return_value = mock_res_fail

    with pytest.raises(Exception) as exc_info:
        await implementer.execute_implementation(
            db=mock_db_fail,
            issue_id=issue_id,
            request=ImplementationRequest(developer_token="token"),
        )
    assert "Implementation invariant violated" in str(exc_info.value)

    # 7. Developer Fix Approval Gate: Human approves the recommended strategy
    fix_approval = Approval(
        id=uuid.uuid4(),
        issue_id=issue_id,
        decision=ApprovalDecision.FIX_APPROVED,
        target_type=ApprovalTarget.FIX_STRATEGY,
        solution_id=sol_id,
        actor="lead_developer",
        notes="Approved boundary check fix",
    )
    issue.approvals.append(fix_approval)

    # 8. Implementer executes the fix on isolated branch
    mock_runner = AsyncMock()
    mock_runner.execute_task.return_value = ImplementationPlanOutput(
        summary="Update subtotal > 100 to subtotal >= 100",
        file_patches=[
            FilePatch(
                file_path="src/cart.js",
                new_content=(
                    "class ShoppingCart {\n"
                    "  constructor() { this.items = []; this.discountRate = 0.0; }\n"
                    "  addItem(name, price, quantity = 1) { this.items.push({ name, price, quantity }); }\n"
                    "  applyDiscount(code) { if (code === 'SAVE20') this.discountRate = 0.20; }\n"
                    "  getSubtotal() { return this.items.reduce((s, i) => s + i.price * i.quantity, 0); }\n"
                    "  getTotal() {\n"
                    "    const s = this.getSubtotal();\n"
                    "    if (s >= 100 && this.discountRate > 0) return s * (1 - this.discountRate);\n"
                    "    return s;\n"
                    "  }\n"
                    "}\n"
                    "module.exports = { ShoppingCart };\n"
                ),
                rationale="Change boundary check to >= 100",
            )
        ],
        commit_message="fix(cart): apply SAVE20 discount on $100 boundary",
    )

    implementer = ImplementerService(runner=mock_runner)
    mock_db_impl = AsyncMock()

    def mock_db_impl_side_effect(stmt):
        m = MagicMock()
        stmt_str = str(stmt)
        if "FROM issues" in stmt_str:
            m.scalar_one_or_none.return_value = issue
        elif "FROM solutions" in stmt_str:
            m.scalar_one_or_none.return_value = solution
        else:
            m.scalar_one_or_none.return_value = None
        return m

    mock_db_impl.execute.side_effect = mock_db_impl_side_effect

    with patch("backend.app.services.workflow_engine.WorkflowEngine.transition_issue", new_callable=AsyncMock):
        with patch("backend.app.services.switch_adapter.switch_adapter.send_message", new_callable=AsyncMock):
            impl = await implementer.execute_implementation(
                db=mock_db_impl,
                issue_id=issue_id,
                request=ImplementationRequest(developer_token="token"),
                actor="lead_developer",
            )

    assert impl.status == ImplementationStatus.COMPLETED
    assert "src/cart.js" in impl.changed_files
    assert impl.branch_name.startswith("fix/pragmata-issue-")
    issue.implementations.append(impl)

    # 9. Verifier runs reproduction re-check and tests in sandbox
    verifier = VerifierService()
    mock_db_verify = AsyncMock()
    mock_res_verify = MagicMock()
    mock_res_verify.scalar_one_or_none.return_value = issue
    mock_db_verify.execute.return_value = mock_res_verify

    with patch("backend.app.services.sandbox.docker_runner.DockerSandbox.run_command") as mock_sandbox_run:
        from backend.app.services.sandbox.docker_runner import SandboxResult
        # Both reproduction and test suite return exit code 0 (PASS)
        mock_sandbox_run.return_value = SandboxResult(
            command="node --test tests/cart.test.js",
            exit_code=0,
            stdout="✔ Cart applies 20% discount on orders of $100 or more (PASS)",
            stderr="",
            duration_seconds=0.2,
            timed_out=False,
        )

        with patch("backend.app.services.workflow_engine.WorkflowEngine.transition_issue", new_callable=AsyncMock) as mock_verify_trans:
            with patch("backend.app.services.switch_adapter.switch_adapter.send_message", new_callable=AsyncMock):
                v_res = await verifier.execute_verification(
                    db=mock_db_verify,
                    issue_id=issue_id,
                    request=VerificationRequest(run_test_suite=True),
                )

    # 10. Fix Verified and Issue Resolved
    assert v_res.all_passed is True
    assert v_res.overall_status == VerificationStatus.PASSED
    assert mock_verify_trans.call_count == 2  # VERIFYING -> RESOLVED

