from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db
from backend.app.schemas.investigation import (
    AgentTaskResponse,
    EvidenceCreate,
    EvidenceResponse,
    InvestigationCreate,
    InvestigationResponse,
    RepoInspectRequest,
    RepoInspectResponse,
    SandboxRunRequest,
    SandboxRunResponse,
)
from backend.app.services.agents.investigation_coordinator import investigation_coordinator
from backend.app.services.agents.roles import InvestigationLeadReport
from backend.app.services.investigation_service import InvestigationService

router = APIRouter(prefix="/issues/{issue_id}", tags=["Investigation & Sandbox"])


@router.post("/investigate", response_model=InvestigationLeadReport)
async def run_investigation_workflow(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger the complete hierarchical bug investigation & reproduction workflow.
    Investigation Lead coordinates Intake Agent, Investigator, Reproducer, and Evidence Validator.
    All findings, sandbox reproduction results, and evidence are persisted to PostgreSQL
    and reported to the issue's Switch collaboration room.
    """
    return await investigation_coordinator.run_investigation(
        db=db,
        issue_id=issue_id,
    )


@router.get("/tasks", response_model=List[AgentTaskResponse])
async def list_agent_tasks(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all agent tasks executed for this issue."""
    return await InvestigationService.list_agent_tasks(
        db=db,
        issue_id=issue_id,
    )


@router.post("/inspect", response_model=RepoInspectResponse)
async def inspect_repository(
    issue_id: str,
    payload: RepoInspectRequest = RepoInspectRequest(),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch repository, record base commit SHA, and inspect project layout,
    languages, frameworks, test runners, and optional code search.
    """
    return await InvestigationService.inspect_repository(
        db=db,
        issue_id=issue_id,
        inspect_req=payload,
    )


@router.post("/sandbox", response_model=SandboxRunResponse)
async def run_in_sandbox(
    issue_id: str,
    payload: SandboxRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a controlled reproduction or test command inside an isolated Docker sandbox.
    Resource limits, timeouts, offline isolation, and host credential scrubbing are enforced.
    Actual exit code, stdout, and stderr are recorded as real evidence.
    """
    return await InvestigationService.run_sandbox_command(
        db=db,
        issue_id=issue_id,
        run_req=payload,
        record_evidence=True,
    )


@router.post("/investigations", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    issue_id: str,
    payload: InvestigationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Record an investigation attempt or outcome."""
    return await InvestigationService.create_investigation(
        db=db,
        issue_id=issue_id,
        payload=payload,
    )


@router.get("/investigations", response_model=List[InvestigationResponse])
async def list_investigations(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all recorded investigation attempts for an issue."""
    return await InvestigationService.list_investigations(
        db=db,
        issue_id=issue_id,
    )


@router.post("/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED)
async def create_evidence(
    issue_id: str,
    payload: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Record an evidence item (test result, reproduction output, log, file reference)."""
    return await InvestigationService.create_evidence(
        db=db,
        issue_id=issue_id,
        payload=payload,
    )


@router.get("/evidence", response_model=List[EvidenceResponse])
async def list_evidence(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all evidence recorded for an issue."""
    return await InvestigationService.list_evidence(
        db=db,
        issue_id=issue_id,
    )
