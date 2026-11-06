import pytest
from httpx import AsyncClient

from backend.app.models.enums import ApprovalDecision, IssueStatus


@pytest.mark.asyncio
async def test_create_issue_minimal(async_client: AsyncClient):
    """Test plain-language intake with only required title and description."""
    payload = {
        "title": "Login button fails when clicked multiple times",
        "description": "Whenever I click login quickly twice, the spinner freezes and nothing happens.",
    }
    response = await async_client.post("/api/v1/issues", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"].startswith("PRAG-")
    assert data["title"] == payload["title"]
    assert data["description"] == payload["description"]
    assert data["status"] == IssueStatus.RECEIVED.value
    assert data["project_id"] is not None


@pytest.mark.asyncio
async def test_create_issue_incomplete_needs_information(async_client: AsyncClient):
    """Test that a report lacking essential description is marked NEEDS_INFORMATION."""
    payload = {
        "title": "Bug found",
        "description": "broken",  # < 10 characters
    }
    response = await async_client.post("/api/v1/issues", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == IssueStatus.NEEDS_INFORMATION.value


@pytest.mark.asyncio
async def test_list_and_get_issue_detail(async_client: AsyncClient):
    """Test issue listing and fetching detail with audit events."""
    create_res = await async_client.post(
        "/api/v1/issues",
        json={
            "title": "Checkout total incorrect with coupon",
            "description": "Applying a 10% coupon increases the total instead of decreasing it.",
            "expected_behavior": "Total should be reduced by 10%",
            "steps_attempted": "Added item to cart, entered coupon SAVE10",
            "reporter_environment": {"browser": "Firefox 125", "os": "Linux"},
        },
    )
    assert create_res.status_code == 201
    issue_id = create_res.json()["id"]

    # List
    list_res = await async_client.get("/api/v1/issues")
    assert list_res.status_code == 200
    issues = list_res.json()
    assert any(i["id"] == issue_id for i in issues)

    # Detail
    detail_res = await async_client.get(f"/api/v1/issues/{issue_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == issue_id
    assert detail["project"] is not None
    assert len(detail["audit_events"]) >= 1
    assert detail["audit_events"][0]["event_type"] == "ISSUE_SUBMITTED"


@pytest.mark.asyncio
async def test_deterministic_workflow_lifecycle_and_triage_gate(async_client: AsyncClient):
    """
    Test the full pre-approval lifecycle:
    RECEIVED -> INVESTIGATING -> REPRODUCING -> REPRODUCED -> AWAITING_DEVELOPER_TRIAGE
    Verify that developer triage gate permits ACCEPTED and rejects unauthorized bypass.
    """
    # 1. Create issue
    create_res = await async_client.post(
        "/api/v1/issues",
        json={
            "title": "Null pointer on empty profile update",
            "description": "Submitting profile form without avatar raises 500 error in API.",
        },
    )
    issue_id = create_res.json()["id"]

    # 2. Transition RECEIVED -> INVESTIGATING
    res1 = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "INVESTIGATING", "actor": "orchestrator", "reason": "Investigation assigned"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "INVESTIGATING"

    # 3. Transition INVESTIGATING -> REPRODUCING
    res2 = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "REPRODUCING", "actor": "reproducer", "reason": "Docker reproduction started"},
    )
    assert res2.status_code == 200
    assert res2.json()["status"] == "REPRODUCING"

    # 4. Transition REPRODUCING -> REPRODUCED
    res3 = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "REPRODUCED", "actor": "evidence_validator", "reason": "Behavior reproduced in sandbox"},
    )
    assert res3.status_code == 200
    assert res3.json()["status"] == "REPRODUCED"

    # 5. Transition REPRODUCED -> AWAITING_DEVELOPER_TRIAGE
    res4 = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "AWAITING_DEVELOPER_TRIAGE", "actor": "orchestrator", "reason": "Evidence presented to developer"},
    )
    assert res4.status_code == 200
    assert res4.json()["status"] == "AWAITING_DEVELOPER_TRIAGE"

    # 6. INVARIANT CHECK: Direct transition to ACCEPTED bypassing developer triage endpoint MUST FAIL (403 Forbidden)
    res_bypass = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "ACCEPTED", "actor": "rogue_agent", "reason": "Auto-accept attempt"},
    )
    assert res_bypass.status_code == 403

    # 7. INVARIANT CHECK: Transition to IMPLEMENTING directly MUST FAIL (Illegal transition 400)
    res_illegal = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "IMPLEMENTING", "actor": "rogue_agent"},
    )
    assert res_illegal.status_code == 400

    # 8. Unauthenticated Developer Triage MUST FAIL (401 Unauthorized)
    triage_unauth = await async_client.post(
        f"/api/v1/issues/{issue_id}/triage",
        json={"decision": "ACCEPTED", "actor": "spoofed_actor"},
    )
    assert triage_unauth.status_code == 401

    # 8b. Developer Triage with invalid token MUST FAIL (403 Forbidden)
    triage_invalid = await async_client.post(
        f"/api/v1/issues/{issue_id}/triage",
        headers={"Authorization": "Bearer invalid_secret_token"},
        json={"decision": "ACCEPTED", "actor": "spoofed_actor"},
    )
    assert triage_invalid.status_code == 403

    # 8c. Legitimate Developer Triage: Authenticated developer explicitly accepts issue
    dev_headers = {
        "Authorization": "Bearer dev-secret-key-pragmata",
        "X-Developer-Id": "developer@pragmata.internal",
    }
    triage_res = await async_client.post(
        f"/api/v1/issues/{issue_id}/triage",
        headers=dev_headers,
        json={
            "decision": "ACCEPTED",
            "notes": "Reproduced cleanly. Confirmed bug in ProfileService. Begin resolution.",
        },
    )
    assert triage_res.status_code == 200
    assert triage_res.json()["status"] == "ACCEPTED"

    # 9. Verify Audit Trail contains all transitions and human triage
    audit_res = await async_client.get(f"/api/v1/issues/{issue_id}/audit")
    assert audit_res.status_code == 200
    audits = audit_res.json()
    events = [a["event_type"] for a in audits]
    assert "ISSUE_SUBMITTED" in events
    assert "STATE_TRANSITION" in events
    assert "DEVELOPER_TRIAGE" in events

    last_audit = audits[-1]
    assert last_audit["event_type"] == "DEVELOPER_TRIAGE"
    assert last_audit["actor"] == "developer@pragmata.internal"
    assert last_audit["payload"]["decision"] == "ACCEPTED"


