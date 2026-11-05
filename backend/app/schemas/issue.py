import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import ApprovalDecision, IssueStatus
from backend.app.schemas.approval import ApprovalResponse
from backend.app.schemas.audit import AuditEventResponse
from backend.app.schemas.project import ProjectResponse


class IssueCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=512, description="Short summary of what happened")
    description: str = Field(..., min_length=5, description="Detailed explanation of the issue")
    project_id: Optional[uuid.UUID] = Field(None, description="Connected project ID; auto-assigned if omitted")
    expected_behavior: Optional[str] = Field(None, description="What you expected to happen instead")
    steps_attempted: Optional[str] = Field(None, description="Steps or actions taken before the issue occurred")
    reporter_environment: Optional[Dict[str, Any]] = Field(None, description="Optional environment details (browser, OS, device)")


class IssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: uuid.UUID
    title: str
    description: str
    expected_behavior: Optional[str] = None
    steps_attempted: Optional[str] = None
    reporter_environment: Optional[Dict[str, Any]] = None
    status: IssueStatus
    created_at: datetime
    updated_at: datetime


class IssueDetailResponse(IssueResponse):
    project: Optional[ProjectResponse] = None
    approvals: List[ApprovalResponse] = []
    audit_events: List[AuditEventResponse] = []


class IssueTriageRequest(BaseModel):
    decision: ApprovalDecision = Field(..., description="Developer triage decision: ACCEPTED, REJECTED, REQUEST_INFORMATION, DEFERRED")
    actor: str = Field(..., min_length=1, max_length=255, description="Name or identifier of the developer")
    notes: Optional[str] = Field(None, description="Optional explanation or triage notes")


class IssueTransitionRequest(BaseModel):
    target_status: IssueStatus = Field(..., description="Target status for state machine transition")
    actor: str = Field(..., min_length=1, max_length=255, description="Actor initiating transition")
    reason: Optional[str] = Field("", description="Reason for transition")
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata or context")
