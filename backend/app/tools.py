"""Tools the agent can call. Each is a plain Python function the LLM invokes
via native tool/function calling — the docstring IS the tool description the
model sees, so keep it accurate.

Each tool dispatches to one of two backends based on STORE_BACKEND:
  - "memory" (default): in-process dicts from mock_data.py — zero setup,
    used for the standard demo.
  - "postgres": real Postgres (system of record) + pgvector semantic search
    via app/store/postgres.py — used when you've run `docker compose up (or
    seeded a real Postgres/Supabase project, see backend/scripts/seed_postgres.py).
The tool names/schemas the LLM sees are identical either way.
"""
import os
from datetime import date
from typing import Annotated, Optional

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from .mock_data import FAQS, ORDERS, TICKETS, TODAY

STORE_BACKEND = os.getenv("STORE_BACKEND", "memory")


def _deny_if_not_owner(result: dict, order_id: str, session_customer_id: Optional[str]) -> dict:
    """Cross-customer access guard: if this order belongs to someone other
    than whoever the session is for, respond exactly as if it didn't exist —
    never confirm "that order exists but isn't yours", which itself leaks
    information. `session_customer_id` is injected server-side from graph
    state (InjectedState below), not supplied by the model, so a crafted
    prompt can't override whose orders it's allowed to see.

    Guest sessions (no customer_id selected) skip this check by design —
    there's no identity to check against yet. A real deployment would
    require auth before this point, not just after.
    """
    if not result.get("found") or not session_customer_id:
        return result
    if result.get("customer_id") != session_customer_id:
        if STORE_BACKEND == "postgres":
            from .store import postgres as store

            store.log_audit(
                "order_access_denied",
                {"order_id": order_id, "requested_by": session_customer_id, "actual_owner": result.get("customer_id")},
            )
        return {"found": False, "message": f"No order found with ID {order_id}."}
    return result


@tool
def get_order_status(
    order_id: str,
    # No `= None` default here — that would make LangChain stop treating
    # this as an injected arg and expose it in the model's tool schema
    # instead, silently defeating the whole guard (confirmed: adding one
    # back makes it show up in tool_call_schema). Guest sessions are handled
    # by guaranteeing `customer_id` is always a key in graph state (even
    # when None), never by defaulting it here — see run_turn() in graph.py.
    session_customer_id: Annotated[Optional[str], InjectedState("customer_id")],
) -> dict:
    """Look up the current status, items, total, and delivery ETA for a
    customer order by its order ID (format like 'ORD-1001')."""
    if STORE_BACKEND == "postgres":
        from .store import postgres as store

        result = store.get_order_status(order_id)
    else:
        order = ORDERS.get(order_id.strip().upper())
        result = (
            {"found": True, "order_id": order_id.upper(), **order}
            if order
            else {"found": False, "message": f"No order found with ID {order_id}."}
        )
    return _deny_if_not_owner(result, order_id, session_customer_id)


@tool
def check_return_eligibility(
    order_id: str,
    session_customer_id: Annotated[Optional[str], InjectedState("customer_id")],
) -> dict:
    """Check whether an order is eligible for return/refund, based on its
    delivery date and the store's 30-day return window."""
    if STORE_BACKEND == "postgres":
        from .store import postgres as store

        result = store.check_return_eligibility(order_id)
    else:
        order = ORDERS.get(order_id.strip().upper())
        if not order:
            result = {"found": False, "message": f"No order found with ID {order_id}."}
        elif order["status"] != "delivered" or not order["delivered_date"]:
            result = {
                "found": True,
                "customer_id": order["customer_id"],
                "eligible": False,
                "reason": "Order has not been delivered yet, so it isn't eligible for return yet.",
            }
        else:
            delivered = date.fromisoformat(order["delivered_date"])
            days_since = (TODAY - delivered).days
            window = order["return_window_days"]
            eligible = days_since <= window
            result = {
                "found": True,
                "customer_id": order["customer_id"],
                "eligible": eligible,
                "days_since_delivery": days_since,
                "return_window_days": window,
                "reason": (
                    "Within the return window." if eligible
                    else f"Delivered {days_since} days ago, which exceeds the {window}-day return window."
                ),
            }
    return _deny_if_not_owner(result, order_id, session_customer_id)


@tool
def search_faq(query: str) -> list[dict]:
    """Search the store's FAQ knowledge base for articles relevant to a
    customer's general question (shipping, payments, returns policy,
    warranty, support hours, etc). Returns the best-matching articles."""
    if STORE_BACKEND == "postgres":
        from .store import postgres as store

        return store.search_faq(query)

    query_words = set(query.lower().split())
    scored = []
    for faq in FAQS:
        haystack = " ".join([faq["question"].lower(), faq["answer"].lower(), " ".join(faq["tags"])])
        score = sum(1 for w in query_words if w in haystack)
        if score > 0:
            scored.append((score, faq))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [f for _, f in scored[:3]]
    if not top:
        return [{"message": "No matching FAQ article found."}]
    return [{"question": f["question"], "answer": f["answer"]} for f in top]


@tool
def create_support_ticket(customer_id: str, subject: str, summary: str, priority: str) -> dict:
    """Create a human-support escalation ticket when the issue can't be
    resolved automatically, or the customer explicitly asks for a human.
    Priority must be one of: low, medium, high, urgent."""
    if STORE_BACKEND == "postgres":
        from .store import postgres as store

        return store.create_support_ticket(customer_id, subject, summary, priority)

    ticket_id = f"TCK-{1001 + len(TICKETS)}"
    ticket = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "subject": subject,
        "summary": summary,
        "priority": priority,
        "status": "open",
    }
    TICKETS[ticket_id] = ticket
    return ticket


# Tool scopes are deliberately split per agent (least-privilege): the Order &
# Returns Agent can't accidentally search FAQs, the FAQ Agent can't touch
# order data, and only the Escalation Agent files tickets.
ORDER_RETURNS_TOOLS = [get_order_status, check_return_eligibility]
FAQ_TOOLS = [search_faq]

# Shared ToolNode executes whichever of these gets called, regardless of
# which agent called it (dispatch is by tool name).
TOOLS = ORDER_RETURNS_TOOLS + FAQ_TOOLS
