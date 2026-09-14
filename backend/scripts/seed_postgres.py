"""One-time (re-runnable) seed script for the Postgres system-of-record.

Loads the same demo users/orders/FAQs that STORE_BACKEND=memory uses from
mock_data.py, so both backends show identical demo data — and computes real
OpenAI embeddings for each FAQ so search_faq does genuine semantic search
via pgvector once STORE_BACKEND=postgres.

Usage:
    cd backend
    docker compose -f ../docker-compose.yml up -d   # or: docker compose up -d (from repo root)
    export $(grep -v '^#' .env | xargs)              # or just make sure DATABASE_URL/OPENAI_API_KEY are set
    python -m scripts.seed_postgres

Safe to re-run: upserts by primary key, and skips re-embedding a FAQ whose
question/answer text hasn't changed (saves API calls).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.mock_data import FAQS, ORDERS, USERS  # noqa: E402
from app.store import postgres as store  # noqa: E402


def main():
    print(f"Connecting via DATABASE_URL...")
    store.ensure_schema()
    print("Schema ensured.")

    for customer_id, user in USERS.items():
        store.upsert_user(customer_id, user["name"], user["email"])
    print(f"Seeded {len(USERS)} users.")

    for order_id, order in ORDERS.items():
        store.upsert_order(order_id, order)
    print(f"Seeded {len(ORDERS)} orders.")

    print(f"Embedding + seeding {len(FAQS)} FAQ articles (skips unchanged ones)...")
    for faq in FAQS:
        store.upsert_faq(faq["question"], faq["answer"])
    print("Done.")


if __name__ == "__main__":
    main()
