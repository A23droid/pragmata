import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db
from backend.app.models.entities import Project
from backend.app.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/projects", tags=["Projects"])


async def get_or_create_default_project(db: AsyncSession) -> Project:
    stmt = select(Project).limit(1)
    result = await db.execute(stmt)
    project = result.scalars().first()
    if not project:
        project = Project(
            name="Sample Target Repository",
            repo_url="https://github.com/example/sample-repo.git",
            default_branch="main",
            config={"sample": True},
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
    return project


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = Project(
        name=payload.name,
        repo_url=payload.repo_url,
        default_branch=payload.default_branch,
        config=payload.config,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("", response_model=List[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    stmt = select(Project).order_by(Project.created_at.desc())
    result = await db.execute(stmt)
    projects = result.scalars().all()
    if not projects:
        default_p = await get_or_create_default_project(db)
        return [default_p]
    return projects


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
