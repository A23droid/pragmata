import asyncio
import pytest
from httpx import AsyncClient
from backend.app.models.enums import IssueStatus


@pytest.mark.asyncio
async def test_issue_input_validation(async_client: AsyncClient):
    """Test validation rejection for invalid intake requests."""
    # Empty title
    res1 = await async_client.post("/api/v1/issues", json={"title": "", "description": "some description"})
    assert res1.status_code == 422

    # Short description
    res2 = await async_client.post("/api/v1/issues", json={"title": "Valid title", "description": "a"})
    assert res2.status_code == 422


@pytest.mark.asyncio
async def test_invalid_issue_transition_targets(async_client: AsyncClient):
    """Test that arbitrary non-existent statuses or illegal jumps are rejected."""
    create_res = await async_client.post(
        "/api/v1/issues",
        json={"title": "Arbitrary jump test", "description": "Testing illegal state transitions."},
    )
    issue_id = create_res.json()["id"]

    # Non-existent status
    res1 = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "SUPER_HERO_RESOLVED", "actor": "tester"},
    )
    assert res1.status_code == 422

    # Illegal jump from RECEIVED to RESOLVED
    res2 = await async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "RESOLVED", "actor": "tester"},
    )
    assert res2.status_code == 400


@pytest.mark.asyncio
async def test_concurrent_transitions(async_client: AsyncClient):
    """
    Test concurrent transition requests on the same issue.
    Due to row locking in the workflow engine, one transition succeeds and concurrent conflicting
    transitions from the same initial state are safely rejected or processed in sequence.
    """
    create_res = await async_client.post(
        "/api/v1/issues",
        json={"title": "Race condition check", "description": "Testing concurrent state transitions."},
    )
    issue_id = create_res.json()["id"]

    # Fire two concurrent transition attempts from RECEIVED:
    # 1. To INVESTIGATING
    # 2. To NEEDS_INFORMATION
    req1 = async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "INVESTIGATING", "actor": "worker_1"},
    )
    req2 = async_client.post(
        f"/api/v1/issues/{issue_id}/transition",
        json={"target_status": "NEEDS_INFORMATION", "actor": "worker_2"},
    )

    results = await asyncio.gather(req1, req2, return_exceptions=True)
    statuses = [r.status_code for r in results if not isinstance(r, Exception)]

    # At least one transition must succeed (200), and the database state remains consistent.
    assert 200 in statuses

    final_res = await async_client.get(f"/api/v1/issues/{issue_id}")
    assert final_res.status_code == 200
    assert final_res.json()["status"] in ["INVESTIGATING", "NEEDS_INFORMATION"]
