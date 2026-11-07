import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Response, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class LoginPayload(BaseModel):
    email: Optional[str] = "dev@pragmata.local"
    password: Optional[str] = "password"


def _mock_user_response(email: str = "dev@pragmata.local"):
    return {
        "id": "usr_dev_pragmata",
        "name": email.split("@")[0].capitalize() if "@" in email else "Pragmata Developer",
        "email": email,
        "role": "admin",
        "created_at": "2026-01-01T00:00:00Z",
        "server": {
            "version": "0.31.0",
            "contracts": {},
        },
    }


DEFAULT_TENANT = {
    "id": "tenant_zero",
    "slug": "pragmata",
    "name": "PRAGMATA Workspace",
    "role": "owner",
}


# ── Auth & Session ───────────────────────────────────────────────────────────────


@router.get("/auth/config")
async def get_auth_config():
    """Sign-in options configuration probed by Switch Console client."""
    return {
        "password_login_enabled": True,
        "signup_enabled": True,
        "oidc_enabled": False,
        "oidc_provider_label": None,
        "oidc_login_options": [],
        "oidc_browser_handoff": False,
        "signup_mode": "open",
    }


@router.post("/auth/login")
async def login(response: Response, payload: Optional[Dict[str, Any]] = None):
    email = (payload or {}).get("email", "dev@pragmata.local") if isinstance(payload, dict) else "dev@pragmata.local"
    response.set_cookie(
        key="switch_auth",
        value="pragmata_switch_session_token",
        path="/",
        httponly=True,
    )
    return _mock_user_response(email)


@router.post("/auth/signup", status_code=201)
async def signup(response: Response, payload: Optional[Dict[str, Any]] = None):
    email = (payload or {}).get("email", "dev@pragmata.local") if isinstance(payload, dict) else "dev@pragmata.local"
    response.set_cookie(
        key="switch_auth",
        value="pragmata_switch_session_token",
        path="/",
        httponly=True,
    )
    user = _mock_user_response(email)
    return {
        **user,
        "machine": {
            "status": "ready",
            "reason": None,
        },
    }


@router.get("/auth/session")
async def get_session(request: Request):
    user = _mock_user_response()
    return {
        "state": "ready",
        "user": user,
        "tenant": {"id": DEFAULT_TENANT["id"], "name": DEFAULT_TENANT["name"]},
        "tenants": [DEFAULT_TENANT],
    }


@router.get("/auth/me")
async def get_me():
    return _mock_user_response()


@router.get("/auth/me/identities")
async def get_my_identities():
    return []


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("switch_auth", path="/")
    return {"ok": True}


# ── Tenants & Tenant Switching ──────────────────────────────────────────────────


@router.get("/tenants")
async def list_tenants():
    return [DEFAULT_TENANT]


@router.get("/tenants/current")
async def get_current_tenant():
    return {**DEFAULT_TENANT, "administers": True}


@router.post("/tenants/{tenant_id}/switch")
async def switch_tenant(tenant_id: str, response: Response):
    response.set_cookie(
        key="switch_auth",
        value=f"pragmata_{tenant_id}_token",
        path="/",
        httponly=True,
    )
    return _mock_user_response()


@router.get("/invitations/mine")
async def list_my_invitations():
    return []


@router.get("/joinable-tenants")
async def list_joinable_tenants():
    return []


# ── Trust Settings & Feature Flags ──────────────────────────────────────────────


@router.get("/trust-settings")
async def get_trust_settings():
    return {
        "endpoint": "http://localhost:8000/trust",
        "policy_id": None,
        "has_api_key": False,
        "api_key_last4": None,
        "enabled": False,
    }


@router.get("/feature-flags")
async def list_feature_flags():
    return {"flags": []}


# ── Collaborations & Messaging Apps ─────────────────────────────────────────────


