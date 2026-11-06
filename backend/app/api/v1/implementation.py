import logging
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import DeveloperUser, require_developer_auth
from backend.app.db.session import get_db
from backend.app.models.entities import Implementation, Issue, VerificationRun
from backend.app.schemas.implementation import (
    ImplementationDetailResponse,
    ImplementationRequest,
    VerificationRequest,
    VerificationResponse,
)
from backend.app.services.implementation.implementer import implementer_service
from backend.app.services.verification.verifier import verifier_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/issues/{issue_id}", tags=["Implementation & Verification"])


@router.post("/implement", response_model=Dict[str, Any])
async def trigger_implementation(
    issue_id: str,
    request: ImplementationRequest,
    current_user: DeveloperUser = Depends(require_developer_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger isolated implementation of an approved fix on a dedicated Git branch.
    Enforces developer approval invariant before modifying source code.
    """
    impl = await implementer_service.execute_implementation(
        db=db,
        issue_id=issue_id,
        request=request,
        actor=current_user.id,
    )
    return {
        "status": "success",
        "implementation_id": str(impl.id),
        "branch_name": impl.branch_name,
        "base_commit_sha": impl.base_commit_sha,
        "changed_files": impl.changed_files,
        "commit_shas": impl.commit_shas,
    }


@router.post("/verify", response_model=VerificationResponse)
async def trigger_verification(
    issue_id: str,
    request: VerificationRequest,
    current_user: DeveloperUser = Depends(require_developer_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger Docker sandbox verification (reproduction re-run and project tests).
    Transitions issue to RESOLVED only if all verification checks pass.
    """
    return await verifier_service.execute_verification(
        db=db,
        issue_id=issue_id,
        request=request,
        actor=current_user.id,
    )


@router.get("/implementation", response_model=Dict[str, Any])
async def get_implementation_status(
    issue_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch the latest implementation details, Git branch, and verification history for an issue.
    """
    stmt = (
        select(Implementation)
        .where(Implementation.issue_id == issue_id)
        .order_by(Implementation.created_at.desc())
        .options(selectinload(Implementation.verification_runs))
    )
    res = await db.execute(stmt)
    impl = res.scalars().first()

    if not impl:
        return {
            "has_implementation": False,
            "issue_id": issue_id,
        }

    return {
        "has_implementation": True,
        "id": str(impl.id),
        "issue_id": impl.issue_id,
        "branch_name": impl.branch_name,
        "base_commit_sha": impl.base_commit_sha,
        "changed_files": impl.changed_files,
        "commit_shas": impl.commit_shas,
        "status": impl.status.value,
        "created_at": impl.created_at.isoformat(),
        "verification_runs": [
            {
                "id": str(v.id),
                "status": v.status.value,
                "exit_code": v.exit_code,
                "repro_verified": v.repro_verified,
                "regression_test_passed": v.regression_test_passed,
                "created_at": v.created_at.isoformat(),
            }
            for v in impl.verification_runs
        ],
    }
