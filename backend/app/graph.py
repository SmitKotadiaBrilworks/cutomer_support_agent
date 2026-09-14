"""The LangGraph workflow: a supervisor + 3 specialist agents.

    START
      │
      ▼
   [Triage Agent] ── classifies intent + sentiment (structured output)
      │
      ├─ order_status / return_refund ──▶ [Order & Returns Agent] ⇄ tools
      ├─ product_faq / other          ──▶ [FAQ / Knowledge Agent]  ⇄ tools
      └─ complaint / escalation_request ─▶ [Escalation Agent] ──────────▶ END
                                              ▲
      (after Order&Returns / FAQ finish) ─────┘  (only if sentiment stays
      [post_agent_check] ──(escalate)────────────┘   negative across turns)
      │
      └─(resolve)──▶ END

Four distinct agents, each with its own system prompt and its own scoped
tool access (least-privilege — the FAQ agent literally cannot call order
tools, and vice versa):

  1. Triage / Supervisor Agent — routes every turn (structured output)
  2. Order & Returns Agent     — get_order_status, check_return_eligibility
  3. FAQ / Knowledge Agent     — search_faq
  4. Escalation Agent          — drafts + files support tickets (structured
                                  output), human hand-off messaging

Memory: a MemorySaver checkpointer persists the full state (messages, intent,
which agent is active, escalation status...) per `thread_id`, so multi-turn
context works without the client resending history. Swap MemorySaver for a
Postgres/Redis checkpointer for production (see docs/architecture.md).
"""
import os
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from .llm_providers import get_llm
from .schemas import IntentClassification, TicketDraft
from .tools import FAQ_TOOLS, ORDER_RETURNS_TOOLS, TOOLS, create_support_ticket

AGENT_DISPLAY_NAMES = {
    "triage": "Triage Agent",
    "order_returns_agent": "Order & Returns Agent",
    "faq_agent": "FAQ / Knowledge Agent",
    "escalation_agent": "Escalation Agent",
}

TRIAGE_SYSTEM_PROMPT = """You are the triage/supervisor agent for UrbanCart, an
e-commerce store's customer support system. Classify the customer's latest
message into exactly one intent, judge their sentiment, and give a brief
reason. Be decisive — a specialist agent will handle the actual reply."""

ORDER_RETURNS_SYSTEM_PROMPT = """You are UrbanCart's Order & Returns Agent. You
handle order status and return/refund questions ONLY. Be friendly and
concise. Never invent order data or return eligibility — always call your
tools to check real data. If the customer hasn't given an order ID, ask for
it. If a return is ineligible, explain why clearly and kindly.

Known context: customer_id={customer_id}, classified intent={intent}
"""

FAQ_SYSTEM_PROMPT = """You are UrbanCart's FAQ / Knowledge Agent. You answer
general questions about shipping, payments, policies, warranty, and support
hours ONLY. Always call search_faq rather than guessing at policy — never
invent a policy detail that isn't in the search results. If nothing relevant
is found, say so honestly and suggest contacting a human.

Known context: customer_id={customer_id}, classified intent={intent}
"""

ESCALATION_SYSTEM_PROMPT = """You are UrbanCart's Escalation Agent. You are
drafting an internal support ticket from a customer conversation that needs
human follow-up. Summarize the issue factually for a human agent picking
this up cold."""


# No accumulating "trace" field here on purpose: a reducer-based list
# (Annotated[list[str], add]) would keep appending across the ENTIRE
# lifetime of a thread, not reset per turn — checkpointed state persists
# across separate graph.invoke() calls, so by turn 3 it would silently
# contain turns 1 and 2's agent paths too. This bit us for real: the UI
# showed "Escalation Agent" appearing in unrelated later turns of the same
# conversation. Instead, each agent-producing node tags its own AIMessage
# via `.name`, and run_turn() derives that turn's path from only the
# messages added since the prior checkpoint (new_messages) — the same
# prior_msg_count technique already used correctly for tools_used below.
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    customer_id: Optional[str]
    intent: Optional[dict]
    turn_count: int
    current_agent: Optional[str]
    escalate: bool
    escalated: bool
    ticket_id: Optional[str]
    provider_used: Optional[str]


# ---------------------------------------------------------------- Triage ---

