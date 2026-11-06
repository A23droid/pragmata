import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.models.entities import (
    AgentTask,
    ConversationReference,
    Evidence,
    Investigation,
    Issue,
    Project,
)
from backend.app.models.enums import (
    AgentRole,
    ChannelType,
    EvidenceType,
    InvestigationOutcome,
    IssueStatus,
    ProvenanceType,
    TaskStatus,
)
from backend.app.schemas.switch import SwitchMessagePayload
from backend.app.services.agents.roles import (
    EvidenceCitation,
    EvidenceValidationResult,
    IntakeAnalysisResult,
    InvestigationLeadReport,
    InvestigatorResult,
    ReproducerPlan,
)
from backend.app.services.agents.runner import agent_runner
from backend.app.services.repository.inspector import RepoInspector
from backend.app.services.repository.workspace import ManagedWorkspace
from backend.app.services.sandbox.docker_runner import (
    CommandSecurityViolation,
    DockerSandbox,
    SandboxResult,
)
from backend.app.services.switch_adapter import switch_adapter
from backend.app.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


def wrap_untrusted(tag: str, content: str) -> str:
    """Safely format untrusted repository/user text inside strict containment tags."""
    sanitized = content.replace(f"</{tag}>", f"<\\[ESCAPED_END_{tag}\\]>")
    return f"<{tag}>\n{sanitized}\n</{tag}>"


