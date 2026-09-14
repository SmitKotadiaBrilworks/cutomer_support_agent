# UrbanCart Customer Support Agent — Multi-Agent POC

A working, runnable proof-of-concept of a production-style AI customer
support system for an e-commerce brand ("UrbanCart", fictional). Built to
demonstrate — with real, inspectable code and a live demo UI rather than
slides — how Brilworks builds AI products beyond simple API wrapping:
**multiple cooperating agents**, multi-step workflows, structured outputs,
memory/state, tool calling, and evaluation.

See [`docs/client_answers.md`](docs/client_answers.md) for how this POC
answers the four evaluation questions directly, and
[`docs/architecture.md`](docs/architecture.md) for the backend architecture
recommendation for a production, AI-heavy consumer app.

## Four agents, not one

This is a genuine **supervisor / multi-agent** system — four distinct agents,
each with its own system prompt and its own scoped tool access:

1. **Triage Agent** — classifies intent + sentiment (structured output) and
   routes every turn to a specialist.
2. **Order & Returns Agent** — order status & return/refund eligibility.
   Tools: `get_order_status`, `check_return_eligibility`.
3. **FAQ / Knowledge Agent** — shipping, payments, policy, warranty
   questions. Tools: `search_faq`.
4. **Escalation Agent** — drafts and files a support ticket (a second
   structured-output call) and hands off to a human, triggered either
   explicitly or automatically when sentiment stays negative across turns.

Tool access is least-privilege by design: the FAQ agent literally cannot
call order tools, and vice versa — each agent can only do its one job.

## Architecture

```
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
```

- **Memory** — a LangGraph `MemorySaver` checkpointer persists the full
  conversation state (messages, classified intent, which agent is active,
  escalation status) per `session_id`, so multi-turn context works without
  the client resending history. Swap for Postgres/Redis in production — see
  architecture doc.
- **Multi-provider LLM with fallback** — every LLM call goes through
  [`backend/app/llm_providers.py`](backend/app/llm_providers.py), which tries
  **OpenAI → Anthropic (Claude) → Google (Gemini)** in order, and tracks
  which provider actually answered (surfaced live in the UI). Only providers
  with a key set in `.env` are used, so the demo keeps working even if one
  provider's key is missing or its API has an outage — a real production
  resilience/cost-routing pattern, not just a demo trick.

