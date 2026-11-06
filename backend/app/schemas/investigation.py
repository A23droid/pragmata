import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import EvidenceType, InvestigationOutcome, ProvenanceType


class RepoInspectRequest(BaseModel):
    max_depth: int = Field(default=3, ge=1, le=8, description="Maximum directory traversal depth")
    search_query: Optional[str] = Field(None, description="Optional regex/text search query across repository")
    file_extensions: Optional[List[str]] = Field(None, description="Optional extension filters, e.g. ['.py', '.ts']")


class RepoInspectResponse(BaseModel):
    commit_sha: str
    branch: str
    total_files: int
    detected_languages: List[str]
    detected_frameworks: List[str]
    test_commands: List[str]
    file_tree: List[Dict[str, Any]]
    readme_snippet: Optional[str] = None
    config_files: List[str] = []
    search_results: List[Dict[str, Any]] = []


class SandboxRunRequest(BaseModel):
    command: str = Field(..., min_length=1, description="Command to execute inside isolated Docker container")
    image: Optional[str] = Field(None, description="Docker image (defaults to configured alpine:latest)")
    timeout_seconds: Optional[int] = Field(None, ge=1, le=180, description="Execution timeout in seconds")
    network_enabled: bool = Field(default=False, description="Whether network should be enabled; default is false")
    read_only_workspace: bool = Field(default=False, description="Mount workspace as read-only")


class SandboxRunResponse(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    error_message: Optional[str] = None


class InvestigationCreate(BaseModel):
    commit_sha: Optional[str] = Field(None, description="Recorded base commit SHA tested")
    environment_details: Dict[str, Any] = Field(default_factory=dict)
    outcome: InvestigationOutcome = Field(default=InvestigationOutcome.PENDING)
    summary: Optional[str] = None


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: str
    commit_sha: Optional[str] = None
    environment_details: Dict[str, Any]
    attempts_count: int
    outcome: InvestigationOutcome
    summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EvidenceCreate(BaseModel):
    investigation_id: Optional[uuid.UUID] = None
    evidence_type: EvidenceType
    content: str
    tool_name: Optional[str] = None
    exit_code: Optional[int] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    provenance: ProvenanceType = ProvenanceType.TOOL


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: str
    investigation_id: Optional[uuid.UUID] = None
    evidence_type: EvidenceType
    content: str
    tool_name: Optional[str] = None
    exit_code: Optional[int] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    provenance: ProvenanceType
    created_at: datetime


class AgentTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: str
    agent_role: str
    status: str
    task_input: Dict[str, Any] = Field(default_factory=dict)
    task_output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    parent_task_id: Optional[uuid.UUID] = None
    timeout_seconds: int
    retry_count: int
    max_retries: int
    created_at: datetime
    updated_at: datetime
