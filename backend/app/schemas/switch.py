from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from backend.app.models.enums import ChannelType


class SwitchAgentRegistration(BaseModel):
    agent_id: str
    display_name: str
    role: str
    capabilities: List[str] = Field(default_factory=list)


class SwitchRoomCreate(BaseModel):
    issue_id: str
    room_name: str
    channel_type: ChannelType = ChannelType.INVESTIGATION
    topic: Optional[str] = None
    initial_members: List[str] = Field(default_factory=list)


class SwitchMessagePayload(BaseModel):
    room_id: str
    sender_id: str
    sender_role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SwitchHandoff(BaseModel):
    issue_id: str
    room_id: str
    from_role: str
    to_role: str
    task_description: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class ConversationReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: str
    room_id: str
    channel_type: ChannelType
    external_thread_id: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
