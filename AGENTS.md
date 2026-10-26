# SupportFlow development guide

This is a standalone local Python / React project inspired by DeerFlow. Keep business logic in `services.py`, retrieval in `knowledge.py`, agent assembly in `agent.py`, and HTTP concerns in `app.py`.

## Invariants

- Authenticate the caller and verify conversation ownership before admitting a run. Never accept model-supplied user identity.
- The agent may propose a ticket draft; only the explicit authenticated confirmation endpoint creates a ticket.
- Preserve database uniqueness for draft confirmation, idempotency keys and active conversation runs. Preserve conditional version updates for ticket mutations.
- Demo mode is deterministic and clearly labeled. Monitor values are synthetic until an actual integration is implemented.
- This version uses one API process and local SQLite checkpoints. Do not introduce multiworker startup without redesigning ownership and recovery.
- Shared knowledge is deployment-wide; do not claim tenant isolation or semantic retrieval unless implemented and tested.
- Never log provider credentials, environment contents or complete provider exception payloads.
- Keep the optional DeerFlow adapter on public `deerflow_extension_api` contracts. The standalone server must work without that optional dependency.

## Verification

Run meaningful regression tests when changing authentication, transactions, agent state or tool behavior:

```text
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check backend tests scripts
.venv/Scripts/python.exe -m ruff format --check backend tests scripts
cd frontend
npm test
npm run build
```

`scripts/smoke_http.py` starts and stops its own server using temporary data. `scripts/evaluate.py` uses a small synthetic corpus and must keep failed examples visible. `scripts/smoke_live.py` calls the configured external model and consumes tokens; it is opt-in.

Runtime data, `.env`, virtual environments and build dependencies must remain ignored. Update README / architecture and verification scope when behavior changes.
