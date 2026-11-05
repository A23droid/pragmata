import secrets
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.v1.projects import get_or_create_default_project
from backend.app.db.session import get_db
from backend.app.models.entities import AuditEvent, Issue, Project
from backend.app.models.enums import IssueStatus
from backend.app.schemas.audit import AuditEventResponse
from backend.app.schemas.issue import (
    IssueCreate,
    IssueDetailResponse,
    IssueResponse,
    IssueTransitionRequest,
    IssueTriageRequest,
)
from backend.app.services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/issues", tags=["Issues"])


def generate_issue_id() -> str:
    return f"PRAG-{secrets.token_hex(3).upper()}"


@router.post("", response_model=IssueResponse, status_code=status.HTTP_201_CREATED)
async def create_issue(
    payload: IssueCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Intake bug report from any user (reporter/developer).
    Non-technical plain language input is accepted.
    """
    # Resolve or create default project if not provided
    project_id = payload.project_id
    if not project_id:
        default_project = await get_or_create_default_project(db)
        project_id = default_project.id
    else:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with ID '{project_id}' does not exist.",
            )

    issue_id = generate_issue_id()

    # Determine initial status:
    # If the report is lacking basic detail, mark NEEDS_INFORMATION, else RECEIVED.
    initial_status = IssueStatus.RECEIVED
    if len(payload.description.strip()) < 10:
        initial_status = IssueStatus.NEEDS_INFORMATION

    issue = Issue(
        id=issue_id,
        project_id=project_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        expected_behavior=payload.expected_behavior.strip() if payload.expected_behavior else None,
        steps_attempted=payload.steps_attempted.strip() if payload.steps_attempted else None,
        reporter_environment=payload.reporter_environment,
        status=initial_status,
    )
    db.add(issue)

    # Record intake audit event
    audit = AuditEvent(
        issue_id=issue_id,
        event_type="ISSUE_SUBMITTED",
        from_state=None,
        to_state=initial_status.value,
        actor="reporter",
        payload={
            "title": issue.title,
            "has_environment": bool(issue.reporter_environment),
        },
    )
    db.add(audit)

    await db.commit()
    await db.refresh(issue)
    return issue


@router.get("", response_model=List[IssueResponse])
async def list_issues(
    status_filter: Optional[IssueStatus] = Query(None, alias="status", description="Filter by issue status"),
    project_id: Optional[uuid.UUID] = Query(None, description="Filter by project ID"),
    db: AsyncSession = Depends(get_db),
):
    """List issues with optional status and project filters."""
    stmt = select(Issue).order_by(Issue.created_at.desc())
    if status_filter:
        stmt = stmt.where(Issue.status == status_filter)
    if project_id:
        stmt = stmt.where(Issue.project_id == project_id)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{issue_id}", response_model=IssueDetailResponse)
async def get_issue(issue_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch complete issue details including project metadata, approvals, and audit trail."""
    stmt = (
        select(Issue)
        .where(Issue.id == issue_id)
        .options(
            selectinload(Issue.project),
            selectinload(Issue.approvals),
            selectinload(Issue.audit_events),
        )
    )
    result = await db.execute(stmt)
    issue = result.scalar_one_or_none()
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found.",
        )
    return issue


@router.post("/{issue_id}/triage", response_model=IssueResponse)
async def triage_issue(
    issue_id: str,
    payload: IssueTriageRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Developer triage gate.
    Authenticated developer explicitly accepts, rejects, requests info, or defers the issue.
    """
    return await WorkflowEngine.triage_issue(
        db=db,
        issue_id=issue_id,
        decision=payload.decision,
        actor=payload.actor,
        notes=payload.notes,
    )


@router.post("/{issue_id}/transition", response_model=IssueResponse)
async def transition_issue(
    issue_id: str,
    payload: IssueTransitionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Deterministic workflow transition. Validates transition legality and enforces guards.
    """
    return await WorkflowEngine.transition_issue(
        db=db,
        issue_id=issue_id,
        target_status=payload.target_status,
        actor=payload.actor,
        reason=payload.reason or "",
        payload=payload.payload,
    )


@router.get("/{issue_id}/audit", response_model=List[AuditEventResponse])
async def get_issue_audit(issue_id: str, db: AsyncSession = Depends(get_db)):
    """Fetch complete immutable audit log for an issue."""
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.issue_id == issue_id)
        .order_by(AuditEvent.created_at.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()
