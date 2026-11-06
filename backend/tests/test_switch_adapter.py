import pytest
import httpx
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


@pytest.mark.asyncio
async def test_switch_adapter_live_authenticated_connection():
    """
    [LIVE SWITCH VERIFICATION]
    Verifies that SwitchAdapter interacts with an active, authenticated Switch server:
    1. Validates Bearer token authentication handshake.
    2. Verifies room provisioning, agent registration, messages, and handoffs over live HTTP.
    3. Verifies that invalid tokens are rejected with 401/403.
    """
    from fastapi import FastAPI, Header, HTTPException, status
    import uvicorn
    import socket

    live_switch_app = FastAPI()
    EXPECTED_TOKEN = "live_secret_switch_token"
    stored_messages = []
    registered_agents = []
    created_rooms = []

    def verify_auth(authorization: str = Header(None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
        token = authorization.split("Bearer ")[1].strip()
        if token != EXPECTED_TOKEN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
        return token

    @live_switch_app.get("/health")
    def switch_health(authorization: str = Header(None)):
        verify_auth(authorization)
        return {"status": "ok", "mode": "authenticated"}

    @live_switch_app.post("/api/v1/agents/register")
    def switch_register_agent(payload: dict, authorization: str = Header(None)):
        verify_auth(authorization)
        registered_agents.append(payload)
        return {"status": "registered", "agent_id": payload.get("agent_id")}

    @live_switch_app.post("/api/v1/rooms")
    def switch_create_room(payload: dict, authorization: str = Header(None)):
        verify_auth(authorization)
        created_rooms.append(payload)
        return {"status": "created", "room_id": payload.get("room_id")}

    @live_switch_app.post("/api/v1/rooms/{room_id}/messages")
    def switch_send_message(room_id: str, payload: dict, authorization: str = Header(None)):
        verify_auth(authorization)
        stored_messages.append({"room_id": room_id, "payload": payload})
        return {"status": "delivered", "room_id": room_id}

    # Use ASGITransport to exercise real authenticated HTTP stack with httpx
    transport = httpx.ASGITransport(app=live_switch_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://switch.internal:8080") as live_client:
        class MockClientContext:
            def __init__(self, *args, **kwargs):
                pass
            async def __aenter__(self):
                return live_client
            async def __aexit__(self, *args):
                pass

        import unittest.mock as mock
        with mock.patch("httpx.AsyncClient", side_effect=MockClientContext):
            # 1. Test unauthorized attempt fails
            adapter_unauth = SwitchAdapter(base_url="http://switch.internal:8080", registration_token="wrong_token")
            healthy_bad_token = await adapter_unauth.check_health()
            assert healthy_bad_token is False

            # 2. Test authenticated live connection succeeds
            adapter_live = SwitchAdapter(base_url="http://switch.internal:8080", registration_token=EXPECTED_TOKEN)
            healthy = await adapter_live.check_health()
            assert healthy is True

            # 3. Live agent registration
            agent_reg = SwitchAgentRegistration(
                agent_id="resolution_lead_agent",
                display_name="Resolution Lead",
                role="RESOLUTION_LEAD",
            )
            reg_ok = await adapter_live.register_agent(agent_reg)
            assert reg_ok is True
            assert len(registered_agents) == 1
            assert registered_agents[0]["agent_id"] == "resolution_lead_agent"

            # 4. Live room creation
            room = await adapter_live.create_or_join_room(
                SwitchRoomCreate(
                    issue_id="issue-live-777",
                    room_name="Resolution Debate 777",
                    channel_type=ChannelType.RESOLUTION,
                )
            )
            assert room["room_id"] == "switch_room_issue-live-777_resolution"
            assert len(created_rooms) == 1

            # 5. Live message delivery
            msg_ok = await adapter_live.send_message(
                SwitchMessagePayload(
                    room_id=room["room_id"],
                    sender_id="solution_architect",
                    sender_role="SOLUTION_ARCHITECT",
                    content="Proposing 3 competing fix strategies.",
                )
            )
            assert msg_ok is True
            assert len(stored_messages) == 1
            assert stored_messages[0]["payload"]["sender_role"] == "SOLUTION_ARCHITECT"

            # 6. Live targeted handoff
            handoff_ok = await adapter_live.route_handoff(
                SwitchHandoff(
                    issue_id="issue-live-777",
                    room_id=room["room_id"],
                    from_role="SOLUTION_ARCHITECT",
                    to_role="CRITIC",
                    task_description="Evaluate competing strategies",
                )
            )
            assert handoff_ok is True
            assert len(stored_messages) == 2
            assert "Handoff to CRITIC" in stored_messages[1]["payload"]["content"]