class InvestigationCoordinator:
    """
    Hierarchical Investigation Coordinator managed by the Investigation Lead.
    Coordinates Intake Agent, Investigator, Reproducer, and Evidence Validator.
    Enforces read-only repository access, Docker sandbox execution, concrete evidence citations,
    PostgreSQL persistence, and Switch collaboration reporting.
    """

    def __init__(self, runner=None):
        self.runner = runner or agent_runner

    async def get_issue_and_project(self, db: AsyncSession, issue_id: str) -> Issue:
        stmt = (
            select(Issue)
            .where(Issue.id == issue_id)
            .options(selectinload(Issue.project))
        )
        res = await db.execute(stmt)
        issue = res.scalar_one_or_none()
        if not issue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue '{issue_id}' not found.",
            )
        return issue

    async def get_switch_room_id(self, db: AsyncSession, issue_id: str) -> Optional[str]:
        stmt = select(ConversationReference).where(
            ConversationReference.issue_id == issue_id,
            ConversationReference.channel_type == ChannelType.INVESTIGATION,
        )
        res = await db.execute(stmt)
        ref = res.scalars().first()
        return ref.room_id if ref else None

    async def post_to_room(
        self,
        room_id: Optional[str],
        sender_role: AgentRole,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not room_id:
            return
        try:
            await switch_adapter.send_message(
                SwitchMessagePayload(
                    room_id=room_id,
                    sender_id=sender_role.value.lower().replace("_", "-"),
                    sender_role=sender_role.value,
                    content=content,
                    metadata=metadata or {},
                )
            )
        except Exception as ex:
            logger.warning(f"Could not dispatch Switch message to room {room_id}: {ex}")

    async def run_investigation(
        self,
        db: AsyncSession,
        issue_id: str,
        timeout_per_agent: float = 30.0,
    ) -> InvestigationLeadReport:
        """
        Executes the full Phase 6 investigation workflow.
        Guarantees:
          - Read-only inspection of the repository
          - Execution strictly bounded inside DockerSandbox
          - Verification that REPRODUCED is only assigned if execution confirmed failure
          - Full evidence and task persistence in PostgreSQL
          - Switch progress updates
          - Developer triage handoff (Lead never accepts or rejects)
        """
        issue = await self.get_issue_and_project(db, issue_id)
        project: Project = issue.project
        room_id = await self.get_switch_room_id(db, issue_id)
        evidence_ids: List[str] = []

        # 0. Start Lead coordination
        lead_task = AgentTask(
            issue_id=issue_id,
            agent_role=AgentRole.INVESTIGATION_LEAD,
            status=TaskStatus.RUNNING,
            task_input={"issue_title": issue.title, "project_repo": project.repo_url},
            timeout_seconds=int(timeout_per_agent * 5),
            max_retries=1,
        )
        db.add(lead_task)
        await db.commit()
        await db.refresh(lead_task)

        # Transition workflow to INVESTIGATING
        try:
            await WorkflowEngine.transition_issue(
                db=db,
                issue_id=issue_id,
                target_status=IssueStatus.INVESTIGATING,
                actor="investigation_lead",
                reason="Starting multi-agent investigation and reproduction workflow.",
            )
        except Exception as ex:
            logger.info(f"Issue {issue_id} state transition to INVESTIGATING note: {ex}")

        await self.post_to_room(
            room_id,
            AgentRole.INVESTIGATION_LEAD,
            f"**[Investigation Lead]** Initiating investigation for issue **{issue_id}**: *\"{issue.title}\"* against repository `{project.repo_url}`.",
        )

        # 1. Intake Agent Phase
        intake_prompt = (
            f"Please structure this incoming user bug report:\n"
            f"{wrap_untrusted('bug_title', issue.title)}\n"
            f"{wrap_untrusted('bug_description', issue.description)}\n"
            f"{wrap_untrusted('expected_behavior', issue.expected_behavior or 'Not provided')}\n"
            f"{wrap_untrusted('steps_attempted', issue.steps_attempted or 'Not provided')}\n"
            f"{wrap_untrusted('reporter_environment', str(issue.reporter_environment or {}))}\n"
            "Identify expected vs actual behaviour. Determine if critical context is missing."
        )

        intake_result: IntakeAnalysisResult = await self.runner.execute_task(
            role=AgentRole.INTAKE_AGENT,
            schema=IntakeAnalysisResult,
            prompt=intake_prompt,
            issue_id=issue_id,
            switch_room_id=room_id,
            db=db,
            parent_task_id=lead_task.id,
            timeout_seconds=timeout_per_agent,
        )

        # Handle missing information early exit
        if intake_result.missing_context and len(intake_result.clarification_questions) > 0:
            summary = (
                f"Intake Agent identified missing critical information. "
                f"Questions for reporter: {'; '.join(intake_result.clarification_questions)}"
            )
            inv = Investigation(
                issue_id=issue_id,
                outcome=InvestigationOutcome.NEEDS_INFORMATION,
                summary=summary,
                attempts_count=1,
                environment_details={"stage": "intake_incomplete"},
            )
            db.add(inv)

            try:
                await WorkflowEngine.transition_issue(
                    db=db,
                    issue_id=issue_id,
                    target_status=IssueStatus.NEEDS_INFORMATION,
                    actor="investigation_lead",
                    reason="Incomplete bug report missing required context to reproduce.",
                )
            except Exception as e:
                logger.warning(f"Could not transition issue to NEEDS_INFORMATION: {e}")

            lead_task.status = TaskStatus.COMPLETED
            lead_task.task_output = {"outcome": InvestigationOutcome.NEEDS_INFORMATION.value, "summary": summary}
            await db.commit()

            await self.post_to_room(
                room_id,
                AgentRole.INVESTIGATION_LEAD,
                f"**[Investigation Lead]** Investigation halted: Missing critical information.\n"
                + "\n".join(f"- {q}" for q in intake_result.clarification_questions),
            )

            return InvestigationLeadReport(
                issue_id=issue_id,
                outcome=InvestigationOutcome.NEEDS_INFORMATION,
                summary=summary,
                structured_report=intake_result,
                triage_recommendation="Request clarification from reporter before proceeding with reproduction.",
                next_step="Awaiting reporter clarification.",
            )

        # 2. Workspace Setup & Base Commit Recording
        ws = ManagedWorkspace(
            repo_url=project.repo_url,
            branch_or_commit=project.default_branch,
        )

        base_commit_sha = "unknown"
        try:
            base_commit_sha = await ws.setup()
        except Exception as clone_err:
            summary = f"Failed to clone repository '{project.repo_url}': {str(clone_err)}"
            logger.error(summary)
            inv = Investigation(
                issue_id=issue_id,
                outcome=InvestigationOutcome.BLOCKED,
                summary=summary,
                attempts_count=1,
                environment_details={"stage": "clone_failed", "error": str(clone_err)},
            )
            db.add(inv)

            try:
                await WorkflowEngine.transition_issue(
                    db=db,
                    issue_id=issue_id,
                    target_status=IssueStatus.VERIFICATION_BLOCKED,
                    actor="investigation_lead",
                    reason=summary,
                )
            except Exception:
                pass

            lead_task.status = TaskStatus.FAILED
            lead_task.error_message = summary
            await db.commit()
            await ws.cleanup()

            await self.post_to_room(
                room_id,
                AgentRole.INVESTIGATION_LEAD,
                f"**[Investigation Lead]** Investigation BLOCKED: Could not clone repository `{project.repo_url}`.",
            )

            return InvestigationLeadReport(
                issue_id=issue_id,
                outcome=InvestigationOutcome.BLOCKED,
                summary=summary,
                structured_report=intake_result,
                triage_recommendation="Check repository URL and GitHub credentials.",
                next_step="Blocked at repository setup.",
            )

        investigation_record = Investigation(
            issue_id=issue_id,
            commit_sha=base_commit_sha,
            outcome=InvestigationOutcome.PENDING,
            attempts_count=1,
            environment_details={
                "repo_url": project.repo_url,
                "branch": project.default_branch,
                "commit_sha": base_commit_sha,
            },
        )
        db.add(investigation_record)
        await db.flush()

        try:
            # 3. Investigator Phase (Read-Only Repository Exploration)
            inspector = RepoInspector(ws.path)
            summary_info = inspector.summarize()

            # Search keywords from title/summary
            search_query = intake_result.title.split()[0] if intake_result.title else None
            search_matches = []
            if search_query:
                try:
                    search_matches = inspector.search_code(query=search_query, max_matches=5)
                except Exception:
                    search_matches = []

            # Format untrusted repository overview
            file_tree_snippet = [f["path"] for f in summary_info.file_tree[:30]]
            search_preview = [f"{m.file_path}:{m.line_number}: {m.line_content}" for m in search_matches]

            investigator_prompt = (
                f"Examine the repository structure for this structured issue:\n"
                f"Title: {intake_result.title}\n"
                f"Expected: {intake_result.expected_behaviour}\n"
                f"Actual: {intake_result.actual_behaviour}\n\n"
                f"{wrap_untrusted('detected_languages', ', '.join(summary_info.detected_languages))}\n"
                f"{wrap_untrusted('detected_frameworks', ', '.join(summary_info.detected_frameworks))}\n"
                f"{wrap_untrusted('test_commands', ', '.join(summary_info.test_commands))}\n"
                f"{wrap_untrusted('file_tree_sample', str(file_tree_snippet))}\n"
                f"{wrap_untrusted('code_search_matches', str(search_preview))}\n\n"
                "Identify relevant files and symbols. Provide concrete citations. "
                "Explicitly separate any suspected root cause hypothesis from verified reproduction."
            )

            investigator_result: InvestigatorResult = await self.runner.execute_task(
                role=AgentRole.INVESTIGATOR,
                schema=InvestigatorResult,
                prompt=investigator_prompt,
                issue_id=issue_id,
                switch_room_id=room_id,
                db=db,
                parent_task_id=lead_task.id,
                timeout_seconds=timeout_per_agent,
            )

            # Persist Investigator file citations as concrete Evidence
            for cit in investigator_result.citations:
                ev_cit = Evidence(
                    issue_id=issue_id,
                    investigation_id=investigation_record.id,
                    evidence_type=EvidenceType.FILE_REFERENCE,
                    content=f"{cit.relevance_note}\nSnippet: {cit.snippet or 'N/A'}",
                    file_path=cit.file_path,
                    line_start=cit.line_start,
                    line_end=cit.line_end,
                    provenance=ProvenanceType.AGENT,
                )
                db.add(ev_cit)
                await db.flush()
                evidence_ids.append(str(ev_cit.id))

            # 4. Reproducer Phase (Minimal Reproduction Plan & Docker Execution)
            try:
                await WorkflowEngine.transition_issue(
                    db=db,
                    issue_id=issue_id,
                    target_status=IssueStatus.REPRODUCING,
                    actor="investigation_lead",
                    reason="Delegating minimal reproduction procedure to Reproducer.",
                )
            except Exception:
                pass

            reproducer_prompt = (
                f"Develop a minimal reproduction command for this issue:\n"
                f"Report: {intake_result.summary}\n"
                f"Relevant files: {', '.join(investigator_result.relevant_files)}\n"
                f"Test commands found in repo: {', '.join(summary_info.test_commands)}\n"
                "The command will execute inside an isolated read-only Docker container. "
                "Specify the command and expected failure pattern."
            )

            reproducer_plan: ReproducerPlan = await self.runner.execute_task(
                role=AgentRole.REPRODUCER,
                schema=ReproducerPlan,
                prompt=reproducer_prompt,
                issue_id=issue_id,
                switch_room_id=room_id,
                db=db,
                parent_task_id=lead_task.id,
                timeout_seconds=timeout_per_agent,
            )

            # 5. Execute Reproduction in Isolated Docker Sandbox (Strict Read-Only)
            sandbox = DockerSandbox(
                workspace_path=ws.path,
                image=settings.SANDBOX_DEFAULT_IMAGE,
                timeout_seconds=int(timeout_per_agent),
                network_enabled=False,
                read_only_workspace=True,  # STRICT READ-ONLY MOUNT: no modifying code in Phase 6!
            )

            sandbox_result: Optional[SandboxResult] = None
            security_violation: Optional[str] = None
            try:
                sandbox_result = await sandbox.run_command(reproducer_plan.command_to_run)
            except CommandSecurityViolation as csv:
                security_violation = str(csv)
                logger.warning(f"Sandbox security violation in issue {issue_id}: {csv}")
                sandbox_result = SandboxResult(
                    command=reproducer_plan.command_to_run,
                    exit_code=126,
                    stdout="",
                    stderr=f"Security violation: {security_violation}",
                    duration_seconds=0.0,
                    error_message=security_violation,
                )
            except Exception as sex:
                logger.error(f"Sandbox execution error in issue {issue_id}: {sex}")
                sandbox_result = SandboxResult(
                    command=reproducer_plan.command_to_run,
                    exit_code=1,
                    stdout="",
                    stderr=str(sex),
                    duration_seconds=0.0,
                    error_message=str(sex),
                )

            # Persist execution output as concrete Evidence
            full_output = f"COMMAND: {sandbox_result.command}\nEXIT_CODE: {sandbox_result.exit_code}\nSTDOUT:\n{sandbox_result.stdout}\nSTDERR:\n{sandbox_result.stderr}"
            if sandbox_result.error_message:
                full_output += f"\nERROR: {sandbox_result.error_message}"

            ev_exec = Evidence(
                issue_id=issue_id,
                investigation_id=investigation_record.id,
                evidence_type=EvidenceType.REPRODUCTION_OUTPUT,
                content=full_output,
                tool_name="docker_sandbox",
                exit_code=sandbox_result.exit_code,
                provenance=ProvenanceType.TOOL,
            )
            db.add(ev_exec)
            await db.flush()
            evidence_ids.append(str(ev_exec.id))

            await self.post_to_room(
                room_id,
                AgentRole.REPRODUCER,
                f"**[Reproducer]** Sandbox execution finished with exit code `{sandbox_result.exit_code}` in {sandbox_result.duration_seconds}s.",
                metadata={"exit_code": sandbox_result.exit_code, "timed_out": sandbox_result.timed_out},
            )

            # 6. Evidence Validator Phase (Independent Outcome Classification)
            # Evaluate concrete evidence deterministically in Python to prevent LLM hallucinations:
            # An issue can NEVER be classified as REPRODUCED without a concrete failing command
            # matching the expected failure pattern!
            deterministic_outcome = InvestigationOutcome.NOT_REPRODUCED
            is_valid_repro = False
            actual_matches = False
            missing_deps = []

            # Check for security violation / timeout
            if sandbox_result.timed_out:
                deterministic_outcome = InvestigationOutcome.BLOCKED
            elif security_violation:
                deterministic_outcome = InvestigationOutcome.BLOCKED
            # Check for missing dependency / environment requirements
            elif any(
                term in (sandbox_result.stderr + sandbox_result.stdout).lower()
                for term in [
                    "command not found",
                    "module not found",
                    "modulenotfounderror",
                    "nosuchfile",
                    "missing dependency",
                ]
            ) or (
                not reproducer_plan.can_run_offline
                and any(
                    term in (sandbox_result.stderr + sandbox_result.stdout).lower()
                    for term in ["connection refused", "network is unreachable", "could not resolve host"]
                )
            ):
                deterministic_outcome = InvestigationOutcome.ENVIRONMENT_DEPENDENT
                missing_deps.append("Offline sandbox network or missing system runtime/package.")
            elif sandbox_result.exit_code != 0:
                # Failure observed! Check if failure matches expected defect pattern
                exp_pattern = reproducer_plan.expected_failure_pattern.lower().strip()
                combined_output = (sandbox_result.stdout + "\n" + sandbox_result.stderr).lower()

                # Check for command execution errors, missing binary, or syntax errors that aren't the defect
                is_shell_or_syntax_error = any(
                    err in combined_output
                    for err in [
                        "/bin/sh:",
                        "sh: 1:",
                        "command not found",
                        "syntaxerror:",
                        "syntax error",
                        "permission denied",
                        "cannot execute",
                    ]
                ) and (exp_pattern not in combined_output)

                # Invariant: REPRODUCED requires matching actual execution evidence against the specific defect pattern,
                # NOT merely a non-zero exit code or generic terms like 'error' or 'fail'.
                pattern_is_meaningful = len(exp_pattern) >= 4 and exp_pattern not in {"error", "fail", "failed", "test"}
                matches_expected_pattern = pattern_is_meaningful and (exp_pattern in combined_output)

                if is_shell_or_syntax_error:
                    deterministic_outcome = InvestigationOutcome.ENVIRONMENT_DEPENDENT
                    missing_deps.append("Command syntax error or tool unavailable in sandbox.")
                elif matches_expected_pattern:
                    deterministic_outcome = InvestigationOutcome.REPRODUCED
                    is_valid_repro = True
                    actual_matches = True
                else:
                    deterministic_outcome = InvestigationOutcome.NOT_REPRODUCED
            else:
                # Exit code is 0: Test passed, defect NOT reproduced!
                deterministic_outcome = InvestigationOutcome.NOT_REPRODUCED

            validator_prompt = (
                f"Independently validate the reproduction attempt:\n"
                f"Report: {intake_result.summary}\n"
                f"Expected Failure: {reproducer_plan.expected_failure_pattern}\n"
                f"Sandbox Command: {sandbox_result.command}\n"
                f"Exit Code: {sandbox_result.exit_code}\n"
                f"Timed Out: {sandbox_result.timed_out}\n"
                f"{wrap_untrusted('stdout', sandbox_result.stdout[:500])}\n"
                f"{wrap_untrusted('stderr', sandbox_result.stderr[:500])}\n\n"
                "Validate the outcome. Explicitly separate actual reproduction from root cause hypotheses. "
                "Confirm whether execution matched the expected failure."
            )

            val_result: EvidenceValidationResult = await self.runner.execute_task(
                role=AgentRole.EVIDENCE_VALIDATOR,
                schema=EvidenceValidationResult,
                prompt=validator_prompt,
                issue_id=issue_id,
                switch_room_id=room_id,
                db=db,
                parent_task_id=lead_task.id,
                timeout_seconds=timeout_per_agent,
            )

            # Invariant: Code overrides LLM if LLM tries to claim REPRODUCED without actual failure!
            if val_result.outcome == InvestigationOutcome.REPRODUCED and not is_valid_repro:
                logger.warning(
                    f"Evidence Validator LLM claimed REPRODUCED for issue {issue_id}, but execution exit_code was {sandbox_result.exit_code}. Overriding to NOT_REPRODUCED."
                )
                val_result.outcome = deterministic_outcome
                val_result.is_valid_reproduction = False
                val_result.distinction_explanation += (
                    " [Deterministic Rule Applied: Issue cannot be marked REPRODUCED without failing execution evidence.]"
                )
            else:
                val_result.outcome = deterministic_outcome
                val_result.is_valid_reproduction = is_valid_repro
                val_result.actual_failure_matches_expected = actual_matches

            val_result.cited_evidence_ids = evidence_ids
            val_result.missing_context_or_dependencies.extend(missing_deps)

            # 7. Finalization by Investigation Lead
            final_outcome = val_result.outcome
            investigation_record.outcome = final_outcome
            investigation_record.summary = (
                f"Outcome: {final_outcome.value}. "
                f"Reproduction command: `{sandbox_result.command}` (exit {sandbox_result.exit_code}). "
                f"Validation: {val_result.evidence_summary}"
            )
            investigation_record.environment_details = {
                "base_commit_sha": base_commit_sha,
                "sandbox_image": settings.SANDBOX_DEFAULT_IMAGE,
                "read_only_workspace": True,
                "network_enabled": False,
                "exit_code": sandbox_result.exit_code,
                "duration_seconds": sandbox_result.duration_seconds,
            }

            # Update issue status for developer triage:
            # Lead NEVER accepts or rejects! Moves to AWAITING_DEVELOPER_TRIAGE or NEEDS_INFORMATION
            if final_outcome == InvestigationOutcome.REPRODUCED:
                try:
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.REPRODUCED,
                        actor="investigation_lead",
                        reason=f"Reproduction confirmed in sandbox (exit code {sandbox_result.exit_code}).",
                    )
                except Exception as e:
                    logger.warning(f"Workflow transition to REPRODUCED note: {e}")

                try:
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
                        actor="investigation_lead",
                        reason="Bug reproduced with concrete evidence. Ready for developer triage.",
                    )
                except Exception as e:
                    logger.warning(f"Workflow transition to AWAITING_DEVELOPER_TRIAGE note: {e}")

            elif final_outcome == InvestigationOutcome.NOT_REPRODUCED:
                try:
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.NOT_REPRODUCED,
                        actor="investigation_lead",
                        reason=f"Reproduction attempt did not reproduce defect (exit code {sandbox_result.exit_code}).",
                    )
                except Exception as e:
                    logger.warning(f"Workflow transition to NOT_REPRODUCED note: {e}")

                try:
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
                        actor="investigation_lead",
                        reason="Bug not reproduced. Ready for developer triage.",
                    )
                except Exception as e:
                    logger.warning(f"Workflow transition to AWAITING_DEVELOPER_TRIAGE note: {e}")

            elif final_outcome == InvestigationOutcome.NEEDS_INFORMATION:
                try:
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.NEEDS_INFORMATION,
                        actor="investigation_lead",
                        reason="Missing critical information required to investigate.",
                    )
                except Exception as e:
                    logger.warning(f"Workflow transition to NEEDS_INFORMATION note: {e}")

            elif final_outcome == InvestigationOutcome.BLOCKED:
                try:
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.VERIFICATION_BLOCKED,
                        actor="investigation_lead",
                        reason=investigation_record.summary,
                    )
                except Exception as e:
                    logger.warning(f"Workflow transition to VERIFICATION_BLOCKED note: {e}")

            else:  # ENVIRONMENT_DEPENDENT
                try:
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.NOT_REPRODUCED,
                        actor="investigation_lead",
                        reason="Reproduction outcome is environment-dependent or missing dependencies.",
                    )
                    await WorkflowEngine.transition_issue(
                        db=db,
                        issue_id=issue_id,
                        target_status=IssueStatus.AWAITING_DEVELOPER_TRIAGE,
                        actor="investigation_lead",
                        reason="Environment-dependent outcome. Ready for developer triage.",
                    )
                except Exception as e:
                    logger.warning(f"Workflow transition for environment-dependent note: {e}")

            lead_task.status = TaskStatus.COMPLETED
            lead_task.task_output = {
                "outcome": final_outcome.value,
                "base_commit_sha": base_commit_sha,
                "evidence_count": len(evidence_ids),
                "summary": investigation_record.summary,
            }

            await db.commit()

            lead_report_summary = (
                f"**[Investigation Lead] Investigation Complete**\n"
                f"- **Outcome**: `{final_outcome.value}`\n"
                f"- **Base Commit**: `{base_commit_sha}`\n"
                f"- **Reproduction**: {'Confirmed with evidence' if is_valid_repro else 'Not reproduced'}\n"
                f"- **Suspected Root Cause**: {investigator_result.suspected_root_cause_hypothesis or 'Under analysis'}\n"
                f"- **Developer Action**: Issue is now **AWAITING_DEVELOPER_TRIAGE**. Developer can Accept, Reject, Request Information, or Defer."
            )
            await self.post_to_room(room_id, AgentRole.INVESTIGATION_LEAD, lead_report_summary)

            return InvestigationLeadReport(
                issue_id=issue_id,
                outcome=final_outcome,
                summary=investigation_record.summary,
                structured_report=intake_result,
                code_investigation=investigator_result,
                reproduction_plan=reproducer_plan,
                sandbox_execution_performed=True,
                evidence_validation=val_result,
                triage_recommendation="Awaiting developer triage gate. Resolution phase cannot start without explicit developer acceptance.",
                evidence_ids=evidence_ids,
                next_step="AWAITING_DEVELOPER_TRIAGE",
            )

        finally:
            await ws.cleanup()


investigation_coordinator = InvestigationCoordinator()
