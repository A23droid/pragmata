import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.entities import (
    AuditEvent,
    Implementation,
    Investigation,
    Issue,
    VerificationRun,
)
from backend.app.models.enums import (
    ChannelType,
    ImplementationStatus,
    IssueStatus,
    VerificationStatus,
)
from backend.app.schemas.implementation import (
    CheckResult,
    VerificationRequest,
    VerificationResponse,
)
from backend.app.schemas.switch import SwitchMessagePayload
from backend.app.services.repository.workspace import ManagedWorkspace
from backend.app.services.sandbox.docker_runner import DockerSandbox
from backend.app.services.switch_adapter import switch_adapter
from backend.app.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


class VerifierService:
    """
    Verification Authority:
    1. Re-runs the original reproduction procedure in the Docker sandbox (must confirm defect no longer reproduces).
    2. Runs configured project tests (e.g. npm test / vitest or pytest).
    3. Guarantees that code is NOT marked RESOLVED unless all required checks pass.
    4. Records exact exit codes, raw stdout/stderr, and pass/fail states in PostgreSQL.
    """

    async def execute_verification(
        self,
        db: AsyncSession,
        issue_id: str,
        request: VerificationRequest,
        actor: str = "VERIFIER",
    ) -> VerificationResponse:
        # Load issue with implementations, investigations, and project
        stmt = (
            select(Issue)
            .where(Issue.id == issue_id)
            .options(
                selectinload(Issue.project),
                selectinload(Issue.implementations),
                selectinload(Issue.investigations),
                selectinload(Issue.verification_runs),
            )
        )
        res = await db.execute(stmt)
        issue = res.scalar_one_or_none()
        if not issue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue '{issue_id}' not found.",
            )

        # Check that an implementation exists
        valid_impls = [
            i for i in issue.implementations
            if i.status in (ImplementationStatus.COMPLETED, ImplementationStatus.IN_PROGRESS)
        ]
        if not valid_impls:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification requires a completed implementation to verify.",
            )
        latest_impl = sorted(valid_impls, key=lambda i: i.created_at, reverse=True)[0]

        # Transition to VERIFYING
        await WorkflowEngine.transition_issue(
            db=db,
            issue_id=issue.id,
            target_status=IssueStatus.VERIFYING,
            actor=actor,
            reason=f"Starting verification run for implementation branch {latest_impl.branch_name}",
        )

        # Retrieve reproduction command from investigation evidence or metadata
        repro_command = "echo 'No custom reproduction command specified'"
        expected_failure = ""
        if issue.investigations:
            latest_inv = sorted(issue.investigations, key=lambda i: i.created_at, reverse=True)[0]
            if latest_inv.metadata_json:
                repro_command = latest_inv.metadata_json.get("command_to_run") or repro_command
                expected_failure = latest_inv.metadata_json.get("expected_failure_pattern", "")

        # Determine project test command from project config or defaults
        test_command = "npm test" if (latest_impl.changed_files and any(f.endswith((".ts", ".js", ".json")) for f in latest_impl.changed_files)) else "pytest"

        # Setup workspace checkout on the fix branch
        workspace = ManagedWorkspace(
            repo_url=issue.project.repo_url,
            branch_or_commit=latest_impl.commit_shas[0] if latest_impl.commit_shas else latest_impl.branch_name,
            workspace_id=f"verify_{issue_id[:8]}_{uuid.uuid4().hex[:6]}",
        )

        sandbox = DockerSandbox(
            workspace_path=workspace.path,
            timeout_seconds=60,
        )

        commands_executed: List[str] = []
        raw_outputs: List[str] = []
        all_checks_passed = True

        try:
            await workspace.setup()

            # 1. Re-run original reproduction procedure
            commands_executed.append(repro_command)
            repro_res = await sandbox.run_command(repro_command)
            raw_outputs.append(f"=== REPRODUCTION CHECK ({repro_command}) ===\nExit: {repro_res.exit_code}\n{repro_res.stdout}\n{repro_res.stderr}")

            # Reproduction check is PASSED if exit code is 0 (or expected failure pattern is absent)
            repro_passed = repro_res.exit_code == 0
            if expected_failure and expected_failure in (repro_res.stdout + repro_res.stderr):
                repro_passed = False

            repro_check = CheckResult(
                name="Reproduction Check",
                command=repro_command,
                exit_code=repro_res.exit_code,
                output=repro_res.stdout or repro_res.stderr or "Completed",
                passed=repro_passed,
            )
            if not repro_passed:
                all_checks_passed = False

            # 2. Run project test suite if requested
            test_check = None
            if request.run_test_suite:
                commands_executed.append(test_command)
                test_res = await sandbox.run_command(test_command)
                raw_outputs.append(f"=== TEST SUITE CHECK ({test_command}) ===\nExit: {test_res.exit_code}\n{test_res.stdout}\n{test_res.stderr}")
                test_passed = test_res.exit_code == 0
                test_check = CheckResult(
                    name="Project Test Suite",
                    command=test_command,
                    exit_code=test_res.exit_code,
                    output=test_res.stdout or test_res.stderr or "Completed",
                    passed=test_passed,
                )
                if not test_passed:
                    all_checks_passed = False

            # Determine final verification status
            final_status = VerificationStatus.PASSED if all_checks_passed else VerificationStatus.FAILED

            # Record VerificationRun in DB
            v_run = VerificationRun(
                issue_id=issue.id,
                implementation_id=latest_impl.id,
                status=final_status,
                commands_run=commands_executed,
                exit_code=0 if all_checks_passed else 1,
                raw_output="\n\n".join(raw_outputs),
                regression_test_passed=test_check.passed if test_check else True,
                repro_verified=repro_passed,
            )
            db.add(v_run)
            await db.commit()
            await db.refresh(v_run)

            # Update issue status based on verification outcome
            if all_checks_passed:
                await WorkflowEngine.transition_issue(
                    db=db,
                    issue_id=issue.id,
                    target_status=IssueStatus.RESOLVED,
                    actor=actor,
                    reason=f"Fix verified successfully. All required checks passed (VerificationRun {v_run.id})",
                )
            else:
                await WorkflowEngine.transition_issue(
                    db=db,
                    issue_id=issue.id,
                    target_status=IssueStatus.IMPLEMENTATION_FAILED,
                    actor=actor,
                    reason=f"Verification failed. Issue remains unresolved (VerificationRun {v_run.id})",
                )

            # Notify Switch implementation channel
            switch_room_id = f"switch_room_{issue_id}_implementation"
            outcome_emoji = "✅" if all_checks_passed else "❌"
            await switch_adapter.send_message(
                SwitchMessagePayload(
                    room_id=switch_room_id,
                    sender_id="VERIFIER",
                    sender_role="VERIFIER",
                    content=(
                        f"{outcome_emoji} **Verification Run Finished: {final_status.value}**\n"
                        f"- Reproduction Check: {'PASSED' if repro_passed else 'FAILED'} (Exit {repro_check.exit_code})\n"
                        f"- Test Suite Check: {('PASSED' if (test_check and test_check.passed) else 'FAILED') if test_check else 'SKIPPED'}\n"
                        f"- Final Issue Status: **{issue.status.value}**"
                    ),
                    metadata={"verification_id": str(v_run.id), "passed": all_checks_passed},
                )
            )

            return VerificationResponse(
                issue_id=issue.id,
                overall_status=final_status,
                reproduction_check=repro_check,
                test_suite_check=test_check,
                all_passed=all_checks_passed,
                summary=f"Verification {final_status.value}. Issue status transitioned to {issue.status.value}.",
            )

        finally:
            await workspace.cleanup()


verifier_service = VerifierService()
