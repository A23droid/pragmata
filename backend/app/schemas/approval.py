import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from backend.app.models.enums import ApprovalDecision, ApprovalTarget


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: str
    decision: ApprovalDecision
    target_type: ApprovalTarget
    solution_id: Optional[uuid.UUID] = None
    custom_strategy: Optional[str] = None
    actor: str
    notes: Optional[str] = None
    created_at: datetime