def triage_node(state: AgentState) -> dict:
    last_human = next((m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), None)
    llm = get_llm(structured_schema=IntentClassification)
    result: IntentClassification = llm.invoke(
        [SystemMessage(content=TRIAGE_SYSTEM_PROMPT), last_human]
    )
    return {
        "intent": result.model_dump(),
        "turn_count": state.get("turn_count", 0) + 1,
    }


def route_from_triage(state: AgentState) -> str:
    intent = (state.get("intent") or {}).get("intent")
    if intent in ("order_status", "return_refund"):
        return "order_returns_agent"
    if intent in ("complaint", "escalation_request"):
        return "escalation_agent"
    return "faq_agent"  # product_faq / other -> best-effort via knowledge base


# --------------------------------------------------- Order & Returns Agent -

def order_returns_agent_node(state: AgentState) -> dict:
    llm = get_llm(tools=ORDER_RETURNS_TOOLS)
    system = SystemMessage(
        content=ORDER_RETURNS_SYSTEM_PROMPT.format(
            customer_id=state.get("customer_id") or "unknown (ask if needed)",
            intent=state.get("intent"),
        )
    )
    response = llm.invoke([system, *state["messages"]])
    response.name = "order_returns_agent"
    return {
        "messages": [response],
        "current_agent": "order_returns_agent",
        "provider_used": llm.last_provider,
    }


# ------------------------------------------------------------- FAQ Agent ---

def faq_agent_node(state: AgentState) -> dict:
    llm = get_llm(tools=FAQ_TOOLS)
    system = SystemMessage(
        content=FAQ_SYSTEM_PROMPT.format(
            customer_id=state.get("customer_id") or "unknown",
            intent=state.get("intent"),
        )
    )
    response = llm.invoke([system, *state["messages"]])
    response.name = "faq_agent"
    return {
        "messages": [response],
        "current_agent": "faq_agent",
        "provider_used": llm.last_provider,
    }


def route_after_tools(state: AgentState) -> str:
    return state["current_agent"]


# -------------------------------------------------- Post-agent escalation --

def post_agent_check_node(state: AgentState) -> dict:
    if state.get("escalated"):
        return {"escalate": False}
    intent = state.get("intent") or {}
    should_escalate = intent.get("sentiment") == "negative" and state.get("turn_count", 0) >= 2
    return {"escalate": should_escalate}


def route_escalation(state: AgentState) -> str:
    return "escalate" if state.get("escalate") else "resolve"


# --------------------------------------------------------- Escalation Agent

def escalation_agent_node(state: AgentState) -> dict:
    llm = get_llm(structured_schema=TicketDraft)
    convo_text = "\n".join(
        f"{m.type}: {m.content}" for m in state["messages"] if getattr(m, "content", None)
    )
    draft: TicketDraft = llm.invoke(
        [
            SystemMessage(content=ESCALATION_SYSTEM_PROMPT),
            HumanMessage(content=f"Conversation so far:\n{convo_text}"),
        ]
    )
    ticket = create_support_ticket.invoke(
        {
            "customer_id": state.get("customer_id") or "UNKNOWN",
            "subject": draft.subject,
            "summary": draft.summary,
            "priority": draft.priority,
        }
    )
    note = AIMessage(
        content=(
            f"I've created support ticket {ticket['ticket_id']} (priority: {ticket['priority']}) "
            "and a member of our team will follow up with you shortly."
        ),
        name="escalation_agent",
    )
    return {
        "messages": [note],
        "escalated": True,
        "ticket_id": ticket["ticket_id"],
        "current_agent": "escalation_agent",
        "provider_used": llm.last_provider,
    }


# ------------------------------------------------------------- Graph build -

