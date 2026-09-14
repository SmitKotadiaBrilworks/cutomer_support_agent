# UrbanCart Support POC — Technical Walkthrough

Three views of the same system: the request lifecycle end to end, the
LangGraph agent workflow that does the actual reasoning, and the Postgres
schema it all reads and writes.

## 1. Request lifecycle

Every chat message makes one round trip through four components. LangGraph
is the one doing the thinking — it expands into the full agent workflow in
section 2.

```mermaid
flowchart LR
    Browser["Browser\n(Next.js chat UI)"] -- "POST /chat" --> FastAPI["FastAPI\n(/chat endpoint)"]
    FastAPI -- "invoke()" --> LangGraph["LangGraph\n(compiled StateGraph)\n4 agents — see §2"]
    FastAPI -- "reply + trace" --> Browser

    LangGraph -- "chat / classify calls" --> Providers["Model providers\n1. OpenAI (primary)\n2. Anthropic (fallback)\n3. Google (fallback)"]
    LangGraph -- "tool calls / rows" --> Postgres["Postgres\nbusiness data · Supabase"]
    LangGraph -- "checkpoint r/w" --> Redis["Redis\nconversation memory"]
```

One HTTP round trip per message. The browser never talks to LangGraph,
Postgres, or Redis directly — FastAPI is the only entry point, and
everything downstream of `graph.invoke()` happens server-side, keyed by
`session_id`.

## 2. Inside LangGraph — the agent workflow

Four agents, not one prompt. A Triage agent classifies every message and
routes it; two specialists loop with tools until they have an answer; a
deterministic check — not another LLM call — decides whether a human needs
to get involved.

```mermaid
flowchart TD
    START((START)) --> Triage["Triage Agent\nclassify intent + sentiment\n(structured output)"]

    Triage -- "order_status / return_refund" --> OrderAgent["Order & Returns Agent\nget_order_status\ncheck_return_eligibility"]
    Triage -- "product_faq / other" --> FAQAgent["FAQ / Knowledge Agent\nsearch_faq\npgvector semantic match"]
    Triage -. "complaint / escalation_request" .-> Escalation["Escalation Agent\ndrafts + files a ticket\n(structured output)"]

    OrderAgent <-- "tool_calls ⇄ result" --> Tools["Tools (shared ToolNode)\ndispatches by tool name,\nexecutes, returns"]
    FAQAgent <-- "tool_calls ⇄ result" --> Tools

    OrderAgent -- "no more tool_calls" --> Check{"post_agent_check\nsentiment negative\n2+ turns?"}
    FAQAgent -- "no more tool_calls" --> Check

    Check -. "escalate" .-> Escalation
    Check -- "resolve" --> END((END))
    Escalation --> END
```

Matches `backend/app/graph.py` exactly, including the parts a summary would
normally drop: the shared `ToolNode` dispatches by tool name regardless of
which agent called it, and `post_agent_check` is plain Python reading
conversation state — not an LLM call — so the escalation safety net can't be
talked out of firing by a persuasive reply.

## 3. Data model

Five tables backing the workflow above, all living inside their own
**`urbancart`** Postgres schema — not `public` — specifically so this can
share a database with an existing application without touching it.

```mermaid
erDiagram
    users ||--o{ orders : places
    users ||..o{ tickets : "referenced (no FK)"

    users {
        TEXT customer_id PK
        TEXT name
        TEXT email
    }

    orders {
        TEXT order_id PK
        TEXT customer_id FK
        TEXT status
        TEXT_ARRAY items
        NUMERIC total
        DATE order_date
        DATE delivered_date "nullable"
        DATE eta "nullable"
        INT return_window_days "default 30"
    }

    tickets {
        TEXT ticket_id PK "e.g. TCK-1001"
        TEXT customer_id "nullable"
        TEXT subject
        TEXT summary
        TEXT priority "low…urgent"
        TEXT status "default open"
        TIMESTAMPTZ created_at
    }

    faq_embeddings {
        SERIAL id PK
        TEXT question "unique"
        TEXT answer
        VECTOR embedding "standalone, no relationships"
    }

    audit_log {
        BIGSERIAL id PK
        TEXT event_type
        JSONB payload
        TIMESTAMPTZ created_at
    }
```

The only enforced relationship is `orders.customer_id → users.customer_id`;
the link from tickets to a customer is intentionally logical-only, since a
ticket can be filed before a customer is identified. `faq_embeddings` and
`audit_log` are standalone by design. A separate, pre-existing `public`
schema in the same database (18 tables, unrelated project) is untouched by
any of this.

| Table | Purpose |
|---|---|
| **users** | The customer directory. Every order and, loosely, every ticket traces back to a row here. |
| **orders** | System of record for order status, items, and delivery dates — what the Order & Returns agent reads and reasons over. |
| **tickets** | Human-escalation records the Escalation agent files when it can't resolve something on its own. |
| **faq_embeddings** | The knowledge base — each FAQ's text plus its vector embedding, searched by meaning (pgvector) instead of keyword. |
| **audit_log** | Append-only trail of every lookup, search, and ticket creation the agents perform — one row per action, timestamped. |

> **Verified, not assumed.** This schema was created against a live Supabase
> project that already had 18 tables from an unrelated, in-progress
> application in its `public` schema. After creating and seeding all five
> tables above, the existing 18 were checked again — still exactly 18,
> untouched. Same guarantee holds for any Postgres instance this runs
> against, including a fresh one.

---

- Agent workflow: `backend/app/graph.py`
- Provider chain: `backend/app/llm_providers.py`
- Schema DDL: `backend/app/store/postgres.py`
