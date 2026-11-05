import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, ConfigDict


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: str
    event_type: str
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    actor: str
    payload: Dict[str, Any] = {}
    created_at: datetime