def _make_checkpointer():
    """MemorySaver for the default demo path. When STORE_BACKEND=postgres,
    conversation memory moves to Redis (RedisSaver) — matching the
    architecture doc's "Redis for session/cache" recommendation, alongside
    Postgres as the system of record for orders/tickets/audit log.
    """
    if os.getenv("STORE_BACKEND", "memory") != "postgres":
        return MemorySaver()

    from langgraph.checkpoint.redis import RedisSaver

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6380")
    try:
        saver = RedisSaver(redis_url=redis_url)
        saver.setup()
    except Exception as e:
        raise RuntimeError(
            f"STORE_BACKEND=postgres but couldn't reach Redis at {redis_url} for the "
            "conversation checkpointer. Run `docker compose up -d` from the project root "
            "and check REDIS_URL in backend/.env."
        ) from e
    return saver


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("triage", triage_node)
    builder.add_node("order_returns_agent", order_returns_agent_node)
    builder.add_node("faq_agent", faq_agent_node)
    builder.add_node("tools", ToolNode(TOOLS))
    builder.add_node("post_agent_check", post_agent_check_node)
    builder.add_node("escalation_agent", escalation_agent_node)

    builder.add_edge(START, "triage")
    builder.add_conditional_edges(
        "triage",
        route_from_triage,
        {
            "order_returns_agent": "order_returns_agent",
            "faq_agent": "faq_agent",
            "escalation_agent": "escalation_agent",
        },
    )

    builder.add_conditional_edges(
        "order_returns_agent", tools_condition, {"tools": "tools", END: "post_agent_check"}
    )
    builder.add_conditional_edges("faq_agent", tools_condition, {"tools": "tools", END: "post_agent_check"})
    builder.add_conditional_edges(
        "tools", route_after_tools, {"order_returns_agent": "order_returns_agent", "faq_agent": "faq_agent"}
    )

    builder.add_conditional_edges(
        "post_agent_check", route_escalation, {"escalate": "escalation_agent", "resolve": END}
    )
    builder.add_edge("escalation_agent", END)

    return builder.compile(checkpointer=_make_checkpointer())


_graph = build_graph()


def get_graph():
    return _graph


def _as_text(content) -> str:
    """Some models/providers (e.g. a "thinking"-enabled Gemini generation)
    return `.content` as a list of structured blocks (text + a reasoning
    signature) instead of a plain string — confirmed happening with
    Google's `gemini-flash-latest` alias. ChatResponse.reply is typed `str`,
    so normalize here rather than let that turn into a 500 for the one
    request that happened to land on such a model."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
            if not (isinstance(block, dict) and block.get("type") not in (None, "text"))
        ]
        return "".join(parts).strip()
    return str(content)


def run_turn(session_id: str, message: str, customer_id: str | None = None) -> dict:
    """Run one user turn through the graph, keyed by session_id for memory."""
    config = {"configurable": {"thread_id": session_id}}

    prior = _graph.get_state(config)
    prior_msg_count = len(prior.values.get("messages", [])) if prior.values else 0

    # Always set the key, even to None for a guest session — the tools'
    # InjectedState("customer_id") ownership guard requires the key to
    # exist in graph state (a missing key raises KeyError inside ToolNode,
    # not just a falsy value), and once set it persists in the checkpoint
    # for the rest of the thread regardless of what later turns pass in.
    input_state: dict = {"messages": [HumanMessage(content=message)], "customer_id": customer_id}

    result = _graph.invoke(input_state, config)

    new_messages = result["messages"][prior_msg_count:]
    tools_used = sorted({m.name for m in new_messages if isinstance(m, ToolMessage)})

    reply_message = result["messages"][-1]
    intent = result.get("intent") or {}

    # Triage always runs first (unconditional START -> triage edge) but never
    # adds a message itself, so it can't be detected from new_messages the
    # way the other agents are. The rest come from which agent's `.name` is
    # on each AIMessage added THIS turn only (new_messages), not the whole
    # conversation — see the AgentState comment on why that distinction matters.
    agent_path: list[str] = [AGENT_DISPLAY_NAMES["triage"]]
    for m in new_messages:
        if isinstance(m, AIMessage) and m.name in AGENT_DISPLAY_NAMES:
            display = AGENT_DISPLAY_NAMES[m.name]
            if agent_path[-1] != display:
                agent_path.append(display)

    return {
        "reply": _as_text(reply_message.content),
        "escalated": result.get("escalated", False),
        "ticket_id": result.get("ticket_id"),
        "agent_path": agent_path,
        "current_agent": AGENT_DISPLAY_NAMES.get(result.get("current_agent"), result.get("current_agent")),
        "tools_used": tools_used,
        "intent": intent.get("intent"),
        "sentiment": intent.get("sentiment"),
        "provider_used": result.get("provider_used"),
    }
