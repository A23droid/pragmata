"""
PRAGMATA Demo Flow — Branch 2
Hardcoded end-to-end demo for the hackathon video.

POST /api/v1/demo/run
  → Creates the demo issue (cart discount bug)
  → Runs every workflow phase with hardcoded responses
  → Posts each agent message to the Switch Console room in sequence
  → Returns the full log so the frontend can replay it

The Switch room is created automatically and all agent messages appear
live in Switch Console during the demo.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter

from backend.app.api.gateway import _STORED_ROOMS, _build_room_detail

router = APIRouter(prefix="/demo", tags=["Demo"])
logger = logging.getLogger(__name__)

# ── Hardcoded Demo Data ──────────────────────────────────────────────────────────

DEMO_ISSUE = {
    "id": "demo-001",
    "title": "SAVE20 discount coupon not applying on $100 cart",
    "description": (
        "When a customer adds a $100 item and applies the SAVE20 coupon, "
        "the total stays at $100 instead of becoming $80. The 20% discount "
        "is completely ignored for carts that total exactly $100."
    ),
    "expected_behavior": "Cart total should be $80 after applying SAVE20 coupon on a $100 order.",
    "steps_attempted": "1. Add Headphones ($100) to cart\n2. Apply coupon SAVE20\n3. Checkout — total shows $100 (expected $80)",
    "status": "RECEIVED",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "reporter_environment": {"browser": "Chrome 120", "os": "Windows 11"},
    "conversations": [],
}

DEMO_ROOM_ID = "demo-room-pragmata-001"

DEMO_SCRIPT: List[Dict[str, Any]] = [
    # ── Phase 1: Intake ──────────────────────────────────────────────────────────
    {
        "phase": "INTAKE",
        "agent": "🎫 Intake Agent",
        "delay": 0.4,
        "message": (
            "**New bug report received — `demo-001`**\n\n"
            "> *SAVE20 discount coupon not applying on \\$100 cart*\n\n"
            "Reporter: Chrome 120 / Windows 11\n"
            "Structured intake complete. Routing to Investigation Lead."
        ),
        "issue_status": "INVESTIGATING",
    },
    # ── Phase 2: Investigation ───────────────────────────────────────────────────
    {
        "phase": "INVESTIGATION",
        "agent": "🔍 Investigator Agent",
        "delay": 0.8,
        "message": (
            "**Repository scan — `demo/sample-node-cart/src/cart.js`**\n\n"
            "Found suspicious comparison on line 30:\n"
            "```js\n"
            "// BUG: should be >= 100, not > 100\n"
            "if (subtotal > 100 && this.discountRate > 0) {\n"
            "```\n"
            "A cart totalling **exactly \\$100** passes the guard condition as *false* → discount never applied.\n"
            "Confidence: **96%**. Routing to Reproducer."
        ),
        "issue_status": "INVESTIGATING",
    },
    # ── Phase 3: Reproduction ────────────────────────────────────────────────────
    {
        "phase": "REPRODUCTION",
        "agent": "🧪 Reproducer Agent",
        "delay": 1.0,
        "message": (
            "**Sandbox execution — `node --test tests/cart.test.js`**\n\n"
            "```\n"
            "✗ Cart applies 20% discount on orders of $100 or more with SAVE20 coupon\n"
            "  AssertionError [ERR_ASSERTION]: 100 !== 80\n"
            "  at TestContext.<anonymous> (tests/cart.test.js:16:10)\n"
            "```\n"
            "**Bug reproduced.** Exact failure: `100 !== 80` on line 16.\n"
            "Evidence stored → PostgreSQL. Flagging for developer triage."
        ),
        "issue_status": "AWAITING_DEVELOPER_TRIAGE",
    },
    # ── Phase 4: Developer Triage (Human Gate) ───────────────────────────────────
    {
        "phase": "TRIAGE",
        "agent": "👤 Developer (Human Gate)",
        "delay": 0.6,
        "message": (
            "**✅ Issue accepted — developer approved for fix**\n\n"
            "Root cause confirmed: off-by-one comparison (`>` instead of `>=`) in `getTotal()`.\n"
            "Authorising resolution debate."
        ),
        "issue_status": "ACCEPTED",
    },
    # ── Phase 5: Root Cause Analysis ────────────────────────────────────────────
    {
        "phase": "RCA",
        "agent": "🧠 Resolution Lead",
        "delay": 0.8,
        "message": (
            "**Root Cause Analysis complete**\n\n"
            "- **Root Cause:** Strict inequality `> 100` in `ShoppingCart.getTotal()` excludes edge case where `subtotal === 100`.\n"
            "- **Blast Radius:** Isolated to `getTotal()` — no side effects on `addItem()`, `applyDiscount()`, or `getSubtotal()`.\n"
            "- **Fix Risk:** Minimal — single character change, fully covered by existing test suite."
        ),
        "issue_status": "ROOT_CAUSE_ANALYSIS",
    },
    # ── Phase 6: Fix Strategy Debate ────────────────────────────────────────────
    {
        "phase": "FIX_DEBATE",
        "agent": "⚔️ Architect Agent",
        "delay": 0.6,
        "message": (
            "**Strategy A — Minimal boundary fix** *(recommended)*\n\n"
            "```diff\n"
            "-  if (subtotal > 100 && this.discountRate > 0) {\n"
            "+  if (subtotal >= 100 && this.discountRate > 0) {\n"
            "```\n"
            "1-line change. Directly addresses root cause. Zero scope creep. Test passes immediately."
        ),
        "issue_status": "FIX_STRATEGY_DISCUSSION",
    },
    {
        "phase": "FIX_DEBATE",
        "agent": "🛡️ Scope Guardian",
        "delay": 0.5,
        "message": (
            "**Scope review — Strategy A approved**\n\n"
            "Blast radius: 1 line in 1 file. No API changes, no schema changes, no dependency changes.\n"
            "Risk score: **LOW**. No objections. Proceeding."
        ),
        "issue_status": "FIX_STRATEGY_DISCUSSION",
    },
    # ── Phase 7: Fix Approval (Human Gate) ──────────────────────────────────────
    {
        "phase": "FIX_APPROVAL",
        "agent": "👤 Developer (Human Gate)",
        "delay": 0.6,
        "message": (
            "**✅ Fix strategy approved**\n\n"
            "Approving Strategy A: change `> 100` to `>= 100` in `cart.js:30`.\n"
            "Authorising implementation."
        ),
        "issue_status": "AWAITING_FIX_APPROVAL",
    },
    # ── Phase 8: Implementation ──────────────────────────────────────────────────
    {
        "phase": "IMPLEMENTATION",
        "agent": "🔧 Implementer Agent",
        "delay": 1.2,
        "message": (
            "**Implementation complete**\n\n"
            "```diff\n"
            "--- a/demo/sample-node-cart/src/cart.js\n"
            "+++ b/demo/sample-node-cart/src/cart.js\n"
            "@@ -27,7 +27,7 @@\n"
            "   getTotal() {\n"
            "     const subtotal = this.getSubtotal();\n"
            "-    if (subtotal > 100 && this.discountRate > 0) {\n"
            "+    if (subtotal >= 100 && this.discountRate > 0) {\n"
            "       return subtotal * (1 - this.discountRate);\n"
            "     }\n"
            "```\n"
            "Patch applied. Handing off to Verifier."
        ),
        "issue_status": "IMPLEMENTING",
    },
    # ── Phase 9: Verification ────────────────────────────────────────────────────
    {
        "phase": "VERIFICATION",
        "agent": "✅ Verifier Agent",
        "delay": 1.0,
        "message": (
            "**All tests pass ✓**\n\n"
            "```\n"
            "✓ Cart calculates total for standard items\n"
            "✓ Cart applies 20% discount on orders of $100 or more with SAVE20 coupon\n\n"
            "2 tests passed — 0 failed\n"
            "```\n"
            "Regression check: clean. Issue **`demo-001` marked RESOLVED** ✅\n\n"
            "— PRAGMATA Workflow Complete"
        ),
        "issue_status": "RESOLVED",
    },
]


# ── In-memory demo state ─────────────────────────────────────────────────────────
_demo_state: Dict[str, Any] = {
    "running": False,
    "log": [],
    "issue": None,
    "room_id": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _post_to_switch_room(room_id: str, agent: str, message: str):
    """Store message in the in-memory Switch Console room."""
    if room_id not in _STORED_ROOMS:
        _STORED_ROOMS[room_id] = _build_room_detail(
            room_id,
            "PRAGMATA — Bug Investigation (demo-001)",
            "Automated demo flow: cart discount bug investigation & fix",
            instructions="This room is managed by PRAGMATA agents. Agents post their findings here as the investigation progresses.",
            agent_ids=["pragmata-orchestrator", "pragmata-triage", "pragmata-reproducer",
                       "pragmata-resolution", "pragmata-implementer", "pragmata-verifier"],
        )

    if "_messages" not in _STORED_ROOMS[room_id]:
        _STORED_ROOMS[room_id]["_messages"] = []

    msg = {
        "id": f"msg_{uuid.uuid4().hex[:8]}",
        "room_id": room_id,
        "sender": agent,
        "content": message,
        "created_at": _now(),
    }
    _STORED_ROOMS[room_id]["_messages"].append(msg)
    logger.info(f"[Switch Room {room_id}] {agent}: {message[:80]}...")
    return msg


async def _run_demo_flow():
    """Execute the hardcoded demo script end-to-end."""
    global _demo_state

    _demo_state["running"] = True
    _demo_state["log"] = []
    _demo_state["issue"] = dict(DEMO_ISSUE)
    _demo_state["room_id"] = DEMO_ROOM_ID

    # Provision the Switch room
    await _post_to_switch_room(
        DEMO_ROOM_ID,
        "🤖 PRAGMATA Orchestrator",
        (
            "**Bug report `demo-001` received — opening investigation room**\n\n"
            "Issue: *SAVE20 discount coupon not applying on $100 cart*\n"
            "Repo: `demo/sample-node-cart` · Stack: Node.js\n\n"
            "Dispatching agent team. All findings will be posted here.\n"
            "Developer, you will be pinged at triage and fix-approval gates."
        ),
    )

    for step in DEMO_SCRIPT:
        await asyncio.sleep(step["delay"])

        # Update issue status
        _demo_state["issue"]["status"] = step["issue_status"]

        # Post to Switch room
        msg = await _post_to_switch_room(DEMO_ROOM_ID, step["agent"], step["message"])

        # Record in log
        entry = {
            "phase": step["phase"],
            "agent": step["agent"],
            "status": step["issue_status"],
            "message": step["message"],
            "timestamp": msg["created_at"],
        }
        _demo_state["log"].append(entry)

    _demo_state["running"] = False
    logger.info("Demo flow complete — issue demo-001 RESOLVED")


# ── API Endpoints ────────────────────────────────────────────────────────────────


@router.post("/run", status_code=202)
async def run_demo():
    """
    Kick off the full hardcoded demo flow asynchronously.
    Messages are streamed into the Switch Console room in real time.
    Poll GET /api/v1/demo/status to watch progress.
    """
    if _demo_state["running"]:
        return {"status": "already_running", "room_id": _demo_state["room_id"]}

    # Reset state
    _demo_state["log"] = []
    _demo_state["issue"] = None

    # Fire off the demo flow as a background task (non-blocking)
    asyncio.create_task(_run_demo_flow())

    return {
        "status": "started",
        "room_id": DEMO_ROOM_ID,
        "switch_room_url": f"http://localhost:8000/gateway/rooms/{DEMO_ROOM_ID}",
        "poll_url": "http://localhost:8000/api/v1/demo/status",
        "message": "Demo flow started — open Switch Console and watch the PRAGMATA room.",
    }


@router.get("/status")
async def get_demo_status():
    """Live status of the running demo flow."""
    return {
        "running": _demo_state["running"],
        "room_id": _demo_state["room_id"],
        "issue": _demo_state["issue"],
        "steps_completed": len(_demo_state["log"]),
        "total_steps": len(DEMO_SCRIPT) + 1,  # +1 for orchestrator opener
        "log": _demo_state["log"],
    }


@router.get("/room/messages")
async def get_demo_room_messages():
    """All messages posted to the Switch Console demo room so far."""
    room = _STORED_ROOMS.get(DEMO_ROOM_ID, {})
    return room.get("_messages", [])


@router.post("/reset")
async def reset_demo():
    """Reset demo state so it can be re-run."""
    _demo_state["running"] = False
    _demo_state["log"] = []
    _demo_state["issue"] = None
    _demo_state["room_id"] = None
    _STORED_ROOMS.pop(DEMO_ROOM_ID, None)
    return {"status": "reset"}