@router.get("/collaborations")
async def list_collaborations():
    return [
        {
            "bridge_id": "install_switch_local",
            "bridge_type": "slack",
            "display_name": "Pragmata Collab",
            "status": "connected",
            "agent_greetings_enabled": False,
            "is_default": True,
            "preconfigured": True,
            "room_count": len(_STORED_ROOMS),
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]


@router.get("/collaborations/types")
async def list_collaboration_types():
    return []


@router.get("/messaging-apps")
async def list_messaging_apps():
    return {
        "platforms": ["slack", "discord", "matrix"],
        "claimable": [
            {"platform": "slack", "connected": True, "can_add_chat": True},
            {"platform": "discord", "connected": True, "can_add_chat": True},
            {"platform": "matrix", "connected": True, "can_add_chat": True},
        ],
    }


@router.post("/messaging-apps/{platform}/install")
async def install_messaging_app(platform: str):
    return {
        "id": f"install_{platform}_local",
        "platform": platform,
        "name": f"Pragmata {platform.capitalize()}",
        "connected": True,
    }


@router.post("/messaging-apps/{platform}/claim")
async def claim_messaging_app(platform: str):
    return {
        "url": f"http://localhost:8000/gateway/messaging-apps/{platform}/callback",
        "code": "pragmata_claim_code",
        "bot_handle": f"pragmata_bot_{platform}",
    }


@router.get("/messaging-apps/installs")
async def list_messaging_installs():
    return {
        "installs": [
            {
                "id": "install_switch_local",
                "platform": "slack",
                "name": "Pragmata Collab",
                "connected": True,
            }
        ]
    }


# ── Rooms & Agents (In-Memory Store synced with SwitchAdapter) ───────────────────

_STORED_ROOMS: Dict[str, Dict[str, Any]] = {}


def _build_room_detail(room_id: str, name: str, description: str = "", instructions: str = "", agent_ids: List[str] = None):
    agent_ids = agent_ids or []
    return {
        "id": room_id,
        "name": name,
        "description": description,
        "channel_type": "room",
        "admin_mode": False,
        "agent_count": len(agent_ids),
        "connected_user_count": 1,
        "connected_user_names": ["Pragmata Developer"],
        "bridge_id": "install_switch_local",
        "bridge_display_name": "Pragmata Collab",
        "bridge_type": "slack",
        "transport_room_id": f"transport_{room_id}",
        "matrix_room_id": f"!{room_id}:pragmata.local",
        "external_channel_id": None,
        "instructions": instructions,
        "protection_config": None,
        "observe_config": None,
        "agent_ids": agent_ids,
        "agent_statuses": {aid: "online" for aid in agent_ids},
        "roles": [],
        "join_event_listeners": [],
    }


@router.get("/rooms")
async def list_rooms():
    from backend.app.services.switch_adapter import switch_adapter
    # Combine rooms from switch_adapter and local console created rooms
    all_rooms = list(_STORED_ROOMS.values())
    for r_id, r in switch_adapter._rooms.items():
        if r_id not in _STORED_ROOMS:
            all_rooms.append(_build_room_detail(r_id, r.get("name", r_id), r.get("topic", "")))
    return all_rooms


@router.post("/rooms", status_code=201)
async def create_room(req: Dict[str, Any]):
    from backend.app.services.switch_adapter import switch_adapter
    room_id = f"room_{uuid.uuid4().hex[:8]}"
    name = req.get("name", "New Room")
    description = req.get("description", "")
    instructions = req.get("instructions", "")
    agent_ids = req.get("agents", []) or req.get("agent_ids", [])

    room_detail = _build_room_detail(room_id, name, description, instructions, agent_ids)
    _STORED_ROOMS[room_id] = room_detail

    # Sync into switch_adapter
    switch_adapter._rooms[room_id] = {
        "room_id": room_id,
        "name": name,
        "topic": description,
        "active": True,
        "members": agent_ids,
    }
    return room_detail


@router.get("/rooms/{room_id}")
async def get_room(room_id: str):
    if room_id in _STORED_ROOMS:
        return _STORED_ROOMS[room_id]
    return _build_room_detail(room_id, f"Room {room_id}")


@router.get("/rooms/{room_id}/messages")
async def get_room_messages(room_id: str):
    return []


@router.post("/rooms/{room_id}/messages", status_code=201)
async def post_room_message(room_id: str, msg: Dict[str, Any]):
    return {
        "id": f"msg_{uuid.uuid4().hex[:8]}",
        "room_id": room_id,
        "content": msg.get("content", ""),
        "sender": "usr_dev_pragmata",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/chats")
async def list_chats():
    return []


@router.get("/agents")
async def list_agents():
    # Return available system and investigation roles for Switch Console picker
    default_agents = [
        {"id": "pragmata-orchestrator", "name": "PRAGMATA Orchestrator", "role": "ORCHESTRATOR", "capabilities": ["workflow", "planning"], "status": "online"},
        {"id": "pragmata-triage", "name": "Triage Lead", "role": "TRIAGE", "capabilities": ["reproduction", "triage"], "status": "online"},
        {"id": "pragmata-reproducer", "name": "Reproduction Specialist", "role": "REPRODUCER", "capabilities": ["sandbox", "testing"], "status": "online"},
        {"id": "pragmata-resolution", "name": "Resolution Lead", "role": "RESOLUTION_LEAD", "capabilities": ["synthesis", "review"], "status": "online"},
        {"id": "pragmata-scope-guardian", "name": "Scope Guardian", "role": "SCOPE_GUARDIAN", "capabilities": ["blast_radius", "safety"], "status": "online"},
        {"id": "pragmata-rubric-evaluator", "name": "Rubric Evaluator", "role": "RUBRIC_EVALUATOR", "capabilities": ["scoring", "compliance"], "status": "online"},
        {"id": "pragmata-implementer", "name": "Implementation Specialist", "role": "IMPLEMENTER", "capabilities": ["patching", "git"], "status": "online"},
        {"id": "pragmata-verifier", "name": "Verification Specialist", "role": "VERIFIER", "capabilities": ["test_runner", "regression"], "status": "online"},
    ]
    return default_agents


@router.get("/management/agents")
async def list_management_agents():
    return await list_agents()

