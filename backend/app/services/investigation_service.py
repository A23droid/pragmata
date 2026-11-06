import logging
import uuid
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.entities import Evidence, Investigation, Issue, Project
from backend.app.models.enums import EvidenceType, InvestigationOutcome, ProvenanceType
from backend.app.schemas.investigation import (
    EvidenceCreate,
    InvestigationCreate,
    RepoInspectRequest,
    RepoInspectResponse,
    SandboxRunRequest,
    SandboxRunResponse,
)
from backend.app.services.repository.inspector import RepoInspector
from backend.app.services.repository.workspace import ManagedWorkspace
from backend.app.services.sandbox.docker_runner import DockerSandbox

logger = logging.getLogger(__name__)


class InvestigationService:
    @classmethod
    async def get_issue_with_project(cls, db: AsyncSession, issue_id: str) -> Issue:
        stmt = (
            select(Issue)
            .where(Issue.id == issue_id)
            .options(selectinload(Issue.project))
        )
        result = await db.execute(stmt)
        issue = result.scalar_one_or_none()
        if not issue:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Issue '{issue_id}' not found.",
            )
        return issue

    @classmethod
    async def inspect_repository(
        cls,
        db: AsyncSession,
        issue_id: str,
        inspect_req: RepoInspectRequest,
    ) -> RepoInspectResponse:
        """
        Clones project repository into a managed workspace, records the exact commit SHA,
        safely extracts file tree, languages, frameworks, test runners, and optional code search.
        Workspace is guaranteed to be cleaned up after inspection.
        """
        issue = await cls.get_issue_with_project(db, issue_id)
        project: Project = issue.project

        async with ManagedWorkspace(
            repo_url=project.repo_url,
            branch_or_commit=project.default_branch,
        ) as ws:
            inspector = RepoInspector(ws.path)
            summary = inspector.summarize()

            search_results = []
            if inspect_req.search_query:
                matches = inspector.search_code(
                    query=inspect_req.search_query,
                    max_matches=25,
                    file_extensions=inspect_req.file_extensions,
                )
                search_results = [
                    {
                        "file_path": m.file_path,
                        "line_number": m.line_number,
                        "line_content": m.line_content,
                    }
                    for m in matches
                ]

            return RepoInspectResponse(
                commit_sha=ws.commit_sha or "unknown",
                branch=ws.metadata.branch if ws.metadata else project.default_branch,
                total_files=summary.total_files,
                detected_languages=summary.detected_languages,
                detected_frameworks=summary.detected_frameworks,
                test_commands=summary.test_commands,
                file_tree=summary.file_tree,
                readme_snippet=summary.readme_snippet,
                config_files=summary.config_files,
                search_results=search_results,
            )

    @classmethod
    async def run_sandbox_command(
        cls,
        db: AsyncSession,
        issue_id: str,
        run_req: SandboxRunRequest,
        record_evidence: bool = True,
    ) -> SandboxRunResponse:
        """
        Executes a controlled command inside the safe Docker sandbox with resource limits,
        bounded output, and offline isolation. Optionally records the real outcome as Evidence.
        """
        issue = await cls.get_issue_with_project(db, issue_id)
        project: Project = issue.project

        async with ManagedWorkspace(
            repo_url=project.repo_url,
            branch_or_commit=project.default_branch,
        ) as ws:
            sandbox = DockerSandbox(
                workspace_path=ws.path,
                image=run_req.image,
                timeout_seconds=run_req.timeout_seconds,
                network_enabled=run_req.network_enabled,
                read_only_workspace=run_req.read_only_workspace,
            )
            result = await sandbox.run_command(run_req.command)

            # Persist real execution evidence in PostgreSQL
            if record_evidence:
                # 1. Update or create investigation record
                inv_stmt = select(Investigation).where(Investigation.issue_id == issue_id).order_by(Investigation.created_at.desc())
                inv_res = await db.execute(inv_stmt)
                investigation = inv_res.scalars().first()
                if not investigation:
                    investigation = Investigation(
                        issue_id=issue_id,
                        commit_sha=ws.commit_sha,
                        environment_details={"image": sandbox.image, "network": run_req.network_enabled},
                        attempts_count=1,
                        outcome=InvestigationOutcome.PENDING,
                        summary=f"Reproduction attempt using '{run_req.command[:60]}'",
                    )
                    db.add(investigation)
                    await db.flush()
                else:
                    investigation.attempts_count += 1
                    if ws.commit_sha:
                        investigation.commit_sha = ws.commit_sha

                # 2. Record Evidence entity
                full_output = (result.stdout + "\n" + result.stderr).strip()
                evidence = Evidence(
                    issue_id=issue_id,
                    investigation_id=investigation.id,
                    evidence_type=EvidenceType.REPRODUCTION_OUTPUT,
                    content=full_output or "[No output produced]",
                    tool_name="docker_sandbox",
                    exit_code=result.exit_code,
                    provenance=ProvenanceType.TOOL,
                )
                db.add(evidence)
                await db.commit()

            return SandboxRunResponse(
                command=result.command,
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=result.duration_seconds,
                timed_out=result.timed_out,
                error_message=result.error_message,
            )

    @classmethod
    async def create_investigation(
        cls,
        db: AsyncSession,
        issue_id: str,
        payload: InvestigationCreate,
    ) -> Investigation:
        await cls.get_issue_with_project(db, issue_id)
        investigation = Investigation(
            issue_id=issue_id,
            commit_sha=payload.commit_sha,
            environment_details=payload.environment_details,
            outcome=payload.outcome,
            summary=payload.summary,
            attempts_count=1,
        )
        db.add(investigation)
        await db.commit()
        await db.refresh(investigation)
        return investigation

    @classmethod
    async def list_investigations(
        cls,
        db: AsyncSession,
        issue_id: str,
    ) -> List[Investigation]:
        stmt = (
            select(Investigation)
            .where(Investigation.issue_id == issue_id)
            .order_by(Investigation.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def create_evidence(
        cls,
        db: AsyncSession,
        issue_id: str,
        payload: EvidenceCreate,
    ) -> Evidence:
        await cls.get_issue_with_project(db, issue_id)
        evidence = Evidence(
            issue_id=issue_id,
            investigation_id=payload.investigation_id,
            evidence_type=payload.evidence_type,
            content=payload.content,
            tool_name=payload.tool_name,
            exit_code=payload.exit_code,
            file_path=payload.file_path,
            line_start=payload.line_start,
            line_end=payload.line_end,
            provenance=payload.provenance,
        )
        db.add(evidence)
        await db.commit()
        await db.refresh(evidence)
        return evidence

    @classmethod
    async def list_evidence(
        cls,
        db: AsyncSession,
        issue_id: str,
    ) -> List[Evidence]:
        stmt = (
            select(Evidence)
            .where(Evidence.issue_id == issue_id)
            .order_by(Evidence.created_at.desc())
        )
        result = await db.execute(stmt)
        return result.scalars().all()
