import pytest
from httpx import AsyncClient

from backend.app.models.enums import ChannelType
from backend.app.schemas.switch import (
    SwitchAgentRegistration,
    SwitchHandoff,
    SwitchMessagePayload,
    SwitchRoomCreate,
)
from backend.app.services.switch_adapter import SwitchAdapter


@pytest.mark.asyncio
async def test_switch_adapter_offline_graceful_degradation():
    """Ensure adapter handles an unreachable Switch server gracefully without raising errors."""
    adapter = SwitchAdapter(base_url="http://127.0.0.1:9999", registration_token="test_token")
    is_healthy = await adapter.check_health()
    assert is_healthy is False

    reg = SwitchAgentRegistration(
        agent_id="test_intake",
        display_name="Intake Lead",
        role="INTAKE_AGENT",
    )
    reg_result = await adapter.register_agent(reg)
    assert reg_result is True

    room = await adapter.create_or_join_room(
        SwitchRoomCreate(
            issue_id="issue-123",
            room_name="Investigation-123",
            channel_type=ChannelType.INVESTIGATION,
        )
    )
    assert room["room_id"] == "switch_room_issue-123_investigation"

    msg_sent = await adapter.send_message(
        SwitchMessagePayload(
            room_id=room["room_id"],
            sender_id="test_intake",
            sender_role="INTAKE_AGENT",
            content="Investigation started.",
        )
    )
    assert msg_sent is True

    handoff_ok = await adapter.route_handoff(
        SwitchHandoff(
            issue_id="issue-123",
            room_id=room["room_id"],
            from_role="INTAKE_AGENT",
            to_role="INVESTIGATOR",
            task_description="Locate bug in cart calculation",
        )
    )
    assert handoff_ok is True


@pytest.mark.asyncio
async def test_switch_api_agent_registration_and_status(async_client: AsyncClient):
    """Test registering an agent role via the REST API and checking status endpoint."""
    reg_payload = {
        "agent_id": "test-orchestrator",
        "display_name": "Test Orchestrator",
        "role": "ORCHESTRATOR",
        "capabilities": ["task_dispatch", "state_management"],
    }
    reg_res = await async_client.post("/api/v1/switch/agents", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["agent_id"] == "test-orchestrator"
    assert reg_data["role"] == "ORCHESTRATOR"

    status_res = await async_client.get("/api/v1/switch/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert "registered_agents" in status_data
    assert "test-orchestrator" in status_data["registered_agents"]


@pytest.mark.asyncio
async def test_issue_creation_provisions_and_persists_switch_rooms(async_client: AsyncClient):
    """
    Verify that when an issue is submitted:
    1. Three Switch rooms (INVESTIGATION, RESOLUTION, IMPLEMENTATION) are automatically provisioned.
    2. ConversationReference records are stored in PostgreSQL with stable IDs.
    3. Issue detail response contains all three conversation references.
    4. GET /api/v1/issues/{issue_id}/rooms returns the room mapping.
    """
    create_res = await async_client.post(
        "/api/v1/issues",
        json={
            "title": "Crash on file upload with large file",
            "description": "Uploading a 50MB PDF triggers a timeout and unhandled rejection.",
        },
    )
    assert create_res.status_code == 201
    issue_id = create_res.json()["id"]

    # Verify rooms via GET /api/v1/issues/{issue_id}/rooms
    rooms_res = await async_client.get(f"/api/v1/issues/{issue_id}/rooms")
    assert rooms_res.status_code == 200
    rooms = rooms_res.json()
    assert len(rooms) == 3

    channels = {r["channel_type"] for r in rooms}
    assert channels == {"INVESTIGATION", "RESOLUTION", "IMPLEMENTATION"}

    for r in rooms:
        expected_suffix = r["channel_type"].lower()
        assert r["room_id"] == f"switch_room_{issue_id}_{expected_suffix}"
        assert r["metadata"]["room_name"] != ""

    # Verify Issue detail includes conversations
    detail_res = await async_client.get(f"/api/v1/issues/{issue_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert "conversations" in detail
    assert len(detail["conversations"]) == 3
    conv_channels = [c["channel_type"] for c in detail["conversations"]]
    assert "INVESTIGATION" in conv_channels
    assert "RESOLUTION" in conv_channels
    assert "IMPLEMENTATION" in conv_channels
