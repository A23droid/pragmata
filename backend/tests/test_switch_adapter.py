import pytest
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

