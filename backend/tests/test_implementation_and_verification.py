import os
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.app.models.entities import (
    Approval,
    Implementation,
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


@pytest.fixture
def sample_demo_repo_path():
    demo_path = Path("d:/pragmata/pragmata/demo/sample-node-cart").resolve()
    return str(demo_path)


@pytest.mark.asyncio
async def test_implementation_blocked_without_developer_approval():
    """Invariant: Implementation must not start without recorded developer fix approval."""
    service = ImplementerService()
    mock_db = AsyncMock()

    # Issue with NO approvals
    unapproved_issue = Issue(
        id="issue-unapproved-1",
        project_id=uuid.uuid4(),
        title="Cart discount bug",
        description="Fails at 100",
        status=IssueStatus.AWAITING_FIX_APPROVAL,
        approvals=[],
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = unapproved_issue
    mock_db.execute.return_value = mock_res

    with pytest.raises(Exception) as exc_info:
        await service.execute_implementation(
            db=mock_db,
            issue_id="issue-unapproved-1",
            request=ImplementationRequest(developer_token="dev_secret_token"),
        )
    assert "Implementation invariant violated" in str(exc_info.value)


@pytest.mark.asyncio
async def test_implementation_branch_and_patch_application(sample_demo_repo_path):
    """Verify that Implementer creates branch and writes patches strictly to approved files."""
    mock_runner = AsyncMock()
    mock_runner.execute_task.return_value = ImplementationPlanOutput(
        summary="Fix cart discount calculation to check >= 100",
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
                    "    return (s >= 100 && this.discountRate > 0) ? s * (1 - this.discountRate) : s;\n"
                    "  }\n"
                    "}\n"
                    "module.exports = { ShoppingCart };\n"
                ),
                rationale="Changed > 100 to >= 100 to fix boundary condition",
            )
        ],
        commit_message="fix(cart): apply discount on orders of $100 or more",
    )

    service = ImplementerService(runner=mock_runner)
    mock_db = AsyncMock()

    sol_id = uuid.uuid4()
    proj_id = uuid.uuid4()
    project = Project(
        id=proj_id,
        name="Cart Project",
        repo_url=sample_demo_repo_path,
        default_branch="master",
    )
    approved_solution = Solution(
        id=sol_id,
        issue_id="issue-approved-1",
        title="Correct Boundary Comparison",
        description="Change subtotal > 100 to subtotal >= 100",
        rationale="Fixes boundary bug",
        affected_files=["src/cart.js"],
        advantages=["Minimal diff"],
        disadvantages=[],
    )
    approval = Approval(
        id=uuid.uuid4(),
        issue_id="issue-approved-1",
        decision=ApprovalDecision.FIX_APPROVED,
        target_type=ApprovalTarget.FIX_STRATEGY,
        solution_id=sol_id,
        actor="lead_dev",
    )
    issue = Issue(
        id="issue-approved-1",
        project_id=proj_id,
        title="Cart discount bug",
        description="Fails at 100",
        status=IssueStatus.AWAITING_FIX_APPROVAL,
        project=project,
        approvals=[approval],
        investigations=[],
        solutions=[approved_solution],
        implementations=[],
    )

    def mock_execute_side_effect(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt)
        if "FROM issues" in stmt_str:
            mock_result.scalar_one_or_none.return_value = issue
        elif "FROM solutions" in stmt_str:
            mock_result.scalar_one_or_none.return_value = approved_solution
        else:
            mock_result.scalar_one_or_none.return_value = None
            mock_result.scalars.return_value.first.return_value = None
        return mock_result

    mock_db.execute.side_effect = mock_execute_side_effect

    with patch("backend.app.services.workflow_engine.WorkflowEngine.transition_issue", new_callable=AsyncMock) as mock_trans:
        with patch("backend.app.services.switch_adapter.switch_adapter.send_message", new_callable=AsyncMock):
            impl = await service.execute_implementation(
                db=mock_db,
                issue_id="issue-approved-1",
                request=ImplementationRequest(developer_token="dev_secret_token"),
                actor="lead_dev",
            )

    assert impl.status == ImplementationStatus.COMPLETED
    assert "src/cart.js" in impl.changed_files
    assert impl.branch_name.startswith("fix/pragmata-issue-")
    assert len(impl.commit_shas) > 0
    mock_trans.assert_called_once()


@pytest.mark.asyncio
async def test_verification_transitions_to_resolved_when_checks_pass(sample_demo_repo_path):
    """Verify that Verifier runs checks in sandbox and transitions issue to RESOLVED upon passing."""
    service = VerifierService()
    mock_db = AsyncMock()

    proj_id = uuid.uuid4()
    project = Project(
        id=proj_id,
        name="Cart Project",
        repo_url=sample_demo_repo_path,
        default_branch="master",
    )
    impl = Implementation(
        id=uuid.uuid4(),
        issue_id="issue-verify-1",
        branch_name="master",
        base_commit_sha="eb60953",
        changed_files=["src/cart.js"],
        commit_shas=["eb60953"],
        status=ImplementationStatus.COMPLETED,
    )
    issue = Issue(
        id="issue-verify-1",
        project_id=proj_id,
        title="Cart bug",
        status=IssueStatus.IMPLEMENTING,
        project=project,
        implementations=[impl],
        investigations=[],
        verification_runs=[],
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = issue
    mock_db.execute.return_value = mock_res

    # Mock DockerSandbox execution to simulate passing checks
    with patch("backend.app.services.sandbox.docker_runner.DockerSandbox.run_command") as mock_run:
        from backend.app.services.sandbox.docker_runner import SandboxResult
        mock_run.return_value = SandboxResult(
            command="node --test tests/cart.test.js",
            exit_code=0,
            stdout="✔ Cart applies 20% discount on orders of $100 or more (PASS)",
            stderr="",
            duration_seconds=0.5,
            timed_out=False,
        )

        with patch("backend.app.services.workflow_engine.WorkflowEngine.transition_issue", new_callable=AsyncMock) as mock_trans:
            with patch("backend.app.services.switch_adapter.switch_adapter.send_message", new_callable=AsyncMock):
                res = await service.execute_verification(
                    db=mock_db,
                    issue_id="issue-verify-1",
                    request=VerificationRequest(run_test_suite=True),
                )

    assert res.all_passed is True
    assert res.overall_status == VerificationStatus.PASSED
    assert mock_trans.call_count == 2
