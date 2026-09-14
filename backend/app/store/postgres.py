"""Postgres-backed system of record: users, orders, tickets, audit log, and
FAQ embeddings (pgvector) for real semantic search.

Only used when STORE_BACKEND=postgres (see tools.py, which dispatches here
instead of mock_data.py). Requires `docker compose up -d` (or an equivalent
Postgres with the `vector` extension available — including a hosted one like
Supabase) and DATABASE_URL set.

Everything lives in its own Postgres schema (POSTGRES_SCHEMA, default
"urbancart"), not `public` — this is what makes it safe to point at a
Postgres instance / Supabase project that already has other tables in it
(e.g. `public.users`): every unqualified table name in this file resolves
against `search_path`, which every pooled connection is configured with, so
none of this can collide with or overwrite anything outside its own schema.

Schema is intentionally simple for a POC — no migration framework, just
idempotent `CREATE TABLE IF NOT EXISTS`. A real project would use Alembic (or
similar) instead of `ensure_schema()`.
"""
import json
import os
import re
from datetime import date
from functools import lru_cache

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

_RAW_SCHEMA = os.getenv("POSTGRES_SCHEMA", "urbancart")
if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", _RAW_SCHEMA):
    raise RuntimeError(f"POSTGRES_SCHEMA={_RAW_SCHEMA!r} is not a valid Postgres identifier")
PG_SCHEMA = _RAW_SCHEMA

# Embeddings need their own provider choice (Anthropic has no public
# embeddings API), independent of which chat model is primary. Prefer
# OpenAI if configured, otherwise fall back to Google — but unlike the chat
# fallback chain, this is chosen ONCE at startup, not per-call: every row in
# faq_embeddings must share one fixed vector dimension, so silently
# switching providers mid-run would corrupt the index.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER") or (
    "openai" if os.getenv("OPENAI_API_KEY") else "google" if os.getenv("GOOGLE_API_KEY") else "openai"
)
_EMBEDDING_CONFIG = {
    "openai": {"model": os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"), "dim": 1536},
    "google": {"model": os.getenv("GOOGLE_EMBEDDING_MODEL", "models/gemini-embedding-001"), "dim": 3072},
}
EMBEDDING_MODEL = _EMBEDDING_CONFIG[EMBEDDING_PROVIDER]["model"]
EMBEDDING_DIM = _EMBEDDING_CONFIG[EMBEDDING_PROVIDER]["dim"]


def _configure(conn):
    # `public` stays on the search_path (after our schema) because the
    # `vector` type from the extension typically lives there — this does
    # NOT put our tables in public, it only makes extension types visible.
    conn.execute(f"SET search_path TO {PG_SCHEMA}, public")
    # psycopg3 isn't autocommit by default, so the SET above leaves the
    # connection mid-transaction; the pool requires connections to be idle
    # when handed back, or it discards them (and retries forever). The SET
    # itself survives the commit — only the (empty) transaction ends.
    conn.commit()
    register_vector(conn)


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("STORE_BACKEND=postgres but DATABASE_URL is not set (see backend/.env.example)")
    return database_url


@lru_cache
def get_pool() -> ConnectionPool:
    # prepare_threshold=None disables server-side prepared statements, which
    # a pgbouncer connection in transaction-pooling mode (e.g. Supabase's
    # default pooled connection string, port 6543) doesn't support — without
    # this, queries start failing after a handful of requests once psycopg's
    # autoprepare kicks in. Harmless against a direct, non-pooled connection.
    return ConnectionPool(
        _database_url(),
        min_size=1,
        max_size=5,
        configure=_configure,
        kwargs={"prepare_threshold": None},
    )


def ensure_schema() -> None:
    """Cheap, idempotent DDL — safe to run on every app startup.

    Creates the `vector` extension on a bare connection *before* touching the
    pool: the pool's `configure` hook registers pgvector's Python<->SQL type
    adapter on every connection it opens via `register_vector()`, which
    raises if the `vector` type doesn't exist yet — guaranteed on a brand
    new database (e.g. a fresh Supabase project) that's never had the
    extension enabled.
    """
    with psycopg.connect(_database_url(), autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA}")

    with get_pool().connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                customer_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES users(customer_id),
                status TEXT NOT NULL,
                items TEXT[] NOT NULL,
                total NUMERIC(10, 2) NOT NULL,
                order_date DATE NOT NULL,
                delivered_date DATE,
                eta DATE,
                return_window_days INT NOT NULL DEFAULT 30
            )
            """
        )
        conn.execute("CREATE SEQUENCE IF NOT EXISTS ticket_seq START 1001")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                customer_id TEXT,
                subject TEXT NOT NULL,
                summary TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS faq_embeddings (
                id SERIAL PRIMARY KEY,
                question TEXT NOT NULL UNIQUE,
                answer TEXT NOT NULL,
                embedding vector({EMBEDDING_DIM})
            )
            """
        )
        # No ANN index (ivfflat/hnsw) at this scale — a handful of FAQ rows is
        # faster with an exact scan than a tuned approximate index. Add one
        # (`CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)`) once
        # the knowledge base is large enough for it to matter.