@pytest.mark.asyncio
async def test_developer_triage_rejections_and_deferrals(async_client: AsyncClient):
    """Test developer rejecting or deferring issues."""
    # Test Reject
    res1 = await async_client.post(
        "/api/v1/issues",
        json={"title": "Spam report", "description": "This is not an actual bug."},
    )
    issue_id1 = res1.json()["id"]
    await async_client.post(
        f"/api/v1/issues/{issue_id1}/transition",
        json={"target_status": "AWAITING_DEVELOPER_TRIAGE", "actor": "orchestrator"},
    )
    dev_headers = {"Authorization": "Bearer dev-secret-key-pragmata", "X-Developer-Id": "lead_dev"}
    triage_rej = await async_client.post(
        f"/api/v1/issues/{issue_id1}/triage",
        headers=dev_headers,
        json={"decision": "REJECTED", "notes": "Expected behavior by design."},
    )
    assert triage_rej.status_code == 200
    assert triage_rej.json()["status"] == "REJECTED"

    # Test Defer
    res2 = await async_client.post(
        "/api/v1/issues",
        json={"title": "Low priority cosmetic issue", "description": "Border radius 1px off."},
    )
    issue_id2 = res2.json()["id"]
    await async_client.post(
        f"/api/v1/issues/{issue_id2}/transition",
        json={"target_status": "AWAITING_DEVELOPER_TRIAGE", "actor": "orchestrator"},
    )
    triage_def = await async_client.post(
        f"/api/v1/issues/{issue_id2}/triage",
        headers=dev_headers,
        json={"decision": "DEFERRED", "notes": "Postpone until v2 redesign."},
    )
    assert triage_def.status_code == 200
    assert triage_def.json()["status"] == "DEFERRED"


@pytest.mark.asyncio
async def test_implementation_blocked_without_fix_approval(async_client: AsyncClient):
    """Verify that moving to IMPLEMENTING without a recorded FIX_STRATEGY approval is forbidden."""
    create_res = await async_client.post(
        "/api/v1/issues",
        json={"title": "Security bypass in token parsing", "description": "Algorithm NONE accepted in auth header."},
    )
    issue_id = create_res.json()["id"]

    # Move to ACCEPTED
    await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "AWAITING_DEVELOPER_TRIAGE", "actor": "orchestrator"},
    )
    dev_headers = {"Authorization": "Bearer dev-secret-key-pragmata", "X-Developer-Id": "security_lead"}
    triage_res = await async_client.post(
        f"/api/v1/issues/{issue_id}/triage",
        headers=dev_headers,
        json={"decision": "ACCEPTED"},
    )
    assert triage_res.status_code == 200

    # Move to RCA -> FIX_STRATEGY_DISCUSSION -> AWAITING_FIX_APPROVAL
    await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "ROOT_CAUSE_ANALYSIS", "actor": "resolution_lead"},
    )
    await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "FIX_STRATEGY_DISCUSSION", "actor": "architect"},
    )
    await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "AWAITING_FIX_APPROVAL", "actor": "resolution_lead"},
    )

    # Attempting to move to IMPLEMENTING without recorded approval must be rejected with 403
    imp_res = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "IMPLEMENTING", "actor": "implementer_agent"},
    )
    assert imp_res.status_code == 403
    assert "recorded developer fix approval" in imp_res.json()["detail"]
