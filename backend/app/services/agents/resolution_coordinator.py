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
    Approval,
    AuditEvent,
    ConversationReference,
    Evidence,
    Investigation,
    Issue,
    Solution,
)
from backend.app.models.enums import (
    AgentRole,
    ApprovalDecision,
    ApprovalTarget,
    ChannelType,
    IssueStatus,
    TaskStatus,
)
from backend.app.schemas.resolution import (
    CriticEvaluation,
    OptimizerEvaluationReport,
    ProposalCritique,
    ProposalScopeAudit,
    RootCauseAnalysisReport,
    ScopeGuardianReport,
    SolutionArchitectProposals,
    SolutionProposal,
)
from backend.app.schemas.switch import (
    SwitchAgentRegistration,
    SwitchHandoff,
    SwitchMessagePayload,
    SwitchRoomCreate,
)
from backend.app.services.agents.rubric_evaluator import RubricEvaluator
from backend.app.services.agents.runner import AgentRunner, agent_runner
from backend.app.services.agents.scope_guardian import ScopeGuardian
from backend.app.services.switch_adapter import switch_adapter
from backend.app.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


class ResolutionCoordinator:
    """
    Coordinates the PRAGMATA Resolution Hierarchy under Resolution Lead supervision:
    1. Root Cause Analyst
    2. Solution Architect (2-3 distinct strategies)
    3. Critic (independent challenges)
    4. Scope Guardian (independent scope & overengineering audit)
    5. Optimizer/Evaluator (explicit documented rubric ranking)

    Guards:
    - Activation requires explicit server-side developer acceptance.
    - Every root cause references supporting evidence.
    - Invariant: Scope Guardian does not suppress justified security/correctness improvements.
    - Bounded debate rounds and token/execution timeouts enforced.
    - Persists all tasks, findings, proposals, critiques, and evaluations in PostgreSQL.
    - Issue transitions to AWAITING_FIX_APPROVAL for developer decision.
    """

    def __init__(self, runner: Optional[AgentRunner] = None):
        self.runner = runner or agent_runner

    async def run_resolution_workflow(
        self,
        db: AsyncSession,
        issue_id: str,
        debate_round: int = 1,
        timeout_per_agent: float = 45.0,
    ) -> Dict[str, Any]:
        """
        Execute full resolution debate and ranking pipeline for an accepted issue.
        """
        # 1. Activation Gate: Issue must be in ACCEPTED status with recorded developer acceptance
        stmt = (
            select(Issue)
            .where(Issue.id == issue_id)
            .options(
                selectinload(Issue.approvals),
                selectinload(Issue.evidence),
                selectinload(Issue.investigations),
            )
        )
        res = await db.execute(stmt)
        issue = res.scalar_one_or_none()
        if not issue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue '{issue_id}' not found.",
            )

        # Enforce activation gate
        has_developer_acceptance = any(
            a.target_type == ApprovalTarget.ISSUE_TRIAGE
            and a.decision == ApprovalDecision.ACCEPTED
            for a in issue.approvals
        )

        valid_resolution_states = {
            IssueStatus.ACCEPTED,
            IssueStatus.ROOT_CAUSE_ANALYSIS,
            IssueStatus.FIX_STRATEGY_DISCUSSION,
            IssueStatus.AWAITING_FIX_APPROVAL,
        }

        if issue.status not in valid_resolution_states or not has_developer_acceptance:
            logger.warning(
                f"Blocked resolution activation attempt on issue {issue_id}: "
                f"Status is '{issue.status.value}', developer acceptance={has_developer_acceptance}."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Resolution agents cannot be activated before explicit authenticated developer acceptance. "
                    f"Current issue status: '{issue.status.value}'."
                ),
            )

        # 2. Provision / retrieve Switch resolution room
        room_id = f"switch_room_{issue_id}_resolution"
        await switch_adapter.create_or_join_room(
            SwitchRoomCreate(
                issue_id=issue_id,
                room_name=f"Resolution-{issue_id}",
                channel_type=ChannelType.RESOLUTION,
                initial_members=[
                    AgentRole.RESOLUTION_LEAD.value,
                    AgentRole.ROOT_CAUSE_ANALYST.value,
                    AgentRole.SOLUTION_ARCHITECT.value,
                    AgentRole.CRITIC.value,
                    AgentRole.SCOPE_GUARDIAN.value,
                    AgentRole.OPTIMIZER_EVALUATOR.value,
                ],
            )
        )

        # 3. Transition to ROOT_CAUSE_ANALYSIS if currently in ACCEPTED
        if issue.status == IssueStatus.ACCEPTED:
            await WorkflowEngine.transition_issue(
                db=db,
                issue_id=issue_id,
                target_status=IssueStatus.ROOT_CAUSE_ANALYSIS,
                actor="resolution_lead",
                reason="Beginning root cause analysis under Resolution Lead.",
            )

        # Root Resolution Lead Agent Task
        lead_task = AgentTask(
            issue_id=issue_id,
            agent_role=AgentRole.RESOLUTION_LEAD,
            status=TaskStatus.RUNNING,
            task_input={"debate_round": debate_round, "status": issue.status.value},
            timeout_seconds=int(timeout_per_agent * 5),
        )
        db.add(lead_task)
        await db.flush()

        await switch_adapter.send_message(
            SwitchMessagePayload(
                room_id=room_id,
                sender_id=AgentRole.RESOLUTION_LEAD.value,
                sender_role=AgentRole.RESOLUTION_LEAD.value,
                content=(
                    f"🚀 **Resolution Pipeline Started (Round {debate_round})**\n"
                    f"Issue: `{issue.title}` ({issue.id})\n"
                    "Developer acceptance confirmed. Assigning root cause investigation."
                ),
            )
        )

        # 4. Step 1: Root Cause Analyst
        # Collect evidence citations from repository and investigation
        evidence_snippets = []
        evidence_ids = []
        for ev in issue.evidence:
            evidence_ids.append(str(ev.id))
            evidence_snippets.append(
                f"- [Evidence {str(ev.id)[:8]}] Type: {ev.evidence_type.value}, "
                f"File: {ev.file_path or 'N/A'}, ExitCode: {ev.exit_code}: {ev.content[:200]}"
            )

        inv_summary = (
            issue.investigations[0].summary
            if issue.investigations
            else "Investigation confirmed defect."
        )

        rca_prompt = (
            f"Perform Root Cause Analysis for Issue: {issue.title}\n"
            f"Description: {issue.description}\n"
            f"Investigation Finding: {inv_summary}\n"
            f"Evidence Items:\n" + ("\n".join(evidence_snippets) if evidence_snippets else "No evidence files recorded.") + "\n\n"
            "Requirements:\n"
            "1. You MUST distinguish verified root causes from unverified hypotheses.\n"
            "2. Every verified root cause MUST reference supporting evidence IDs and exact file paths.\n"
            "3. Identify affected components and the underlying defect type."
        )

        rca_report: RootCauseAnalysisReport = await self.runner.execute_task(
            role=AgentRole.ROOT_CAUSE_ANALYST,
            schema=RootCauseAnalysisReport,
            prompt=rca_prompt,
            issue_id=issue_id,
            switch_room_id=room_id,
            db=db,
            parent_task_id=lead_task.id,
            timeout_seconds=timeout_per_agent,
        )

        # Targeted handoff to Solution Architect
        await switch_adapter.route_handoff(
            SwitchHandoff(
                issue_id=issue_id,
                room_id=room_id,
                from_role=AgentRole.ROOT_CAUSE_ANALYST.value,
                to_role=AgentRole.SOLUTION_ARCHITECT.value,
                task_description="Formulate 2-3 distinct fix strategies addressing verified root cause.",
                payload={"underlying_defect_type": rca_report.underlying_defect_type},
            )
        )

        # 5. Transition to FIX_STRATEGY_DISCUSSION
        await WorkflowEngine.transition_issue(
            db=db,
            issue_id=issue_id,
            target_status=IssueStatus.FIX_STRATEGY_DISCUSSION,
            actor="resolution_lead",
            reason="Root cause identified. Initiating fix strategy discussion.",
        )

        # 6. Step 2: Solution Architect (proposes 2-3 distinct fix strategies)
        arch_prompt = (
            f"Propose 2 to 3 meaningfully different fix strategies for Issue {issue_id}:\n"
            f"Title: {issue.title}\n"
            f"Root Cause: {rca_report.root_cause_summary}\n"
            f"Defect Type: {rca_report.underlying_defect_type}\n"
            f"Verified Causes: {[c.description for c in rca_report.verified_root_causes]}\n"
            f"Affected Components: {rca_report.affected_components}\n\n"
            "Formulate 2 or 3 distinct strategies (e.g., minimal targeted fix, defensive structural refactor, or architectural adaptation).\n"
            "Each proposal MUST include affected files, expected changes, advantages, disadvantages, complexity score (1-5), security implications, and regression risks."
        )

        arch_result: SolutionArchitectProposals = await self.runner.execute_task(
            role=AgentRole.SOLUTION_ARCHITECT,
            schema=SolutionArchitectProposals,
            prompt=arch_prompt,
            issue_id=issue_id,
            switch_room_id=room_id,
            db=db,
            parent_task_id=lead_task.id,
            timeout_seconds=timeout_per_agent,
        )

        # Handoff to Critic
        await switch_adapter.route_handoff(
            SwitchHandoff(
                issue_id=issue_id,
                room_id=room_id,
                from_role=AgentRole.SOLUTION_ARCHITECT.value,
                to_role=AgentRole.CRITIC.value,
                task_description="Independently challenge assumptions and trade-offs of proposed fix strategies.",
            )
        )

        # 7. Step 3: Critic (Independently challenges each proposal)
        critic_prompt = (
            f"Independently critique the {len(arch_result.proposals)} proposed fix strategies for Issue {issue_id}:\n"
            f"Root Cause: {rca_report.root_cause_summary}\n\n"
        )
        for p in arch_result.proposals:
            critic_prompt += (
                f"--- Proposal {p.proposal_id}: {p.title} ({p.strategy_type}) ---\n"
                f"Files: {p.affected_files}\n"
                f"Expected Changes: {p.expected_changes}\n"
                f"Complexity: {p.complexity_score} ({p.complexity_explanation})\n"
                f"Security: {p.security_implications}\n"
                f"Risks: {p.regression_risks}\n\n"
            )
        critic_prompt += (
            "Evaluate each proposal on its own merits rather than merely agreeing with the Architect. "
            "Identify flaws, edge cases, regression risks, and verify whether the root cause is completely addressed."
        )

        critic_result: CriticEvaluation = await self.runner.execute_task(
            role=AgentRole.CRITIC,
            schema=CriticEvaluation,
            prompt=critic_prompt,
            issue_id=issue_id,
            switch_room_id=room_id,
            db=db,
            parent_task_id=lead_task.id,
            timeout_seconds=timeout_per_agent,
        )

        # 8. Step 4: Independent Scope Guardian Audit
        scope_report: ScopeGuardianReport = ScopeGuardian.audit_proposals_and_debate(
            proposals=arch_result.proposals,
            root_cause=rca_report,
            current_debate_round=debate_round,
        )

        # Persist Scope Guardian AgentTask in PostgreSQL
        guardian_task = AgentTask(
            issue_id=issue_id,
            agent_role=AgentRole.SCOPE_GUARDIAN,
            status=TaskStatus.COMPLETED,
            task_input={"proposals_count": len(arch_result.proposals), "round": debate_round},
            task_output=scope_report.model_dump(mode="json"),
            parent_task_id=lead_task.id,
        )
        db.add(guardian_task)
        await db.flush()

        # Post Scope Guardian audit to Switch resolution room
        guardian_msg = (
            f"🛡️ **[SCOPE GUARDIAN AUDIT]** (Independent Review)\n"
            f"Debate Round: {debate_round}/{scope_report.debate_status.max_rounds}\n"
            f"Intervention Required: **{scope_report.intervention_required}**\n"
        )
        for audit in scope_report.proposals_scope_audit:
            guardian_msg += (
                f"- Proposal `{audit.proposal_id}`: **{audit.verdict}** "
                f"(Overengineering: {audit.overengineering_detected}, Justified Expansion: {audit.justified_scope_expansion})\n"
                f"  *Notes*: {audit.justification_notes}\n"
            )
        if scope_report.intervention_required:
            guardian_msg += f"\n⚠️ **ALERT TO ORCHESTRATOR**: {scope_report.intervention_reason}"

        await switch_adapter.send_message(
            SwitchMessagePayload(
                room_id=room_id,
                sender_id=AgentRole.SCOPE_GUARDIAN.value,
                sender_role=AgentRole.SCOPE_GUARDIAN.value,
                content=guardian_msg,
                metadata={"intervention_required": scope_report.intervention_required},
            )
        )

        # Handoff to Optimizer / Evaluator
        await switch_adapter.route_handoff(
            SwitchHandoff(
                issue_id=issue_id,
                room_id=room_id,
                from_role=AgentRole.RESOLUTION_LEAD.value,
                to_role=AgentRole.OPTIMIZER_EVALUATOR.value,
                task_description="Rank competing proposals using documented evaluation rubric.",
            )
        )

        # 9. Step 5: Optimizer / Evaluator (Documented Rubric Ranking)
        eval_report: OptimizerEvaluationReport = RubricEvaluator.evaluate_proposals(
            proposals=arch_result.proposals,
            critiques=critic_result.critiques,
            scope_audits=scope_report.proposals_scope_audit,
            root_cause=rca_report,
        )

        eval_task = AgentTask(
            issue_id=issue_id,
            agent_role=AgentRole.OPTIMIZER_EVALUATOR,
            status=TaskStatus.COMPLETED,
            task_input={"rubric_weights": "Maintainability:25%, Regression:25%, Simplicity:20%, Performance:15%, Edge:15%"},
            task_output=eval_report.model_dump(mode="json"),
            parent_task_id=lead_task.id,
        )
        db.add(eval_task)
        await db.flush()

        # Post evaluation ranking to Switch
        eval_msg = (
            f"📊 **[EVALUATOR RANKING REPORT]**\n"
            f"Top Recommended: **{eval_report.recommended_proposal_id}**\n\n"
        )
        for ep in eval_report.evaluated_proposals:
            rec_badge = " ⭐ **[RECOMMENDED]**" if ep.is_recommended else ""
            eval_msg += (
                f"- **Rank #{ep.rank}**: `{ep.proposal_id}` (Score: {ep.composite_score}/4.00){rec_badge}\n"
                f"  Gates Passed: {ep.hard_gates_passed} | {ep.recommendation_rationale}\n"
            )
        eval_msg += f"\n*Justification*: {eval_report.ranking_justification}"

        await switch_adapter.send_message(
            SwitchMessagePayload(
                room_id=room_id,
                sender_id=AgentRole.OPTIMIZER_EVALUATOR.value,
                sender_role=AgentRole.OPTIMIZER_EVALUATOR.value,
                content=eval_msg,
            )
        )

        # 10. Persist Solutions into PostgreSQL
        eval_map = {ep.proposal_id: ep for ep in eval_report.evaluated_proposals}
        critique_map = {c.proposal_id: c for c in critic_result.critiques}
        scope_map = {s.proposal_id: s for s in scope_report.proposals_scope_audit}

        # Clear any prior solutions for clean round update
        existing_sols_res = await db.execute(select(Solution).where(Solution.issue_id == issue_id))
        for existing in existing_sols_res.scalars().all():
            await db.delete(existing)
        await db.flush()

        persisted_solutions = []
        for prop in arch_result.proposals:
            ep = eval_map.get(prop.proposal_id)
            cr = critique_map.get(prop.proposal_id)
            sa = scope_map.get(prop.proposal_id)

            sol = Solution(
                issue_id=issue_id,
                title=prop.title,
                strategy_type=prop.strategy_type,
                description=prop.description,
                rationale=prop.complexity_explanation,
                affected_files=prop.affected_files,
                expected_changes=prop.expected_changes,
                advantages=prop.advantages,
                disadvantages=prop.disadvantages,
                security_implications=prop.security_implications,
                regression_risks=prop.regression_risks,
                complexity_score=prop.complexity_score,
                is_recommended=ep.is_recommended if ep else False,
                rank=ep.rank if ep else None,
                critique=cr.model_dump(mode="json") if cr else {},
                evaluation=ep.model_dump(mode="json") if ep else {},
                scope_assessment=sa.model_dump(mode="json") if sa else {},
                supporting_evidence_ids=prop.supporting_evidence_ids or evidence_ids,
            )
            db.add(sol)
            persisted_solutions.append(sol)

        await db.flush()

        # 11. Finalize Resolution Lead task & Transition to AWAITING_FIX_APPROVAL
        lead_task.status = TaskStatus.COMPLETED
        lead_task.task_output = {
            "root_cause": rca_report.model_dump(mode="json"),
            "proposals_count": len(arch_result.proposals),
            "recommended_strategy": eval_report.recommended_proposal_id,
            "debate_round": debate_round,
        }

        # Transition workflow to AWAITING_FIX_APPROVAL
        await WorkflowEngine.transition_issue(
            db=db,
            issue_id=issue_id,
            target_status=IssueStatus.AWAITING_FIX_APPROVAL,
            actor="resolution_lead",
            reason=(
                f"Resolution debate completed (Round {debate_round}). "
                f"{len(persisted_solutions)} competing strategies ready for developer fix approval."
            ),
        )

        await switch_adapter.send_message(
            SwitchMessagePayload(
                room_id=room_id,
                sender_id=AgentRole.RESOLUTION_LEAD.value,
                sender_role=AgentRole.RESOLUTION_LEAD.value,
                content=(
                    f"🏁 **Resolution Stage Complete -> Awaiting Developer Fix Approval**\n"
                    f"Presented {len(persisted_solutions)} competing strategies in dashboard.\n"
                    "Developer approval is mandatory before any implementation begins."
                ),
            )
        )

        await db.commit()
        await db.refresh(issue)

        return {
            "issue_id": issue_id,
            "status": issue.status.value,
            "root_cause": rca_report,
            "proposals": arch_result.proposals,
            "critiques": critic_result.critiques,
            "scope_report": scope_report,
            "evaluation": eval_report,
            "persisted_solutions_count": len(persisted_solutions),
        }


resolution_coordinator = ResolutionCoordinator()
