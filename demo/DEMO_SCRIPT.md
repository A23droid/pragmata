# PRAGMATA --- Hackathon Demo Walkthrough & Script

> **Investigate. Deliberate. Resolve.**
> 
> This document guides you through running the complete PRAGMATA end-to-end demonstration from an unstructured consumer bug report to a verified, developer-approved fix on an isolated Git branch.

---

## 1. Demo Scenario Overview

- **Target Repository:** `demo/sample-node-cart` (Node.js & TypeScript shopping cart)
- **Reported Defect:** A consumer applied promo code `SAVE20` ($20% off on orders of $100 or more) on a $100 cart, but was charged full price ($100 instead of $80).
- **Underlying Root Cause:** Off-by-one boundary comparison in `src/cart.js` (`subtotal > 100` instead of `subtotal >= 100`).
- **Reproduction Test:** `node --test tests/cart.test.js` (fails with `100 !== 80`).

---

## 2. Step-by-Step Demonstration Flow

### Step 1: Bug Intake (Consumer Surface)
1. Open the PRAGMATA Dashboard at `http://localhost:3000`.
2. Click **Submit Bug Report** (top right).
3. Fill in the consumer complaint in plain language:
   - **Title:** `Coupon SAVE20 does not work on my $100 cart`
   - **What happened:** `I added $100 of items and applied coupon SAVE20 which promises 20% off orders of $100 or more, but my total remained $100.`
   - **Expected behavior:** `Total should be $80.`
4. Click **Submit Report**.
   - Notice the issue is created with status `RECEIVED`.
   - Dedicated Switch rooms are provisioned (`switch_room_<id>_investigation`, `resolution`, `implementation`).

### Step 2: Multi-Agent Bug Investigation & Reproduction
1. In the issue detail view, observe the **Multi-Agent Bug Investigation (Phase 6)** card.
2. Click **Run Investigation Workflow**.
   - **Intake Agent:** Normalizes the report and extracts expected vs actual behavior.
   - **Investigator:** Scans the repository and localizes `src/cart.js` and `tests/cart.test.js`.
   - **Reproducer:** Formulates reproduction command `node --test tests/cart.test.js`.
   - **Evidence Validator:** Runs command in sandbox, observes exit code `1` and `100 !== 80`, confirming reproduction.
3. Status advances to `REPRODUCED` &rarr; `AWAITING_DEVELOPER_TRIAGE`.

### Step 3: Developer Triage Gate (Human Authority)
1. In the **Developer Triage Gate (Phase 6)** card, notice that resolution agents are **strictly locked** until developer approval.
2. Select **Accept & Begin Resolution**.
   - Status transitions to `ACCEPTED`.
   - Audit trail records timestamp and developer actor.

### Step 4: Resolution Hierarchy Debate & Scope Guardian
1. In the **Resolution Hierarchy & Fix Strategy Debate (Phase 7)** card, click **Trigger Multi-Agent Fix Debate**.
   - **Root Cause Analyst:** Pinpoints the defect in `ShoppingCart.getTotal()` (`subtotal > 100`).
   - **Solution Architect:** Proposes 2 distinct strategies (Boundary fix in `getTotal()` vs Configurable threshold rules).
   - **Critic:** Challenges strategies, verifies regression risk.
   - **Scope Guardian:** Audits proposals for overengineering, verifying that only `src/cart.js` is touched.
   - **Rubric Evaluator:** Scores proposals on Correctness, Security, Maintainability, and Complexity.
2. Status advances to `AWAITING_FIX_APPROVAL`.

### Step 5: Developer Fix Approval Gate
1. Review the ranked strategy cards.
2. Select **Rank #1: Correct Boundary Comparison** (or provide custom guidance).
3. Click **Approve Fix Strategy for Implementation**.
   - Formal approval is cryptographically verified and recorded in PostgreSQL.

### Step 6: Approved Implementation on Dedicated Branch
1. In the **Approved Implementation & Sandbox Verification (Phase 8)** card, click **Execute Approved Implementation**.
   - Implementer creates a dedicated Git branch `fix/pragmata-issue-<id>`.
   - Writes the minimal fix to `src/cart.js` (`s >= 100`).
   - Commits changes with message `fix(cart): apply discount on orders of $100 or more`.
   - Posts diff preview to Switch room.

### Step 7: Strict Verification & Resolution
1. Click **Run Sandbox Verification**.
   - **Reproduction Re-check:** Re-runs `node --test tests/cart.test.js` &rarr; **PASSED (Exit 0)**!
   - **Test Suite Check:** Full test suite executes &rarr; **PASSED (Exit 0)**!
2. Status transitions to **`RESOLVED`**!
   - Verification outcome is logged to PostgreSQL and broadcast to Switch.

