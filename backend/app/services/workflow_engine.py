import logging
from typing import Any, Dict, Optional, Set
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Approval, AuditEvent, Issue, VerificationRun
from backend.app.models.enums import (
    ApprovalDecision,
    ApprovalTarget,
    IssueStatus,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

# Canonical map of allowed state transitions
ALLOWED_TRANSITIONS: Dict[IssueStatus, Set[IssueStatus]] = {
    IssueStatus.RECEIVED: {
        IssueStatus.INVESTIGATING,
        IssueStatus.NEEDS_INFORMATION,
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    },
    IssueStatus.NEEDS_INFORMATION: {
        IssueStatus.RECEIVED,
        IssueStatus.INVESTIGATING,
        IssueStatus.DEFERRED,
        IssueStatus.REJECTED,
    },
    IssueStatus.INVESTIGATING: {
        IssueStatus.REPRODUCING,
        IssueStatus.NOT_REPRODUCED,
        IssueStatus.NEEDS_INFORMATION,
        IssueStatus.VERIFICATION_BLOCKED,
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    },
    IssueStatus.REPRODUCING: {
        IssueStatus.REPRODUCED,
        IssueStatus.NOT_REPRODUCED,
        IssueStatus.NEEDS_INFORMATION,
        IssueStatus.VERIFICATION_BLOCKED,
    },
    IssueStatus.REPRODUCED: {
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    },
    IssueStatus.NOT_REPRODUCED: {
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
        IssueStatus.INVESTIGATING,
    },
    IssueStatus.AWAITING_DEVELOPER_TRIAGE: {
        IssueStatus.ACCEPTED,
        IssueStatus.REJECTED,
        IssueStatus.NEEDS_INFORMATION,
        IssueStatus.DEFERRED,
        IssueStatus.INVESTIGATING,
    },
    IssueStatus.ACCEPTED: {
        IssueStatus.ROOT_CAUSE_ANALYSIS,
    },
    IssueStatus.ROOT_CAUSE_ANALYSIS: {
        IssueStatus.FIX_STRATEGY_DISCUSSION,
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    },
    IssueStatus.FIX_STRATEGY_DISCUSSION: {
        IssueStatus.AWAITING_FIX_APPROVAL,
    },
    IssueStatus.AWAITING_FIX_APPROVAL: {
        IssueStatus.IMPLEMENTING,
        IssueStatus.FIX_STRATEGY_DISCUSSION,
        IssueStatus.DEFERRED,
        IssueStatus.REJECTED,
    },
    IssueStatus.IMPLEMENTING: {
        IssueStatus.VERIFYING,
        IssueStatus.IMPLEMENTATION_FAILED,
        IssueStatus.AWAITING_FIX_APPROVAL,
    },
    IssueStatus.IMPLEMENTATION_FAILED: {
        IssueStatus.IMPLEMENTING,
        IssueStatus.AWAITING_FIX_APPROVAL,
    },
    IssueStatus.VERIFYING: {
        IssueStatus.RESOLVED,
        IssueStatus.IMPLEMENTATION_FAILED,
        IssueStatus.VERIFICATION_BLOCKED,
    },
    IssueStatus.VERIFICATION_BLOCKED: {
        IssueStatus.INVESTIGATING,
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
        IssueStatus.AWAITING_FIX_APPROVAL,
        IssueStatus.DEFERRED,
    },
    IssueStatus.DEFERRED: {
        IssueStatus.RECEIVED,
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
        IssueStatus.ACCEPTED,
    },
    IssueStatus.REJECTED: {
        IssueStatus.AWAITING_DEVELOPER_TRIAGE,
    },
    IssueStatus.RESOLVED: {
        IssueStatus.INVESTIGATING,
    },
}


class WorkflowEngine:
    @classmethod
    async def get_issue_with_lock(cls, db: AsyncSession, issue_id: str) -> Issue:
        """Fetch issue using SELECT FOR UPDATE to prevent race conditions during state transitions."""
        stmt = select(Issue).where(Issue.id == issue_id).with_for_update()
        result = await db.execute(stmt)
        issue = result.scalar_one_or_none()
        if not issue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue '{issue_id}' not found.",
            )
        return issue

    @classmethod
    async def transition_issue(
        cls,
        db: AsyncSession,
        issue_id: str,
        target_status: IssueStatus,
        actor: str,
        reason: str = "",
        payload: Optional[Dict[str, Any]] = None,
        bypass_triage_check: bool = False,
    ) -> Issue:
        """
        Deterministically transition an issue to a target status with validation and audit logging.
        Enforces product invariants.
        """
        issue = await cls.get_issue_with_lock(db, issue_id)
        current_status = issue.status

        if current_status == target_status:
            return issue

        # 1. Validate state transition legality
        allowed = ALLOWED_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Illegal state transition from '{current_status.value}' to "
                    f"'{target_status.value}'. Allowed transitions: {[s.value for s in allowed]}"
                ),
            )

        # 2. Invariant: Triage gate enforcement
        if (
            current_status == IssueStatus.AWAITING_DEVELOPER_TRIAGE
            and target_status in {IssueStatus.ACCEPTED, IssueStatus.REJECTED, IssueStatus.DEFERRED}
            and not bypass_triage_check
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Transition from AWAITING_DEVELOPER_TRIAGE to {target_status.value} "
                    "requires explicit developer triage action via /triage endpoint."
                ),
            )

        # 3. Invariant: Implementation requires recorded fix approval
        if target_status == IssueStatus.IMPLEMENTING:
            appr_stmt = select(Approval).where(
                Approval.issue_id == issue_id,
                Approval.target_type == ApprovalTarget.FIX_STRATEGY,
            )
            appr_res = await db.execute(appr_stmt)
            if not appr_res.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot begin implementation without recorded developer fix approval.",
                )

        # 4. Invariant: Resolution requires verified verification runs
        if target_status == IssueStatus.RESOLVED:
            v_stmt = select(VerificationRun).where(VerificationRun.issue_id == issue_id)
            v_res = await db.execute(v_stmt)
            runs = v_res.scalars().all()
            if not runs or any(r.status != VerificationStatus.PASSED for r in runs):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot mark issue as RESOLVED: required verification checks have not passed.",
                )

        # 5. Apply transition
        issue.status = target_status

        # 6. Record audit event
        audit = AuditEvent(
            issue_id=issue_id,
            event_type="STATE_TRANSITION",
            from_state=current_status.value,
            to_state=target_status.value,
            actor=actor,
            payload={
                "reason": reason,
                **(payload or {}),
            },
        )
        db.add(audit)
        await db.commit()
        await db.refresh(issue)

        logger.info(
            f"Issue {issue_id} transitioned: {current_status.value} -> {target_status.value} by {actor}"
        )
        return issue

    @classmethod
    async def triage_issue(
        cls,
        db: AsyncSession,
        issue_id: str,
        decision: ApprovalDecision,
        actor: str,
        notes: Optional[str] = None,
    ) -> Issue:
        """
        Enforce the developer triage gate.
        Validates issue state, records developer approval decision, and advances the workflow.
        """
        issue = await cls.get_issue_with_lock(db, issue_id)

        # Developer triage can be conducted when issue is AWAITING_DEVELOPER_TRIAGE,
        # or when REPRODUCED / NOT_REPRODUCED (automatically advances to triage gate).
        if issue.status in {IssueStatus.REPRODUCED, IssueStatus.NOT_REPRODUCED}:
            issue.status = IssueStatus.AWAITING_DEVELOPER_TRIAGE
            db.add(
                AuditEvent(
                    issue_id=issue_id,
                    event_type="AUTO_GATE_TRIGGER",
                    from_state=issue.status.value,
                    to_state=IssueStatus.AWAITING_DEVELOPER_TRIAGE.value,
                    actor="system",
                    payload={"note": "Auto-routed to developer triage gate upon reproduction outcome."},
                )
            )

        if issue.status != IssueStatus.AWAITING_DEVELOPER_TRIAGE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Issue '{issue_id}' is in status '{issue.status.value}' and cannot undergo developer triage. "
                    "Issue must be in 'AWAITING_DEVELOPER_TRIAGE'."
                ),
            )

        # Map decision to target status
        target_status_map = {
            ApprovalDecision.ACCEPTED: IssueStatus.ACCEPTED,
            ApprovalDecision.REJECTED: IssueStatus.REJECTED,
            ApprovalDecision.REQUEST_INFORMATION: IssueStatus.NEEDS_INFORMATION,
            ApprovalDecision.DEFERRED: IssueStatus.DEFERRED,
        }

        if decision not in target_status_map:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid triage decision '{decision.value}'. Must be one of ACCEPTED, REJECTED, REQUEST_INFORMATION, DEFERRED.",
            )

        target_status = target_status_map[decision]

        # Record human approval
        approval = Approval(
            issue_id=issue_id,
            decision=decision,
            target_type=ApprovalTarget.ISSUE_TRIAGE,
            actor=actor,
            notes=notes,
        )
        db.add(approval)

        # Transition issue status
        issue.status = target_status

        # Record audit event
        audit = AuditEvent(
            issue_id=issue_id,
            event_type="DEVELOPER_TRIAGE",
            from_state=IssueStatus.AWAITING_DEVELOPER_TRIAGE.value,
            to_state=target_status.value,
            actor=actor,
            payload={
                "decision": decision.value,
                "notes": notes or "",
            },
        )
        db.add(audit)

        await db.commit()
        await db.refresh(issue)

        logger.info(
            f"Developer triage on {issue_id}: {decision.value} by {actor}. Status now {target_status.value}."
        )
        return issue
