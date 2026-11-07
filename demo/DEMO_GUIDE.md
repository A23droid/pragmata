# PRAGMATA — Video Demo Guide & Script

This document explains the end-to-end bug investigation and resolution demo for PRAGMATA, including setup instructions, video layout, spoken script, and technical details.

---

## 1. What This Demo Proves

PRAGMATA turns an unstructured bug report into a verified, developer-approved code change following core principles:
1. **Evidence Before Certainty:** Reproduction is attempted in an isolated sandbox before engineering work begins.
2. **Human Authority Gates:** Consequential decisions (Issue Acceptance & Fix Approval) require developer sign-off.
3. **Switch-Native Collaboration:** Specialized AI agents collaborate in real-time rooms visible in the Switch Console desktop app and/or Slack.
4. **Verified Completion:** Code changes are not complete until automated regression tests pass.

---

## 2. The Target Bug (`demo/sample-node-cart`)

- **Target File:** `demo/sample-node-cart/src/cart.js`
- **Component:** Pricing & Discount Engine
- **The Defect (Line 30):**
  ```javascript
  // BUG: Strict inequality excludes orders totalling exactly $100
  if (subtotal > 100 && this.discountRate > 0) {
    return subtotal * (1 - this.discountRate);
  }
  ```
- **The Impact:** When a customer orders exactly $100 with code `SAVE20` (20% off $100+), they receive $0 discount.
- **The Reproduction Test (`demo/sample-node-cart/tests/cart.test.js`):**
  ```javascript
  assert.strictEqual(cart.getTotal(), 80); // Fails with AssertionError: 100 !== 80
  ```
- **The Verified Fix:**
  ```javascript
  if (subtotal >= 100 && this.discountRate > 0) {
  ```

---

## 3. Screen Layout for Recording

For the best hackathon video presentation, use a split-screen layout:

```
┌─────────────────────────────────┬─────────────────────────────────┐
│                                 │                                 │
│        PRAGMATA Web UI          │      Switch Console Desktop     │
│    http://localhost:3000/demo   │           (or Slack)            │
│                                 │                                 │
│  • Bug Report Card              │  • Room: #pragmata-demo-001     │
│  • 9-Phase Workflow Pipeline    │  • Live Agent Stream            │
│  • Real-time Progress Bar       │  • Terminal Outputs & Diffs     │
│                                 │                                 │
└─────────────────────────────────┴─────────────────────────────────┘
```

---

## 4. Step-by-Step Recording Instructions

### Step 1: Start Backend (Terminal 1)
```powershell
cd d:\pragmata\pragmata
.\backend\.venv\Scripts\uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Step 2: Start Frontend (Terminal 2)
```powershell
cd d:\pragmata\pragmata\frontend
npm run dev
```

### Step 3: Open Apps
1. Open your browser to **`http://localhost:3000/demo`**.
2. Open the **Switch Console** desktop app and connect to `http://localhost:8000`. Select room `#pragmata-demo-001`.
   *(Optional: If using Slack, paste your Slack Incoming Webhook URL in the top banner on the web page).*

### Step 4: Click "Launch Multi-Agent Workflow" & Record
Click the button on the web page. Over the next ~32 seconds, watch the 9 phases advance on the left while all agent findings stream live on the right.

---

## 5. Voiceover / Narration Script (~60–90 seconds)

> **[0:00 - 0:15] Introduction & Intake**  
> *"Welcome to PRAGMATA. In this demo, an unstructured bug report arrives from an e-commerce customer: the SAVE20 promo coupon isn't giving them 20% off their $100 order. As we click 'Launch', our Intake Agent structures the problem, tags the checkout component, and routes it to the investigator."*

> **[0:15 - 0:30] Static Analysis & Sandbox Reproduction**  
> *"The Investigator Agent scans the repository AST and pinpoints line 30 of cart.js with 98% confidence: a boundary defect using `>` instead of `>=`. Next, our Reproducer Agent spins up an isolated Docker sandbox and executes the test suite—confirming the deterministic failure: 100 !== 80."*

> **[0:30 - 0:45] Human Authority Gate 1 & Fix Deliberation**  
> *"PRAGMATA enforces human authority: before any code changes can occur, the developer reviews the sandbox evidence and officially accepts the bug. Our Resolution Lead conducts root cause analysis, while the Architect and Scope Guardian debate fix options in Switch to prevent scope creep."*

> **[0:45 - 1:05] Human Authority Gate 2, Patching & Verification**  
> *"The developer approves the minimal boundary repair strategy. The Implementer Agent creates a branch and patches the code. Finally, the Verifier Agent re-runs the full test suite in the sandbox: all tests pass, zero regressions, and the issue is marked RESOLVED."*

> **[1:05 - 1:15] Closing**  
> *"Everything you see is synchronized in real-time between PRAGMATA's deterministic state machine and the Switch Console desktop app. Investigate, deliberate, resolve—this is PRAGMATA."*

---

## 6. The 9 Workflow Phases

| Phase | Agent / Actor | Output Artifact |
|---|---|---|
| **1. INTAKE** | 🎫 Intake Agent | Structured intake report, component tag, severity P2 |
| **2. INVESTIGATION** | 🔍 Investigator Agent | Code citation `src/cart.js:30`, 98.4% confidence |
| **3. REPRODUCTION** | 🧪 Reproducer Agent | Sandbox test execution output, `100 !== 80` captured |
| **4. TRIAGE** | 👤 Developer (Human Gate) | Official decision `ACCEPTED`, engineering authorized |
| **5. RCA** | 🧠 Resolution Lead | Blast radius assessment (isolated to 1 function) |
| **6. FIX DEBATE** | 🏛️ Architect & 🛡️ Scope Guardian | Strategy Option A (`>= 100`), scope creep score 0.0/10 |
| **7. FIX APPROVAL** | 👤 Developer (Human Gate) | Explicit developer sign-off on Strategy Option A |
| **8. IMPLEMENTATION** | 🔧 Implementer Agent | Unified git diff patch applied on branch |
| **9. VERIFICATION** | ✅ Verifier Agent | Sandbox re-run: 2/2 tests passed, status `RESOLVED` |

---

## 7. API Endpoints Reference

- **Run Demo:** `POST /api/v1/demo/run`  
  Payload: `{"speed": "realistic", "slack_webhook_url": "..."}`
- **Poll Demo Status:** `GET /api/v1/demo/status`
- **Reset Demo:** `POST /api/v1/demo/reset`
- **Switch Room Messages:** `GET /gateway/rooms/{room_id}/messages`
- **Switch Console Chat Feed:** `GET /gateway/chats/{room_id}/messages`
