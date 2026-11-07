"""
PRAGMATA Demo Flow — Realistic Edition
Tailored for hackathon video recording with Switch Console and/or Slack.

Features:
- Realistic pacing (~3s per phase, ~32s total flow)
- Rich, highly realistic engineering dialogue, code snippets, test outputs, diffs
- Dual publishing:
    1. Switch Console desktop app (/gateway/rooms and /gateway/chats)
    2. Optional Slack Incoming Webhook (posts live to real Slack channel)
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from backend.app.api.gateway import _STORED_ROOMS, _build_room_detail

router = APIRouter(prefix="/demo", tags=["Demo"])
logger = logging.getLogger(__name__)

DEMO_ROOM_ID = "demo-room-pragmata-001"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

DEMO_ISSUE = {
    "id": "demo-001",
    "title": "SAVE20 discount coupon not applying on $100 cart",
    "description": (
        "When a customer adds $100 worth of merchandise (e.g. 1x Headphones at $100) and applies "
        "the SAVE20 promo coupon, the subtotal is calculated as $100 and the final total remains $100 "
        "instead of the expected $80 (20% discount). Customers are complaining they don't get the discount."
    ),
    "expected_behavior": "Orders of $100 or greater qualify for 20% discount with code SAVE20. Final total must be $80.00.",
    "steps_attempted": (
        "1. Open cart, add 1x Headphones ($100.00)\n"
        "2. Apply coupon code 'SAVE20'\n"
        "3. Proceed to checkout: cart displays $100.00 instead of $80.00"
    ),
    "status": "RECEIVED",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "reporter_environment": {"browser": "Chrome 122.0.6261.94", "os": "Windows 11 x64"},
    "conversations": [],
}

# ── Detailed, Realistic Agent Workflow ──────────────────────────────────────────

REALISTIC_SCRIPT: List[Dict[str, Any]] = [
    # ── Phase 1: Intake & Structuring ───────────────────────────────────────────
    {
        "phase": "INTAKE",
        "agent": "🎫 Intake Agent",
        "delay": 2.5,
        "message": (
            "📋 **Bug Report Intake & Structuring** (`demo-001`)\n\n"
            "**Title:** `SAVE20 discount coupon not applying on $100 cart`\n"
            "**Component:** `checkout / pricing-engine`\n"
            "**Severity:** P2 - Revenue Impact\n"
            "**Reporter Environment:** Chrome 122 on Windows 11\n\n"
            "**Structured Hypothesis:**\n"
            "> Cart subtotal validation logic fails boundary condition when subtotal exactly equals the minimum coupon threshold ($100.00).\n\n"
            "Assigning task to **Investigator Agent** for repository inspection."
        ),
        "issue_status": "INVESTIGATING",
    },
    # ── Phase 2: Static Code Investigation ──────────────────────────────────────
    {
        "phase": "INVESTIGATION",
        "agent": "🔍 Investigator Agent",
        "delay": 3.2,
        "message": (
            "🔎 **Repository Static Analysis & AST Inspection**\n\n"
            "Inspecting target repository: `demo/sample-node-cart`\n"
            "`git grep -n \"discountRate\"` &rarr; matched `src/cart.js:14,29`\n\n"
            "📍 **Offending code located in `src/cart.js:27-33`:**\n"
            "```javascript\n"
            "27:  getTotal() {\n"
            "28:    const subtotal = this.getSubtotal();\n"
            "29:    // BUG: Strictly greater than instead of greater-than-or-equal-to\n"
            "30:    if (subtotal > 100 && this.discountRate > 0) {\n"
            "31:      return subtotal * (1 - this.discountRate);\n"
            "32:    }\n"
            "33:    return subtotal;\n"
            "```\n\n"
            "⚠️ **Finding:** Boundary check uses strict inequality (`subtotal > 100`).\n"
            "When `subtotal === 100`, conditional evaluates to `false` and bypasses the discount.\n"
            "**Confidence Score:** 98.4%\n"
            "Handoff to **Reproducer Agent** to confirm in isolated Docker sandbox."
        ),
        "issue_status": "INVESTIGATING",
    },
    # ── Phase 3: Reproduction in Sandbox ────────────────────────────────────────
    {
        "phase": "REPRODUCTION",
        "agent": "🧪 Reproducer Agent",
        "delay": 3.5,
        "message": (
            "🐳 **Docker Sandbox Reproduction Run**\n\n"
            "Executing test suite: `node --test tests/cart.test.js`\n\n"
            "```console\n"
            "$ node --test tests/cart.test.js\n"
            "▶ Cart calculates total for standard items\n"
            "✔ Cart calculates total for standard items (1.42ms)\n"
            "▶ Cart applies 20% discount on orders of $100 or more with SAVE20 coupon\n"
            "✖ Cart applies 20% discount on orders of $100 or more with SAVE20 coupon (2.11ms)\n"
            "  AssertionError [ERR_ASSERTION]: Expected values to be strictly equal:\n"
            "  100 !== 80\n"
            "     at TestContext.<anonymous> (demo/sample-node-cart/tests/cart.test.js:16:10)\n"
            "ℹ tests 2 | pass 1 | fail 1 | cancelled 0 | duration 14.8ms\n"
            "```\n\n"
            "🔴 **REPRODUCED:** Test fails deterministically with `100 !== 80`.\n"
            "Evidence snapshot captured and persisted to PostgreSQL.\n"
            "Escalating to **Developer Triage Gate**."
        ),
        "issue_status": "AWAITING_DEVELOPER_TRIAGE",
    },
    # ── Phase 4: Human Developer Triage Gate ────────────────────────────────────
    {
        "phase": "TRIAGE",
        "agent": "👤 Developer (Human Authority Gate)",
        "delay": 2.8,
        "message": (
            "✅ **Developer Triage Gate: Issue Accepted**\n\n"
            "**Reviewer:** `developer@pragmata.internal`\n"
            "**Decision:** `ACCEPTED`\n"
            "**Notes:** Verified reproduction output. The discount threshold specification requires `$100 or more`, so `$100` must receive the 20% discount. Authorized for fix strategy deliberation."
        ),
        "issue_status": "ACCEPTED",
    },
    # ── Phase 5: Root Cause Analysis (RCA) ──────────────────────────────────────
    {
        "phase": "RCA",
        "agent": "🧠 Resolution Lead",
        "delay": 3.0,
        "message": (
            "📊 **Root Cause Analysis & Blast Radius Assessment**\n\n"
            "- **Root Cause:** Inverted boundary relational operator (`>` instead of `>=`) in `ShoppingCart.getTotal()`.\n"
            "- **Blast Radius:** Single function scope. `addItem()`, `applyDiscount()`, `getSubtotal()` are unaffected.\n"
            "- **Affected Component:** `src/cart.js` line 30.\n"
            "- **Regression Risk:** Low (covered by unit test suite).\n\n"
            "Initiating fix strategy proposal debate between **Architect** and **Scope Guardian**."
        ),
        "issue_status": "ROOT_CAUSE_ANALYSIS",
    },
    # ── Phase 6: Multi-Agent Fix Strategy Debate ────────────────────────────────
    {
        "phase": "FIX_DEBATE",
        "agent": "🏛️ Architect Agent",
        "delay": 3.2,
        "message": (
            "💡 **Fix Strategy Proposal: Option A (Recommended)**\n\n"
            "Modify conditional boundary in `src/cart.js`: replace `>` with `>=`.\n\n"
            "```diff\n"
            "-    if (subtotal > 100 && this.discountRate > 0) {\n"
            "+    if (subtotal >= 100 && this.discountRate > 0) {\n"
            "```\n\n"
            "**Alternative Considered (Option B):** Extract threshold to configurable constant `MINIMUM_DISCOUNT_THRESHOLD = 100`.\n"
            "**Recommendation:** Option A maintains maximum simplicity and directly satisfies the rubric without overengineering."
        ),
        "issue_status": "FIX_STRATEGY_DISCUSSION",
    },
    {
        "phase": "FIX_DEBATE",
        "agent": "🛡️ Scope Guardian",
        "delay": 2.5,
        "message": (
            "🛡️ **Scope Guardian Review**\n\n"
            "Evaluating Option A against PRAGMATA Safety Rubric:\n"
            "• **Diff Size:** 1 line changed, 0 added, 0 deleted\n"
            "• **Schema Migration Needed:** No\n"
            "• **Public API Surface Changed:** No\n"
            "• **Scope Creep Score:** 0.0 / 10 (Clean boundary repair)\n\n"
            "**Recommendation:** APPROVED. Ready for developer sign-off."
        ),
        "issue_status": "FIX_STRATEGY_DISCUSSION",
    },
    # ── Phase 7: Developer Fix Approval Gate ────────────────────────────────────
    {
        "phase": "FIX_APPROVAL",
        "agent": "👤 Developer (Human Authority Gate)",
        "delay": 2.6,
        "message": (
            "🎯 **Developer Fix Approval Gate: Strategy Confirmed**\n\n"
            "**Selected Strategy:** `Option A (Boundary condition repair: >= 100)`\n"
            "**Authorization:** Granted implementation clearance.\n"
            "Dispatching **Implementer Agent** to patch codebase."
        ),
        "issue_status": "AWAITING_FIX_APPROVAL",
    },
    # ── Phase 8: Code Implementation ───────────────────────────────────────────
    {
        "phase": "IMPLEMENTATION",
        "agent": "🔧 Implementer Agent",
        "delay": 3.5,
        "message": (
            "🔨 **Patch Applied to Workspace**\n\n"
            "Branch created: `pragmata/fix-cart-discount-boundary`\n"
            "Target: `demo/sample-node-cart/src/cart.js`\n\n"
            "```diff\n"
            "diff --git a/src/cart.js b/src/cart.js\n"
            "index 7a3c8e..9b4f21 100644\n"
            "--- a/src/cart.js\n"
            "+++ b/src/cart.js\n"
            "@@ -27,7 +27,7 @@ class ShoppingCart {\n"
            "   getTotal() {\n"
            "     const subtotal = this.getSubtotal();\n"
            "-    if (subtotal > 100 && this.discountRate > 0) {\n"
            "+    if (subtotal >= 100 && this.discountRate > 0) {\n"
            "       return subtotal * (1 - this.discountRate);\n"
            "     }\n"
            "     return subtotal;\n"
            "```\n\n"
            "Patch verified in working tree. Passing to **Verifier Agent** for test suite execution."
        ),
        "issue_status": "IMPLEMENTING",
    },
    # ── Phase 9: Verification & Resolution ──────────────────────────────────────
    {
        "phase": "VERIFICATION",
        "agent": "✅ Verifier Agent",
        "delay": 3.2,
        "message": (
            "🏁 **Full Verification Suite Passed**\n\n"
            "Executing clean test run in isolated sandbox:\n"
            "```console\n"
            "$ node --test tests/cart.test.js\n"
            "▶ Cart calculates total for standard items\n"
            "✔ Cart calculates total for standard items (1.23ms)\n"
            "▶ Cart applies 20% discount on orders of $100 or more with SAVE20 coupon\n"
            "✔ Cart applies 20% discount on orders of $100 or more with SAVE20 coupon (0.91ms)\n"
            "ℹ tests 2 | pass 2 | fail 0 | cancelled 0 | duration 12.1ms\n"
            "```\n\n"
            "✨ **Results:**\n"
            "- 2 of 2 unit tests passed (0 failures)\n"
            "- Reproduction test verified: `$100 * 0.8 = $80.00` ✅\n"
            "- Regression test: Clean ✅\n\n"
            "🎉 **Issue `demo-001` marked as RESOLVED.**\n"
            "Workflow complete. All audit evidence committed to PostgreSQL."
        ),
        "issue_status": "RESOLVED",
    },
]

# ── In-Memory Demo State ────────────────────────────────────────────────────────

_demo_state: Dict[str, Any] = {
    "running": False,
    "speed": "realistic",
    "log": [],
    "issue": None,
    "room_id": DEMO_ROOM_ID,
    "slack_webhook": None,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Pre-register the demo room so it shows in Switch Console immediately on startup
def _ensure_demo_room():
    if DEMO_ROOM_ID not in _STORED_ROOMS:
        _STORED_ROOMS[DEMO_ROOM_ID] = _build_room_detail(
            DEMO_ROOM_ID,
            "PRAGMATA — Bug Investigation (demo-001)",
            "Active collaborative room for cart discount bug investigation & resolution",
            instructions="PRAGMATA multi-agent bug resolution room. Agents coordinate and report evidence here.",
            agent_ids=[
                "pragmata-orchestrator",
                "pragmata-triage",
                "pragmata-reproducer",
                "pragmata-resolution",
                "pragmata-scope-guardian",
                "pragmata-implementer",
                "pragmata-verifier",
            ],
        )
        _STORED_ROOMS[DEMO_ROOM_ID]["_messages"] = [
            {
                "id": "msg_intro_001",
                "room_id": DEMO_ROOM_ID,
                "sender": "🤖 PRAGMATA Orchestrator",
                "content": (
                    "**PRAGMATA Agent Collaboration Room Ready**\n\n"
                    "Monitoring issue `demo-001`: *SAVE20 discount coupon not applying on $100 cart*.\n"
                    "Connected agents: Orchestrator, Triage, Reproducer, Resolution Lead, Scope Guardian, Implementer, Verifier.\n"
                    "Awaiting demo trigger."
                ),
                "created_at": _now(),
            }
        ]


_ensure_demo_room()


async def _send_to_slack(webhook_url: str, agent: str, message: str):
    """Post formatted message to Slack webhook if configured."""
    if not webhook_url:
        return
    try:
        payload = {
            "text": f"*{agent}*\n{message}",
            "mrkdwn": True,
        }
        async with httpx.AsyncClient(timeout=3.0) as client:
            await client.post(webhook_url, json=payload)
    except Exception as ex:
        logger.warning(f"Slack post failed: {ex}")


async def _post_agent_message(room_id: str, agent: str, content: str, slack_url: Optional[str] = None):
    _ensure_demo_room()
    msg = {
        "id": f"msg_{uuid.uuid4().hex[:8]}",
        "room_id": room_id,
        "sender": agent,
        "content": content,
        "created_at": _now(),
    }
    _STORED_ROOMS[room_id]["_messages"].append(msg)

    # If Slack webhook is active, post to Slack too
    if slack_url:
        await _send_to_slack(slack_url, agent, content)

    logger.info(f"[{agent}]: {content[:70]}...")
    return msg


async def _run_demo_flow_task(speed_multiplier: float, slack_url: Optional[str] = None):
    global _demo_state
    _demo_state["running"] = True
    _demo_state["log"] = []
    _demo_state["issue"] = dict(DEMO_ISSUE)

    # Initial kickoff message
    await _post_agent_message(
        DEMO_ROOM_ID,
        "🤖 PRAGMATA Orchestrator",
        (
            "⚡ **Workflow Dispatched: Issue `demo-001`**\n\n"
            "Problem: SAVE20 discount coupon not applying on $100 cart\n"
            "Target Repo: `demo/sample-node-cart` (Node.js)\n"
            "Human Gates: Developer Triage (Phase 4), Fix Approval (Phase 7)\n"
            "Begin multi-agent investigation sequence."
        ),
        slack_url=slack_url,
    )

    for step in REALISTIC_SCRIPT:
        # Realistic sleep between agents
        await asyncio.sleep(step["delay"] * speed_multiplier)

        _demo_state["issue"]["status"] = step["issue_status"]
        msg = await _post_agent_message(DEMO_ROOM_ID, step["agent"], step["message"], slack_url=slack_url)

        _demo_state["log"].append({
            "phase": step["phase"],
            "agent": step["agent"],
            "status": step["issue_status"],
            "message": step["message"],
            "timestamp": msg["created_at"],
        })

    _demo_state["running"] = False
    logger.info("Demo execution completed successfully.")


# ── Request / Response Schemas ──────────────────────────────────────────────────


class RunDemoRequest(BaseModel):
    speed: Optional[str] = "realistic"  # "realistic" (~3s/step), "fast" (~0.8s/step)
    slack_webhook_url: Optional[str] = None


# ── Endpoints ───────────────────────────────────────────────────────────────────


@router.post("/run", status_code=202)
async def run_demo(req: Optional[RunDemoRequest] = None):
    if _demo_state["running"]:
        return {"status": "already_running", "room_id": DEMO_ROOM_ID}

    speed_mode = req.speed if req and req.speed else "realistic"
    speed_multiplier = 0.3 if speed_mode == "fast" else 1.0

    slack_url = (req.slack_webhook_url if req and req.slack_webhook_url else None) or SLACK_WEBHOOK_URL
    _demo_state["slack_webhook"] = slack_url

    # Reset log and room messages before starting
    _demo_state["log"] = []
    if DEMO_ROOM_ID in _STORED_ROOMS:
        _STORED_ROOMS[DEMO_ROOM_ID]["_messages"] = []

    asyncio.create_task(_run_demo_flow_task(speed_multiplier, slack_url=slack_url))

    return {
        "status": "started",
        "speed": speed_mode,
        "slack_enabled": bool(slack_url),
        "room_id": DEMO_ROOM_ID,
        "message": (
            "Demo running! Open Switch Console (or watch Slack) to see the dialogue live."
            if slack_url
            else "Demo running! Open Switch Console to see the dialogue live."
        ),
    }


@router.get("/status")
async def get_demo_status():
    return {
        "running": _demo_state["running"],
        "room_id": DEMO_ROOM_ID,
        "issue": _demo_state["issue"],
        "steps_completed": len(_demo_state["log"]),
        "total_steps": len(REALISTIC_SCRIPT) + 1,
        "slack_enabled": bool(_demo_state.get("slack_webhook")),
        "log": _demo_state["log"],
    }


@router.get("/room/messages")
async def get_demo_room_messages():
    room = _STORED_ROOMS.get(DEMO_ROOM_ID, {})
    return room.get("_messages", [])


@router.post("/reset")
async def reset_demo():
    _demo_state["running"] = False
    _demo_state["log"] = []
    _demo_state["issue"] = None
    _ensure_demo_room()
    return {"status": "reset"}
