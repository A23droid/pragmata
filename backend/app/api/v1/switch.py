from fastapi import APIRouter, HTTPException, status
from backend.app.schemas.switch import (
    SwitchAgentRegistration,
    SwitchHandoff,
    SwitchMessagePayload,
    SwitchRoomCreate,
)
from backend.app.services.switch_adapter import switch_adapter

router = APIRouter(prefix="/switch", tags=["switch"])


@router.get("/status")
async def get_switch_status():
    """Check connectivity to the configured Switch server."""
    is_healthy = await switch_adapter.check_health()
    return {
        "switch_base_url": switch_adapter.base_url,
        "connected": is_healthy,
        "registered_agents": list(switch_adapter._registered_agents.keys()),
        "active_rooms": list(switch_adapter._rooms.keys()),
    }


@router.post("/rooms")
async def create_switch_room(room_req: SwitchRoomCreate):
    """Create or associate a Switch room with an issue."""
    return await switch_adapter.create_or_join_room(room_req)


@router.post("/messages")
async def send_switch_message(payload: SwitchMessagePayload):
    """Post an agent message into a Switch issue room."""
    ok = await switch_adapter.send_message(payload)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to deliver message to Switch",
        )
    return {"status": "delivered", "room_id": payload.room_id}


@router.post("/handoff")
async def trigger_switch_handoff(handoff: SwitchHandoff):
    """Trigger a targeted task handoff in Switch."""
    ok = await switch_adapter.route_handoff(handoff)
    return {"status": "routed", "to_role": handoff.to_role}

