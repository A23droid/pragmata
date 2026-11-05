import uuid
from datetime import datetime
from typing import Any, Dict
from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Project name")
    repo_url: str = Field(..., min_length=1, max_length=1024, description="Repository URL")
    default_branch: str = Field("main", max_length=255, description="Default Git branch")
    config: Dict[str, Any] = Field(default_factory=dict, description="Project configuration")


class ProjectCreate(ProjectBase):
    pass


class ProjectResponse(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
