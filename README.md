# WhatsApp Template Builder (LLM-first, creation-only)

FastAPI + async SQLAlchemy (PostgreSQL) + OpenAI Responses API (structured outputs) + config‑driven validation/lint. Builds **Meta WhatsApp template creation payloads** only (no sending).

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
# start postgres (docker recommended) or update DATABASE_URL in .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

## Docker

```bash
docker compose up --build
```

## Endpoints
- `GET /health`
- `GET /session/new`
- `POST /chat` {"message": "...", "session_id": "..."}
- `POST /config/reload`