def log_audit(event_type: str, payload: dict) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO audit_log (event_type, payload) VALUES (%s, %s)",
            [event_type, json.dumps(payload, default=str)],
        )


# --------------------------------------------------------------- seeding ---

def upsert_user(customer_id: str, name: str, email: str) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO users (customer_id, name, email) VALUES (%s, %s, %s)
            ON CONFLICT (customer_id) DO UPDATE SET name = EXCLUDED.name, email = EXCLUDED.email
            """,
            [customer_id, name, email],
        )


def upsert_order(order_id: str, order: dict) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO orders
                (order_id, customer_id, status, items, total, order_date, delivered_date, eta, return_window_days)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (order_id) DO UPDATE SET
                customer_id = EXCLUDED.customer_id, status = EXCLUDED.status, items = EXCLUDED.items,
                total = EXCLUDED.total, order_date = EXCLUDED.order_date, delivered_date = EXCLUDED.delivered_date,
                eta = EXCLUDED.eta, return_window_days = EXCLUDED.return_window_days
            """,
            [
                order_id,
                order["customer_id"],
                order["status"],
                order["items"],
                order["total"],
                order["order_date"],
                order["delivered_date"],
                order["eta"],
                order["return_window_days"],
            ],
        )


def embed_text(text: str) -> list[float]:
    if EMBEDDING_PROVIDER == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
    else:
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return embeddings.embed_query(text)


def upsert_faq(question: str, answer: str) -> None:
    """Embeds `question` and upserts the row. Skips re-embedding (an OpenAI
    API call) if the question already exists unchanged."""
    with get_pool().connection() as conn:
        existing = conn.execute(
            "SELECT answer FROM faq_embeddings WHERE question = %s", [question]
        ).fetchone()
        if existing and existing[0] == answer:
            return
        vector = Vector(embed_text(f"{question}\n{answer}"))
        conn.execute(
            """
            INSERT INTO faq_embeddings (question, answer, embedding) VALUES (%s, %s, %s)
            ON CONFLICT (question) DO UPDATE SET answer = EXCLUDED.answer, embedding = EXCLUDED.embedding
            """,
            [question, answer, vector],
        )


# ------------------------------------------------------- tool-facing reads -

def get_order_status(order_id: str) -> dict:
    order_id = order_id.strip().upper()
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT order_id, customer_id, status, items, total, order_date, delivered_date, eta, return_window_days
            FROM orders WHERE order_id = %s
            """,
            [order_id],
        ).fetchone()
    log_audit("order_status_lookup", {"order_id": order_id, "found": row is not None})
    if not row:
        return {"found": False, "message": f"No order found with ID {order_id}."}
    return {
        "found": True,
        "order_id": row[0],
        "customer_id": row[1],
        "status": row[2],
        "items": row[3],
        "total": float(row[4]),
        "order_date": _iso(row[5]),
        "delivered_date": _iso(row[6]),
        "eta": _iso(row[7]),
        "return_window_days": row[8],
    }


def check_return_eligibility(order_id: str) -> dict:
    order_id = order_id.strip().upper()
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT customer_id, status, delivered_date, return_window_days FROM orders WHERE order_id = %s",
            [order_id],
        ).fetchone()
    if not row:
        log_audit("return_eligibility_check", {"order_id": order_id, "found": False})
        return {"found": False, "message": f"No order found with ID {order_id}."}

    order_customer_id, status, delivered_date, window = row
    if status != "delivered" or not delivered_date:
        result = {"found": True, "customer_id": order_customer_id, "eligible": False, "reason": "Order has not been delivered yet, so it isn't eligible for return yet."}
    else:
        days_since = (date.today() - delivered_date).days
        eligible = days_since <= window
        result = {
            "customer_id": order_customer_id,
            "found": True,
            "eligible": eligible,
            "days_since_delivery": days_since,
            "return_window_days": window,
            "reason": (
                "Within the return window." if eligible
                else f"Delivered {days_since} days ago, which exceeds the {window}-day return window."
            ),
        }
    log_audit("return_eligibility_check", {"order_id": order_id, **result})
    return result


def search_faq(query: str, top_k: int = 3) -> list[dict]:
    query_vector = Vector(embed_text(query))
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT question, answer, embedding <=> %s AS distance FROM faq_embeddings ORDER BY distance LIMIT %s",
            [query_vector, top_k],
        ).fetchall()
    log_audit("faq_search", {"query": query, "matches": len(rows)})
    if not rows:
        return [{"message": "No matching FAQ article found."}]
    return [{"question": r[0], "answer": r[1]} for r in rows]


def create_support_ticket(customer_id: str, subject: str, summary: str, priority: str) -> dict:
    with get_pool().connection() as conn:
        seq_val = conn.execute("SELECT nextval('ticket_seq')").fetchone()[0]
        ticket_id = f"TCK-{seq_val}"
        conn.execute(
            "INSERT INTO tickets (ticket_id, customer_id, subject, summary, priority) VALUES (%s, %s, %s, %s, %s)",
            [ticket_id, customer_id, subject, summary, priority],
        )
    ticket = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "subject": subject,
        "summary": summary,
        "priority": priority,
        "status": "open",
    }
    log_audit("ticket_created", ticket)
    return ticket


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None
