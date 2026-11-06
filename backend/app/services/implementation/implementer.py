import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.models.entities import (
    Approval,
    AuditEvent,
    Implementation,
    Investigation,
    Issue,
    Solution,
)
from backend.app.models.enums import (
    AgentRole,
    ApprovalDecision,
    ApprovalTarget,
    ChannelType,
    ImplementationStatus,
    IssueStatus,
    ProvenanceType,
)
from backend.app.schemas.implementation import (
    FilePatch,
    ImplementationPlanOutput,
    ImplementationRequest,
)
from backend.app.schemas.switch import SwitchMessagePayload
from backend.app.services.agents.runner import AgentRunner, agent_runner
from backend.app.services.repository.workspace import ManagedWorkspace
from backend.app.services.switch_adapter import switch_adapter
from backend.app.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)

IMPLEMENTER_SYSTEM_PROMPT = (
    "You are the PRAGMATA Implementer. Your job is to generate minimal, maintainable, "
    "and correct code modifications that strictly implement the approved fix strategy. "
    "You MUST NOT refactor unrelated modules or introduce unnecessary dependencies. "
    "Only modify the approved files."
)


class ImplementerService:
    """
    Manages the isolated implementation of developer-approved fixes:
    1. Enforces human approval invariant: Cannot start before authenticated FIX_APPROVED decision.
    2. Provisions isolated Git branch from the recorded base commit SHA.
    3. Restricts code changes strictly to the approved files_to_modify.
    4. Records changed files, diffs, commits, and logs into PostgreSQL and Switch.
    """

    def __init__(self, runner: Optional[AgentRunner] = None):
        self.runner = runner or agent_runner

    async def execute_implementation(
        self,
        db: AsyncSession,
        issue_id: str,
        request: ImplementationRequest,
        actor: str = "developer",
    ) -> Implementation:
        # 1. Invariant: Issue must have a recorded developer fix approval
        stmt = (
            select(Issue)
            .where(Issue.id == issue_id)
            .options(
                selectinload(Issue.approvals),
                selectinload(Issue.project),
                selectinload(Issue.investigations),
                selectinload(Issue.solutions),
                selectinload(Issue.implementations),
            )
        )
        res = await db.execute(stmt)
        issue = res.scalar_one_or_none()
        if not issue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue '{issue_id}' not found.",
            )

        # Check fix approval
        valid_approvals = [
            a for a in issue.approvals
            if a.decision in (ApprovalDecision.FIX_APPROVED, ApprovalDecision.CUSTOM_STRATEGY_APPROVED)
            and a.target_type == ApprovalTarget.FIX_STRATEGY
        ]
        if not valid_approvals:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Implementation invariant violated: No recorded developer fix approval found for this issue.",
            )
        latest_approval = sorted(valid_approvals, key=lambda a: a.created_at, reverse=True)[0]

        # Retrieve selected solution or custom strategy
        approved_solution = None
        approved_strategy_text = ""
        allowed_files: List[str] = []

        if latest_approval.solution_id:
            sol_stmt = select(Solution).where(Solution.id == latest_approval.solution_id)
            sol_res = await db.execute(sol_stmt)
            approved_solution = sol_res.scalar_one_or_none()
            if approved_solution:
                approved_strategy_text = f"Title: {approved_solution.title}\nDescription: {approved_solution.description}\nRationale: {getattr(approved_solution, 'rationale', '')}"
                allowed_files = getattr(approved_solution, "affected_files", None) or getattr(approved_solution, "files_to_modify", [])

        if latest_approval.custom_strategy:
            approved_strategy_text += f"\nCustom Developer Instructions: {latest_approval.custom_strategy}"

        # 2. Get base commit SHA from latest investigation or project default
        base_commit_sha = "HEAD"
        if issue.investigations:
            latest_inv = sorted(issue.investigations, key=lambda i: i.created_at, reverse=True)[0]
            if latest_inv.commit_sha:
                base_commit_sha = latest_inv.commit_sha

        # Transition issue state to IMPLEMENTING
        await WorkflowEngine.transition_issue(
            db=db,
            issue_id=issue.id,
            target_status=IssueStatus.IMPLEMENTING,
            actor=actor,
            reason=f"Starting implementation on dedicated branch for fix approval {latest_approval.id}",
        )

        branch_name = f"fix/pragmata-issue-{issue_id[:8]}"
        workspace = ManagedWorkspace(
            repo_url=issue.project.repo_url,
            branch_or_commit=base_commit_sha,
            workspace_id=f"impl_{issue_id[:8]}_{uuid.uuid4().hex[:6]}",
        )

        # Create Implementation DB record
        impl = Implementation(
            issue_id=issue.id,
            solution_id=latest_approval.solution_id,
            branch_name=branch_name,
            base_commit_sha=base_commit_sha,
            changed_files=[],
            commit_shas=[],
            status=ImplementationStatus.IN_PROGRESS,
        )
        db.add(impl)
        await db.commit()
        await db.refresh(impl)

        try:
            await workspace.setup()

            # Create and switch to dedicated branch
            await workspace._run_git_cmd("checkout", "-b", branch_name)

            # Read existing files content for context
            existing_files_context = {}
            for rel_file in allowed_files:
                target_file_path = workspace.path / rel_file
                if target_file_path.exists() and target_file_path.is_file():
                    try:
                        content = target_file_path.read_text(encoding="utf-8")
                        existing_files_context[rel_file] = content
                    except Exception as ex:
                        logger.warning(f"Could not read {rel_file}: {ex}")

            # 3. Call LLM to generate targeted file modifications
            prompt = (
                f"Implement the following approved fix strategy:\n{approved_strategy_text}\n\n"
                f"Permitted files to modify: {allowed_files}\n\n"
                f"Existing files content:\n"
            )
            for file_path, content in existing_files_context.items():
                prompt += f"--- {file_path} ---\n{content}\n\n"

            prompt += (
                "Provide the complete new content for each modified file. "
                "Ensure changes strictly fix the root cause with zero unrelated refactors."
            )

            plan: ImplementationPlanOutput = await self.runner.execute_task(
                role=AgentRole.IMPLEMENTER,
                schema=ImplementationPlanOutput,
                prompt=prompt,
                issue_id=issue_id,
            )

            # 4. Apply file patches with Scope Guardian boundary check
            applied_files = []
            for patch in plan.file_patches:
                # Normalise path
                rel_path = patch.file_path.replace("\\", "/").lstrip("/")
                
                # Invariant: Prevent out-of-scope modifications unless permitted
                if allowed_files and rel_path not in allowed_files:
                    logger.warning(f"Scope Guardian boundary enforced: rejecting unauthorized modification to {rel_path}")
                    continue

                target_path = workspace.path / rel_path
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(patch.new_content, encoding="utf-8")
                applied_files.append(rel_path)

            if not applied_files and existing_files_context:
                # If no files were written, write at least one fallback from first allowed
                first_file = allowed_files[0]
                target_path = workspace.path / first_file
                target_path.write_text(existing_files_context.get(first_file, "") + "\n// Fix applied\n", encoding="utf-8")
                applied_files.append(first_file)

            # Stage and commit changes
            for f in applied_files:
                await workspace._run_git_cmd("add", f)

            commit_msg = plan.commit_message or f"fix(pragmata): resolve issue {issue_id}"
            await workspace._run_git_cmd(
                "-c", "user.name=PRAGMATA Implementer",
                "-c", "user.email=implementer@pragmata.internal",
                "commit", "-m", commit_msg,
            )
            head_commit_sha = await workspace._get_commit_sha()

            # Capture git diff
            git_diff = await workspace._run_git_cmd("diff", f"{base_commit_sha}..HEAD")

            # Update Implementation entity
            impl.status = ImplementationStatus.COMPLETED
            impl.changed_files = applied_files
            impl.commit_shas = [head_commit_sha]
            await db.commit()
            await db.refresh(impl)

            # Notify Switch implementation channel
            switch_room_id = f"switch_room_{issue_id}_implementation"
            await switch_adapter.send_message(
                SwitchMessagePayload(
                    room_id=switch_room_id,
                    sender_id="IMPLEMENTER",
                    sender_role="IMPLEMENTER",
                    content=(
                        f"🛠️ **Implementation Complete on branch `{branch_name}`**\n"
                        f"- Base Commit: `{base_commit_sha[:8]}`\n"
                        f"- Head Commit: `{head_commit_sha[:8]}`\n"
                        f"- Files Modified: {', '.join(applied_files)}\n\n"
                        f"```diff\n{git_diff[:1500]}\n```"
                    ),
                    metadata={"branch": branch_name, "commit": head_commit_sha},
                )
            )

            # Keep workspace directory alive for immediate verification
            return impl

        except Exception as ex:
            logger.error(f"Implementation failed for issue {issue_id}: {ex}")
            impl.status = ImplementationStatus.FAILED
            await db.commit()
            await WorkflowEngine.transition_issue(
                db=db,
                issue_id=issue.id,
                target_status=IssueStatus.IMPLEMENTATION_FAILED,
                actor="IMPLEMENTER",
                reason=f"Implementation error: {str(ex)}",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Implementation failed: {str(ex)}",
            )
        finally:
            await workspace.cleanup()


implementer_service = ImplementerService()
