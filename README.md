# PRAGMATA

> **Investigate. Deliberate. Resolve.**
>
> An AI-powered collaborative bug investigation and resolution platform with human authority gates, Switch-native collaboration, and verified completion.

---

## Architecture Overview

```text
Reporter / Developer
        |
        v
Next.js Dashboard (Port 3000)
        |
        v
FastAPI Backend (Port 8000)
        |
        +------------------------------+
        |                              |
        v                              v
PostgreSQL 16 (Port 5432)        Switch Adapter
        |
        v
Deterministic State Machine & Human Approval Gates
```

---

## Quickstart (Local Development)

### Prerequisites

- **Python** >= 3.11
- **Node.js** >= 18 and **npm**
- **Docker** and **Docker Compose**

### 1. Clone & Configure Environment

```bash
cp .env.example .env
```

### 2. Start PostgreSQL via Docker Compose

```bash
docker compose up -d db
```

Confirm the database container is healthy:
```bash
docker compose ps
```

### 3. Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Run database migrations
alembic upgrade head

# Run tests
pytest tests

# Start backend server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend health check: [http://localhost:8000/health](http://localhost:8000/health)
API Documentation (when `DEBUG=true`): [http://localhost:8000/docs](http://localhost:8000/docs)

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend dashboard: [http://localhost:3000](http://localhost:3000)

---

## Hackathon Demo Walkthrough

We provide a self-contained Node.js & TypeScript target repository in `demo/sample-node-cart` with an intentional boundary discount defect (`100 !== 80`).

To run the automated end-to-end demo test:
```bash
cd backend
pytest tests/test_e2e_hackathon_demo.py -v
```

For the complete interactive dashboard walkthrough script, see [demo/DEMO_SCRIPT.md](demo/DEMO_SCRIPT.md).

---

## Invariants & Design Principles

1. **Human Authority:** AI agents investigate, reproduce, and debate. Consequential decisions (issue acceptance, fix selection, PR merging) require authenticated developer approval.
2. **Evidence Before Certainty:** An issue must be reproduced with real recorded output, not assumed plausible.
3. **Approval Before Code Changes:** No source code is modified before fix approval.
4. **Verification Before Completion:** Fixes are marked resolved only after reproduction checks and tests pass.