This follows the same core LangGraph patterns (tool nodes + conditional
routing, checkpointer-based memory, structured outputs, supervisor routing)
described in [LangGraph Advanced Concepts: Tools, Memory & Complex Workflows](https://medium.com/@sainadhbahadursha/langgraph-advanced-concepts-mastering-tools-memory-and-complex-workflows-part-8-agentic-ai-410a3a138c0c).

## Project structure

```
customer-support-poc/
├── README.md                  ← you are here
├── docs/
│   ├── client_answers.md      ← direct answers to the 4 evaluation questions
│   └── architecture.md        ← recommended backend architecture & stack
├── backend/                   ← FastAPI + LangGraph (Python)
│   ├── app/
│   │   ├── main.py            ← FastAPI app (/chat, /health, /agents)
│   │   ├── graph.py           ← the 4-agent LangGraph workflow (core of the POC)
│   │   ├── llm_providers.py   ← OpenAI→Claude→Gemini fallback chain
│   │   ├── tools.py           ← agent tools, scoped per agent
│   │   ├── schemas.py         ← Pydantic structured-output & API schemas
│   │   └── mock_data.py       ← fake orders/FAQ DB (swap for real APIs)
│   ├── eval/
│   │   ├── eval_dataset.jsonl ← 8 labeled test conversations
│   │   └── run_eval.py        ← eval harness (accuracy + optional LLM judge)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   ← Next.js (App Router) + TypeScript + Tailwind
│   ├── src/app/page.tsx        ← chat UI
│   ├── src/components/         ← ChatWindow, AgentSidebar (live agent trace)
│   └── .env.local.example
└── docker-compose.yml          ← optional: Postgres (pgvector) + Redis, see below
```

## Setup & run

**Requirements:** Python 3.11+, Node 20+, at least one of an OpenAI /
Anthropic / Google API key.

**1. Backend**

```bash
cd customer-support-poc/backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and paste in at least one API key (OpenAI recommended as primary)

uvicorn app.main:app --reload --port 8000
```

**2. Frontend** (in a second terminal)

```bash
cd customer-support-poc/frontend
npm install
cp .env.local.example .env.local   # defaults to http://localhost:8000, fine as-is
npm run dev
```

Open **http://localhost:3000**. The right-hand sidebar renders a **live,
animated diagram of the actual LangGraph** (not a mockup — it's drawn from
the same topology as `graph.py`): the node(s) and edges involved in the
latest turn light up and pulse as the response comes back, so the
multi-agent routing is something you *watch happen* on a call rather than
something you describe. Below it, a session-metrics panel tracks turns,
escalations, tool calls, response latency, and the live provider mix as the
conversation goes on. Each chat reply also carries its own trace line
(agent path, tools called, provider, classified intent/sentiment, latency)
directly under the message.

Check `http://localhost:8000/health` any time to see which providers are
currently configured (useful for confirming the fallback chain before a demo).

## Optional: real production-infra mode (Postgres + Redis + pgvector)

By default (`STORE_BACKEND=memory`, the setup above) the POC runs on
in-process mock data — nothing external to install, nothing that can fail
mid-demo. Flip one env var and it runs on the *actual* stack recommended in
[`docs/architecture.md`](docs/architecture.md) instead:

- **Postgres** — real system of record for `users`, `orders`, `tickets`, and
  an `audit_log` (every order lookup, return check, FAQ search, and ticket
  creation is logged there).
- **pgvector** — `search_faq` becomes genuine semantic search (OpenAI or
  Google embeddings, cosine similarity) instead of keyword matching.
- **Redis** — the LangGraph conversation checkpointer moves from in-process
  memory to Redis, so state survives a backend restart.

Setup (local Postgres via Docker):

```bash
# from the project root
docker compose up -d
# (no `docker compose` plugin? use plain `docker run` — see docker-compose.yml
# for the exact image/port/env values to pass)

cd backend
source .venv/bin/activate   # if not already active
# in .env: set STORE_BACKEND=postgres (DATABASE_URL/REDIS_URL defaults already
# match docker-compose.yml's ports — 5433 and 6380, chosen to avoid clashing
# with any Postgres/Redis you already have running locally)

python -m scripts.seed_postgres   # one-time: creates schema, seeds data, embeds FAQs
uvicorn app.main:app --reload --port 8000
```

**Using Supabase instead of local Docker Postgres:** skip the `postgres`
service in `docker compose up -d` (keep `redis` running, or point `REDIS_URL`
at a hosted Redis) and set `DATABASE_URL` in `.env` to your Supabase
project's connection string — prefer the **Transaction pooler** string (port
6543) over the direct one, since direct connections are IPv6-only in most
Supabase regions. See the comment block above `DATABASE_URL` in
`.env.example` for the exact gotchas (prepared statements, SSL, and why the
Supabase anon/service_role API keys aren't needed — this app talks raw
Postgres, not Supabase's REST API). Nothing else changes: same
`seed_postgres.py`, same `ensure_schema()`, same tables.

**Sharing a Postgres instance/Supabase project with another app?** Safe by
default — every table this POC creates lives inside its own schema
(`POSTGRES_SCHEMA`, default `urbancart`), not `public`, specifically so it
can't collide with or overwrite tables from something else running against
the same database (even something as common as a `users` table). Verified:
ran `ensure_schema()` against a database that already had `public.users`,
`public.orders` etc. from an earlier test — those rows were untouched, and
the POC's own tables landed entirely in `urbancart.*`. Only the `vector`
extension itself is installed at the database level (extensions aren't
schema-scoped in the same way), which is inherent to Postgres/pgvector, not
specific to this app.

`GET /health` now also reports `store_backend`, and live `postgres`/`redis`
connectivity — the frontend sidebar shows this too. Re-running
`seed_postgres.py` is safe any time (upserts by primary key; skips
re-embedding a FAQ whose text hasn't changed).

Embeddings need their own provider: defaults to OpenAI if `OPENAI_API_KEY`
is set, otherwise Google (`EMBEDDING_PROVIDER` to override) — Anthropic has
no public embeddings API. This was tested end-to-end with a Google key only:
schema creation, seeding, real semantic search (e.g. "what credit cards can
I pay with" correctly matches the payment-methods FAQ with zero shared
keywords), and the Redis-backed checkpointer all confirmed working.

### Sample data to try

Orders: `ORD-1001` … `ORD-1005` (see
[`mock_data.py`](backend/app/mock_data.py) for statuses/dates). Pick a
"logged in as" customer in the header dropdown to match an order to a
customer_id, try an order ID that doesn't exist to see graceful handling, or
an old delivery date to see a return get correctly declined and watch the
Escalation Agent take over after a couple of frustrated turns.

## Deploying to Vercel

**Two separate Vercel projects** from this one repo — Vercel auto-detects
FastAPI in `backend/` and Next.js in `frontend/` and handles both natively.
No custom entrypoint file or `vercel.json` is needed for either app —
Vercel's zero-config Python runtime finds `app/main.py`'s FastAPI `app` and
serves it directly with the app's own route table (`/health`, `/chat`,
`/agents`) unprefixed, identical to local `uvicorn`.

(Earlier attempts added a custom `backend/api/index.py` + `vercel.json`
rewrite, on the assumption that was required — it wasn't, and interacted
badly with the platform's own FastAPI detection, producing a confusing
uniform 404 on every route. Deleting both and trusting zero-config detection
fixed it immediately. A single project serving both apps under one domain
was tried before that, using a root-level `vercel.json` with
`builds`/`routes` mixing `@vercel/next` and `@vercel/python` — that hit an
unrelated Next.js 16.3 "immutable static assets" vs. Preview Comments build
conflict. Two independent zero-config projects avoids all of this.)

**Redis-backed `postgres` mode has a real gotcha**: `langgraph-checkpoint-redis`
needs the RediSearch module (`FT.*` commands) to build its checkpoint index —
**Upstash's Redis product does not support this module** and rejects those
commands outright, which crashes the app at import time (every route 404s
uniformly, since the module never finishes loading — this looks identical
to a routing bug and is easy to misdiagnose as one). If you want `postgres`
mode's durable conversation memory in production, use a Redis provider with
RediSearch support (e.g. Redis Cloud's free tier), not Upstash. Absent that,
**`STORE_BACKEND=memory`** (the default) works with zero external
dependencies beyond an LLM key — no Postgres, no Redis — and is what's
actually deployed right now.

1. **Backend project** — import the repo into Vercel (or run `vercel link`
   from inside `backend/`, which sets Root Directory automatically), with
   **Root Directory** set to `backend`. Set these env vars in the Vercel
   project settings (same meanings as `.env`):
   - `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` — at least one
   - Leave `STORE_BACKEND` unset (defaults to `memory`), or read the Redis
     gotcha above before setting it to `postgres`
   - If using `postgres` mode: `DATABASE_URL` (Supabase Transaction pooler,
     port 6543), `REDIS_URL` (RediSearch-capable, not Upstash),
     `POSTGRES_SCHEMA`, `EMBEDDING_PROVIDER`, `OPENAI_EMBEDDING_MODEL`,
     `GOOGLE_EMBEDDING_MODEL` as needed — and seed Postgres once first:
     `cd backend && source .venv/bin/activate && python -m scripts.seed_postgres`
   - Deploy, then check `https://<backend-project>.vercel.app/health` — it
     reports `store_backend` and, in `postgres` mode, live `postgres`/`redis`
     connectivity.
2. **Frontend project** — import the same repo as a second Vercel project
   (or `vercel link` from inside `frontend/`), **Root Directory** set to
   `frontend`. Set:
   - `NEXT_PUBLIC_API_URL=https://<backend-project>.vercel.app`
   - Deploy.

Notes:
- CORS is currently wide open (`allow_origins=["*"]`) in
  [`app/main.py`](backend/app/main.py) — fine for a demo, worth narrowing to
  the frontend's exact Vercel URL for anything beyond that, since the two
  apps are on different domains here.
- If a multi-step agent turn (several LLM + tool calls) is slow enough to
  hit your plan's function timeout, that's a Vercel dashboard setting to
  check, not a code change.

## Running the evaluation harness

```bash
cd customer-support-poc/backend
python -m eval.run_eval            # intent accuracy, tool-selection accuracy, escalation correctness
python -m eval.run_eval --judge    # also scores reply quality 1-5 via LLM-as-judge
```

Results print to the console and are saved as JSON under
`backend/eval/results/`. This is a starting point for a CI-gated regression
suite in production — see the architecture doc.

## From POC to production

The default demo path (in-memory data, in-memory checkpointer, no auth)
keeps things easy to read end-to-end. The `STORE_BACKEND=postgres` mode
above already proves out the real data/memory layer; what's left for actual
production:

- **Real business data**: point `store/postgres.py` at the real order/CRM/
  helpdesk system instead of seeded demo rows.
- **Streaming**: stream tokens/agent-progress to the frontend over SSE or
  WebSockets instead of waiting for the full reply.
- **ANN index for FAQ**: add an `ivfflat`/`hnsw` index on `faq_embeddings`
  once the knowledge base is larger than a handful of articles (a plain
  scan is faster below that, and it's what's used today).
- **Auth, rate limiting, PII handling.**
- **Observability**: LangSmith/Langfuse tracing per run, plus structured
  logs/metrics.
- **CI-gated evaluation**: run `eval/run_eval.py`-style regression tests on
  every PR that touches prompts or the graph.
- **Deployment**: containerize both services (Docker), run behind a load
  balancer with autoscaling (ECS/Cloud Run/K8s), CI/CD with canary releases;
  serve the Next.js frontend statically or via its own Node runtime.

Full detail in [`docs/architecture.md`](docs/architecture.md).
