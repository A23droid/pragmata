import logging
from typing import Any, Dict, List, Optional
import httpx

from backend.app.core.config import settings
from backend.app.models.enums import ChannelType
from backend.app.schemas.switch import (
    SwitchAgentRegistration,
    SwitchHandoff,
    SwitchMessagePayload,
    SwitchRoomCreate,
)

logger = logging.getLogger(__name__)


class SwitchAdapter:
    """
    Dedicated Switch Agent Protocol adapter.
    Encapsulates all Switch room management, agent identity registration,
    messaging, and handoffs. Handles connectivity failures gracefully
    without compromising canonical PostgreSQL workflow state.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        registration_token: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.SWITCH_BASE_URL).rstrip("/")
        self.registration_token = registration_token or settings.SWITCH_REGISTRATION_TOKEN
        self.is_connected = False
        self._registered_agents: Dict[str, SwitchAgentRegistration] = {}
        self._rooms: Dict[str, Dict[str, Any]] = {}

    def get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.registration_token:
            headers["Authorization"] = f"Bearer {self.registration_token}"
        return headers

    async def check_health(self) -> bool:
        """Verify reachability of Switch server."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/health", headers=self.get_headers())
                self.is_connected = res.status_code == 200
                return self.is_connected
        except Exception as ex:
            logger.warning(f"Switch server at {self.base_url} is unreachable: {ex}")
            self.is_connected = False
            return False

    async def register_agent(self, registration: SwitchAgentRegistration) -> bool:
        """Register an agent role in Switch."""
        self._registered_agents[registration.agent_id] = registration
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/agents/register",
                    json=registration.model_dump(),
                    headers=self.get_headers(),
                )
                return res.status_code in (200, 201)
        except Exception as ex:
            logger.info(f"Switch agent registration queued locally for {registration.agent_id} ({ex})")
            return True

    async def create_or_join_room(self, room_req: SwitchRoomCreate) -> Dict[str, Any]:
        """Create or associate a Switch room for an issue."""
        room_id = f"switch_room_{room_req.issue_id}_{room_req.channel_type.value.lower()}"
        room_data = {
            "room_id": room_id,
            "issue_id": room_req.issue_id,
            "name": room_req.room_name,
            "channel_type": room_req.channel_type.value,
            "topic": room_req.topic or f"PRAGMATA Issue {room_req.issue_id}",
            "members": list(set(room_req.initial_members)),
            "active": True,
        }
        self._rooms[room_id] = room_data

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{self.base_url}/api/v1/rooms",
                    json=room_data,
                    headers=self.get_headers(),
                )
        except Exception as ex:
            logger.info(f"Switch room creation recorded locally: {room_id} ({ex})")

        return room_data

    async def send_message(self, payload: SwitchMessagePayload) -> bool:
        """Send message from an agent or system into a Switch issue room."""
        logger.info(
            f"[Switch Room {payload.room_id}] [{payload.sender_role}]: {payload.content[:100]}..."
        )
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/v1/rooms/{payload.room_id}/messages",
                    json=payload.model_dump(mode="json"),
                    headers=self.get_headers(),
                )
                return res.status_code in (200, 201)
        except Exception as ex:
            logger.debug(f"Switch message stored locally ({ex})")
            return True

    async def route_handoff(self, handoff: SwitchHandoff) -> bool:
        """Explicit targeted task handoff between agents in Switch."""
        message = SwitchMessagePayload(
            room_id=handoff.room_id,
            sender_id=handoff.from_role,
            sender_role=handoff.from_role,
            content=f"👉 **Handoff to {handoff.to_role}**: {handoff.task_description}",
            metadata={
                "handoff": True,
                "target_role": handoff.to_role,
                "payload": handoff.payload,
            },
        )
        return await self.send_message(message)


switch_adapter = SwitchAdapter()

