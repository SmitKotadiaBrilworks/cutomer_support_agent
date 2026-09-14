# Recommended backend architecture for an AI-heavy consumer application

*(Answer to: "What backend architecture and technology stack would you
recommend for an AI-heavy consumer application, particularly with
scalability and maintainability in mind?")*

The short version: treat the LLM as one more backend dependency behind a
stable API contract — not as the architecture itself. The system needs to
stay scalable and maintainable even as models, prompts, and providers change
underneath it. This POC's structure (a thin API layer, an orchestration
layer, a model-provider layer, and a data layer, each independently
swappable) is a scaled-down version of the same shape we'd recommend for
production — and sections 4 and 5 below (Postgres system-of-record + Redis
session state + pgvector RAG) aren't just described here, they're wired up
and working in the repo behind `STORE_BACKEND=postgres` (see README →
"Optional: real production-infra mode"), not left as a diagram.

## 1. API layer
- **FastAPI** (Python) or **NestJS** (TypeScript) — whichever matches the
  rest of the team's stack. Thin: request validation, auth, rate limiting,
  routing to the orchestration layer. No business/prompt logic here.
- Stream responses (SSE or WebSockets) for anything conversational — users
  tolerate LLM latency far better when they see tokens arriving.

## 2. Orchestration layer
- **LangGraph** for anything with more than one decision point: multi-step
  workflows, tool calling, conditional branching (escalation, retries,
  human-in-the-loop), and state that needs to persist across turns. This is
  the layer this POC's `graph.py` lives in.
- Keep orchestration graphs and prompts in version control, reviewed like
  code — prompt changes are behavior changes.

## 3. Model-provider layer
- Abstract model access behind a single interface (LangChain's chat model
  interface works well) so the app isn't hard-wired to one vendor.
- **Fallback chains** (as in this POC's `llm_providers.py`) for resilience —
  a provider outage or rate limit shouldn't take the product down.
- **Cost/latency routing**: cheap/fast models (e.g. mini/flash tiers) for
  classification and routing steps, stronger models reserved for generation
  that actually needs them. Classification in this POC is a good example of
  a step that doesn't need a frontier model.
- Cache deterministic or frequently-repeated calls where correctness allows.

## 4. Memory & state
- **Short-term (per-conversation)**: a checkpointer-backed store — Redis for
  low-latency session state, or Postgres if you want it queryable/durable.
  This POC uses LangGraph's `MemorySaver` (in-process) as a stand-in; it's a
  one-line swap to `PostgresSaver`/`RedisSaver` for production.
- **Long-term (cross-session)**: user preferences, history, and profile data
  belong in your regular transactional DB, not stuffed into every prompt.
- **Semantic memory / RAG**: a vector store (pgvector if you want to stay in
  Postgres, or a dedicated service like Pinecone/Weaviate) for knowledge-base
  or document retrieval — this POC's `search_faq` is a placeholder for that.

## 5. Data layer
- **Postgres** as the system of record (orders, tickets, users, audit log).
- **Redis** for session/cache.
- **Vector store** for embeddings, if/when RAG is needed.
- Keep the AI layer stateless wherever possible — state lives in these
  stores, not in the process — so API instances can scale horizontally.

## 6. Evaluation & observability
- **Tracing**: LangSmith or Langfuse for per-run traces (prompts, tool calls,
  latencies, token costs) — essential for debugging agent behavior, which is
  much harder to reason about than a normal API's stack trace.
- **Offline eval**: a labeled dataset (this POC's `eval/eval_dataset.jsonl`)
  run in CI on every change to prompts/graph — catches regressions before
  they ship, the same way unit tests catch logic regressions.
- **Online eval**: sampled LLM-as-judge scoring plus real user feedback
  (thumbs up/down, escalation rate, resolution rate) to catch drift that
  offline tests miss.
- **Structured logging/metrics** on every AI call: latency, provider used,
  tokens, cost, fallback triggered — feed into normal ops dashboards/alerts.

## 7. Scalability & maintainability

| Concern | Approach |
|---|---|
| Horizontal scaling | Stateless API/orchestration pods behind a load balancer; state in Redis/Postgres, not memory |
| Latency under load | Streaming responses, async I/O throughout, connection pooling to model providers |
| Cost at scale | Model routing by task complexity, caching, token budgets per request |
| Vendor risk | Provider-abstracted model layer with fallbacks (this POC's approach) |
| Prompt/graph maintainability | Version-controlled prompts, structured-output schemas (Pydantic) instead of regex-parsing free text, small single-purpose nodes over one giant prompt |
| Regression safety | CI-gated eval suite, canary/blue-green deploys |
| Security & compliance | Secrets in a proper secrets manager, PII redaction before logging/tracing, prompt-injection-aware tool design (validate tool inputs, least-privilege tool scopes) |

## 8. Deployment
- Containerize (Docker), deploy on ECS/Cloud Run/Kubernetes depending on the
  team's existing infra — no strong opinion here, consistency with the rest
  of the org's stack matters more than the specific platform.
- CI/CD with automated eval as a merge gate for anything touching prompts or
  the orchestration graph.
