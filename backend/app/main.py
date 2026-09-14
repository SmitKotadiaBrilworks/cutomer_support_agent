import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .graph import run_turn
from .llm_providers import configured_providers
from .schemas import ChatRequest, ChatResponse

STORE_BACKEND = os.getenv("STORE_BACKEND", "memory")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if STORE_BACKEND == "postgres":
        from .store import postgres as store

        store.ensure_schema()  # cheap DDL only — no embeddings/API calls here
    yield


app = FastAPI(title="UrbanCart Customer Support Agent (POC)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_postgres() -> str:
    try:
        from .store import postgres as store

        with store.get_pool().connection(timeout=2) as conn:
            conn.execute("SELECT 1")
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"unreachable: {e}"


def _check_redis() -> str:
    try:
        import redis as redis_client

        r = redis_client.from_url(os.getenv("REDIS_URL", "redis://localhost:6380"), socket_connect_timeout=2)
        r.ping()
        return "ok"
    except Exception as e:  # noqa: BLE001
        return f"unreachable: {e}"


@app.get("/health")
def health():
    providers = configured_providers()
    body = {
        "status": "ok" if providers else "no_providers_configured",
        "configured_providers": list(providers),
        "store_backend": STORE_BACKEND,
    }
    if STORE_BACKEND == "postgres":
        body["postgres"] = _check_postgres()
        body["redis"] = _check_redis()
        if body["postgres"] != "ok" or body["redis"] != "ok":
            body["status"] = "degraded"
    return body


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty")
    try:
        result = run_turn(req.session_id, req.message, req.customer_id)
    except RuntimeError as e:
        # e.g. no provider configured, or (in postgres mode) DB/Redis unreachable
        raise HTTPException(status_code=503, detail=str(e))
    return ChatResponse(
        session_id=req.session_id,
        reply=result["reply"],
        escalated=result["escalated"],
        ticket_id=result["ticket_id"],
        provider_used=result["provider_used"],
        agent_path=result["agent_path"],
        current_agent=result["current_agent"],
        tools_used=result["tools_used"],
        intent=result["intent"],
        sentiment=result["sentiment"],
    )


@app.get("/agents")
def list_agents():
    """Static metadata about the agent roster, for the UI to render (e.g. an
    'agents involved' legend) without hardcoding it client-side."""
    return {
        "agents": [
            {"id": "triage", "name": "Triage Agent", "role": "Classifies intent & sentiment, routes to a specialist"},
            {
                "id": "order_returns_agent",
                "name": "Order & Returns Agent",
                "role": "Order status & return/refund eligibility",
                "tools": ["get_order_status", "check_return_eligibility"],
            },
            {
                "id": "faq_agent",
                "name": "FAQ / Knowledge Agent",
                "role": "General policy & product questions",
                "tools": ["search_faq"],
            },
            {
                "id": "escalation_agent",
                "name": "Escalation Agent",
                "role": "Drafts & files support tickets for human follow-up",
                "tools": ["create_support_ticket"],
            },
        ]
    }
