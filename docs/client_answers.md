# Answers to client evaluation questions

*Companion to the runnable POC in this repo — see [`README.md`](../README.md)
to run it yourself. Every claim below is either a general capability or
refers directly to the code in this repo — nothing here describes a past
client engagement that didn't happen.*

---

### 1. Do you build production applications using OpenAI and frameworks such as LangChain or LangGraph?

Yes. This POC is built exactly that way: OpenAI as the primary model
provider, orchestrated with **LangGraph** for the multi-step agent workflow
and **LangChain** for the model/tool abstractions underneath it. Concretely:

- **LangGraph does the orchestration**, not a chain of if/else calls. The
  whole system is one `StateGraph`
  ([`graph.py`](../backend/app/graph.py)): 6 nodes (Triage, Order & Returns,
  FAQ, Escalation, a shared tool-execution node, an escalation-check node)
  wired together with `add_conditional_edges` — routing decisions
  (`route_from_triage`, `tools_condition`, `route_escalation`) are plain
  Python functions reading the graph's shared state, not prompts trying to
  decide control flow. A `ToolNode` executes whichever tool an agent's LLM
  call requested. A checkpointer (`MemorySaver`, or `RedisSaver` in the
  optional production-infra mode) persists that shared state — conversation
  history, classified intent, which agent is active, escalation status — per
  session, which is what gives the system multi-turn memory.
- **LangChain provides the model and tool abstractions underneath that**:
  the four agents each call a LangChain chat-model object rather than
  hitting an SDK directly, so the same `.bind_tools(...)` /
  `.with_structured_output(...)` call works unmodified whether the live
  model is `ChatOpenAI`, `ChatAnthropic`, or `ChatGoogleGenerativeAI`
  ([`llm_providers.py`](../backend/app/llm_providers.py) — this is also
  where the OpenAI → Anthropic → Google fallback chain lives, a pattern we
  use in production to avoid a single vendor's outage or rate limit taking
  the product down. This is tuned for a fast, real failover, not just a
  theoretical one: each provider is capped at 1 retry / 20s before the chain
  moves on, because we hit exactly this live while building the demo — a
  rate-limited provider's own SDK was retrying internally for 30-60+ seconds
  before ever raising, which would stall a live conversation even with a
  working fallback configured). Tools themselves are plain Python functions wrapped
  with LangChain's `@tool` decorator
  ([`tools.py`](../backend/app/tools.py)), which is what lets a model call
  them via native function/tool calling instead of us hand-parsing its
  output.

### 2. Is the work primarily integrating existing AI APIs, or have you built more complex AI systems (multi-step workflows, structured outputs, memory/state, tool calling, evaluation)?

Both — but the differentiator is the complex-systems side, and this POC is
built specifically to show it, not just describe it:

- **Multi-agent, multi-step workflows**: not one prompt-in/text-out call, but
  a **4-agent supervisor architecture** in LangGraph — a Triage Agent
  classifies and routes to one of three specialists (Order & Returns, FAQ,
  Escalation), each with its own prompt and its own scoped tools, with
  conditional routing and a deterministic escalation safety net
  ([`graph.py`](../backend/app/graph.py)). The demo UI renders this
  live — an animated diagram of the actual graph topology lights up the
  node(s) and edges involved as each reply comes back, and a trace line
  under every message shows exactly which agent(s) handled it, which tools
  ran, which provider answered, and how long it took. It's something you
  watch happen on a call, not a claim to take on faith.
- **Structured outputs**: two Pydantic-schema-constrained LLM calls
  (`IntentClassification`, `TicketDraft` in
  [`schemas.py`](../backend/app/schemas.py)) instead of parsing free text.
- **Memory/state management**: a LangGraph checkpointer persists full
  conversation state (messages, intent, active agent, escalation status) per
  session, so multi-turn context carries over without the client resending
  history. This runs in-process for the quick demo, or on **Redis** with one
  env var (`STORE_BACKEND=postgres`) — see Q3.
- **Tool calling**: each agent has real, scoped callable tools (order
  lookup, return eligibility, FAQ search, ticket creation) via native
  function/tool calling — least-privilege by design, not hardcoded if/else
  logic. The same env var moves these off mock data onto a real **Postgres**
  system of record with an audit log of every lookup, and turns FAQ search
  into genuine **pgvector** semantic search instead of keyword matching.
- **Evaluation**: a labeled eval dataset and harness
  ([`backend/eval/`](../backend/eval/)) scoring intent-classification
  accuracy, tool-selection accuracy, escalation correctness, and optional
  LLM-as-judge reply quality — the same shape of suite we'd wire into CI as a
  regression gate in production.

### 3. What backend architecture and technology stack would you recommend for an AI-heavy consumer application, particularly with scalability and maintainability in mind?

Full writeup in [`docs/architecture.md`](architecture.md). Summary: a thin
API layer (FastAPI/NestJS), a LangGraph orchestration layer for anything
with more than one decision point, a provider-abstracted model layer with
fallback and cost-based routing, memory split into short-term
(Redis/Postgres-backed checkpointer) and long-term (regular DB) plus a
vector store for RAG where needed, and an evaluation/observability layer
(LangSmith/Langfuse tracing + CI-gated eval) treated as a first-class part of
the stack rather than an afterthought. Scalability comes from keeping the AI
layer stateless (state lives in Redis/Postgres, not in-process) so it scales
horizontally like any other API tier; maintainability comes from
version-controlled prompts/graphs and structured outputs instead of
regex-parsed text.

**This isn't just a recommendation on paper** — this POC runs on that exact
stack in an optional mode (`STORE_BACKEND=postgres`, one env var): Postgres
as the system of record (`users`, `orders`, `tickets`, `audit_log`), Redis
for the conversation checkpointer, pgvector for real semantic FAQ search.
`docker-compose.yml` + a one-time seed script bring it up locally in a few
minutes — see `README.md` → "Optional: real production-infra mode."

### 4. Could you walk through a comparable AI application your team has actually built and deployed, including your team's role?

Straight answer: we don't have a directly comparable AI project already
shipped to point you to — so rather than reach for a slide deck about one,
we built this instead. It's not a mockup or a set of screenshots; it's a
live, runnable system with a real UI, running against real infrastructure,
that you can operate yourself before making a decision. We think that's a
stronger basis for evaluating a team than a case study, because you're not
trusting a description of our work — you're looking directly at it.

What that involved, concretely (this is our team's actual role on *this*
piece of work): designing the 4-agent LangGraph architecture and its
routing/escalation logic, building the FastAPI backend and the multi-provider
fallback layer, wiring up the optional Postgres/Redis/pgvector production
data layer end-to-end, building the Next.js UI including the live agent-graph
visualization, and writing the eval harness. It also includes the kind of
things that only show up in real engineering, not in a pitch: a pgvector
type-casting bug we hit and fixed while wiring up semantic search, and a
provider-timeout issue we found live (a rate-limited model's SDK was
retrying internally for 30-60+ seconds before our own fallback chain ever
saw the failure) and fixed by capping retries/timeouts per provider. Nothing
here was scripted for a demo — you're seeing the actual process.

We're glad to walk through any part of it live, extend it in whatever
direction is closest to your actual use case, and — if useful — treat this
build itself as the starting point of the engagement rather than a
throwaway demo.

*(If a genuinely comparable shipped project exists by the time this goes to
the client, replace this section with that instead — a real case study
beats this argument. Don't add one without real specifics behind it.)*
