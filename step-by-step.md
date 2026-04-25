# Step-by-Step Local Development Guide
## arXiv Paper Curator — Phase by Phase Setup

> **Branch: `develop`** — This guide reflects the cloud-services stack (OpenAI, Neon, Upstash, Langfuse Cloud).
> Only **4 Docker containers** run locally. Everything else is a managed cloud service.

---

## Prerequisites — Install These First

| Tool | Why Needed | How to Install |
|------|-----------|---------------|
| **Docker Desktop** | Runs the 4 local containers | Download from docker.com |
| **Python 3.12+** | Local dev & notebooks | `brew install python@3.12` (Mac) / python.org (Windows) |
| **UV** | Package manager | See Step 1 below |
| **OpenAI API Key** | LLM generation (all phases) | platform.openai.com |
| **Jina AI API Key** | Vector embeddings (Phase 4+) | Sign up free at jina.ai |
| **Neon account** | Serverless PostgreSQL | console.neon.tech (free tier) |
| **Upstash account** | Serverless Redis cache | console.upstash.com (free tier) |
| **Langfuse Cloud account** | Tracing & observability | cloud.langfuse.com (free tier) |

**Hardware minimums:**
- 6GB RAM (8GB+ recommended — far less than before, no local LLM needed)
- 5GB free disk space
- Docker Desktop with memory set to 6GB+ (Docker Desktop → Settings → Resources → Memory)

---

## One-Time Machine Setup

### Step 1 — Install UV

```bash
# Mac / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Verify
uv --version
```

### Step 2 — Clone the Repository

```bash
git clone https://github.com/jamwithai/Agentic-RAG-project
cd Agentic-RAG-project
git checkout develop
```

### Step 3 — Create Your `.env` File

**Do NOT copy `.env.example` over your `.env`** — the example has placeholder values.
Create a fresh `.env` with your real credentials:

```dotenv
# ── Application ───────────────────────────────────────────────
DEBUG=true
ENVIRONMENT=development

# ── OpenAI (platform.openai.com → API Keys) ───────────────────
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT=300

# ── Neon Postgres (console.neon.tech → Connection string) ─────
# Use postgresql+psycopg2:// prefix — required for SQLAlchemy
POSTGRES_DATABASE_URL=postgresql+psycopg2://<user>:<password>@<host>.neon.tech/<db>?sslmode=require

# ── Upstash Redis (console.upstash.com → TCP tab, NOT REST tab) ─
REDIS__URL=rediss://default:<token>@<host>.upstash.io:6379
REDIS__TTL_HOURS=6

# ── Langfuse Cloud (us.cloud.langfuse.com → Project Settings → API Keys) ─
# IMPORTANT: double underscore prefix
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=https://us.cloud.langfuse.com
LANGFUSE__ENABLED=true

# ── Jina AI (jina.ai → API Keys) ──────────────────────────────
JINA_API_KEY=jina_...

# ── OpenSearch (local Docker) ──────────────────────────────────
OPENSEARCH__HOST=http://localhost:9200
OPENSEARCH__INDEX_NAME=arxiv-papers-chunks
OPENSEARCH__VECTOR_DIMENSION=1024
```

> **Upstash note:** In the Upstash console, click **Connect → TCP tab** (not the REST tab) to get the `rediss://` URL.

> **Langfuse note:** Use double underscores (`LANGFUSE__PUBLIC_KEY`) — this is how pydantic-settings reads nested config. Single-underscore vars are silently ignored.

### Step 4 — Install Python Dependencies

```bash
uv sync
```

Creates `.venv/` and installs all packages. Takes 1–2 minutes the first time (subsequent runs use the UV cache).

---

## Phase 1 — Infrastructure Foundation

**Goal:** Start the 4 local containers and verify cloud services are reachable.

### Verify Cloud Services First

Before starting Docker, confirm all cloud APIs are reachable:

```bash
uv run python scripts/test_connections.py
```

All 5 checks should be green:
```
✅  OpenAI API
✅  Neon Postgres
✅  Upstash Redis
✅  Langfuse Cloud
✅  Jina AI
```

### Start the 4 Local Containers

```bash
docker compose up --build -d
```

> First run pulls OpenSearch images (~1.5GB) and builds the API and Airflow images. Takes 5–10 minutes.

### Watch Startup Progress

```bash
docker compose ps         # check container statuses
docker compose logs -f    # stream live logs (Ctrl+C to stop)
```

Wait until all containers show `healthy`:

```
rag-api            healthy
rag-opensearch     healthy
rag-dashboards     healthy
rag-airflow        healthy
```

### Verify Health

```bash
curl http://localhost:8000/api/v1/health
```

Expected response:
```json
{
  "status": "ok",
  "services": {
    "database":   {"status": "healthy"},
    "opensearch": {"status": "healthy"},
    "openai":     {"status": "healthy"}
  }
}
```

### Open the Phase 1 Notebook

```bash
uv run jupyter notebook notebooks/phase1/phase1_setup.ipynb
```

### Services Available This Phase

| Service | URL | What to Explore |
|---------|-----|----------------|
| API Docs | http://localhost:8000/docs | Try the `/health` endpoint |
| Airflow | http://localhost:8080 | admin / admin |
| OpenSearch Dashboards | http://localhost:5601 | Explore the empty index |
| Langfuse Cloud | https://us.cloud.langfuse.com | Your project dashboard |

### Phase 1 Checklist

- [ ] `uv run python scripts/test_connections.py` — all 5 green
- [ ] All 4 containers showing `healthy` in `docker compose ps`
- [ ] `curl http://localhost:8000/api/v1/health` returns `{"status":"ok"}`
- [ ] Airflow UI accessible at http://localhost:8080
- [ ] OpenSearch Dashboards accessible at http://localhost:5601

---

## Phase 2 — Data Ingestion Pipeline

**Goal:** Automatically fetch papers from arXiv, parse their PDFs, and store them in Neon PostgreSQL.

### Open the Phase 2 Notebook

```bash
uv run jupyter notebook notebooks/phase2/phase2_arxiv_integration.ipynb
```

### Trigger the Ingestion Pipeline

1. Open Airflow → http://localhost:8080
2. Find the DAG named `arxiv_paper_ingestion`
3. Toggle it **ON** (blue switch on the left)
4. Click the **▶ Trigger DAG** button (play icon)
5. Click into the running DAG to watch individual tasks

What the pipeline does:
```
Fetch 15 cs.AI papers from arXiv API
  → Download PDFs (5 parallel workers)
  → Parse with Docling (extracts text + sections)
  → Store in Neon PostgreSQL
  → Generate run statistics report
```

Takes ~5–10 minutes for 15 papers.

### Verify Papers Are Stored

Connect to Neon via the Neon console SQL editor, or locally:

```bash
# From your local machine (requires psycopg2 installed — already in .venv)
uv run python -c "
import psycopg2, os
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(os.environ['POSTGRES_DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT arxiv_id, title, pdf_processed FROM papers LIMIT 5')
for row in cur.fetchall(): print(row)
conn.close()
"
```

You should see paper rows with titles.

### Phase 2 Checklist

- [ ] `arxiv_paper_ingestion` DAG ran successfully in Airflow
- [ ] Papers visible in Neon PostgreSQL (query above)
- [ ] No failed tasks in the Airflow DAG run
- [ ] At least 10 papers stored

---

## Phase 3 — BM25 Keyword Search

**Goal:** Index papers into OpenSearch and search them using BM25 keyword matching.

### Open the Phase 3 Notebook

```bash
uv run jupyter notebook notebooks/phase3/phase3_opensearch.ipynb
```

### Try the Search API

Open http://localhost:8000/docs → `/api/v1/hybrid-search/` → **Try it out**:

```json
{
  "query": "transformer neural networks",
  "size": 5,
  "from_": 0,
  "use_hybrid": false,
  "latest_papers": false,
  "categories": [],
  "min_score": 0.0
}
```

`use_hybrid: false` = pure BM25 keyword search this phase.

### Phase 3 Checklist

- [ ] OpenSearch index `arxiv-papers-chunks` created
- [ ] Papers indexed (check OpenSearch Dashboards at http://localhost:5601)
- [ ] BM25 search returning results via `/api/v1/hybrid-search/`
- [ ] Results ranked by relevance score

---

## Phase 4 — Hybrid Search (BM25 + Vector Embeddings)

**Goal:** Add semantic vector search using Jina AI embeddings and RRF fusion.

> **Requires `JINA_API_KEY` set in your `.env` file.**

### Open the Phase 4 Notebook

```bash
uv run jupyter notebook notebooks/phase4/phase4_hybrid_search.ipynb
```

### What Changes This Phase

Papers are re-indexed with vector embeddings per chunk:

```
Paper text
  → TextChunker splits into 600-word chunks (100-word overlap)
  → Each chunk → Jina AI API → 1024-dimensional vector
  → Stored in OpenSearch alongside BM25 text fields
```

### Try Hybrid Search

Same endpoint, now with `use_hybrid: true`:

```json
{
  "query": "attention mechanism efficiency improvements",
  "size": 5,
  "from_": 0,
  "use_hybrid": true,
  "latest_papers": false,
  "categories": [],
  "min_score": 0.0
}
```

### Phase 4 Checklist

- [ ] Papers re-indexed with vector embeddings
- [ ] Hybrid search returning results with `search_mode: "hybrid"`
- [ ] Semantic queries finding relevant papers without exact keyword matches

---

## Phase 5 — Complete RAG Pipeline

**Goal:** Connect hybrid search to the OpenAI API to answer natural language questions.

### Open the Phase 5 Notebook

```bash
uv run jupyter notebook notebooks/phase5/phase5_complete_rag_system.ipynb
```

### Ask Your First Question

http://localhost:8000/docs → `/api/v1/ask` → Try it out:

```json
{
  "query": "What are the main challenges in training large language models?",
  "top_k": 3,
  "use_hybrid": true,
  "model": "gpt-4o-mini",
  "categories": []
}
```

Response includes:
- `answer` — OpenAI-generated answer using retrieved paper content
- `sources` — which papers were used
- `chunks_used` — how many text chunks provided as context
- `search_mode` — `hybrid` or `bm25`

Responses are fast — OpenAI API typically responds in 2–5 seconds.

### Try Streaming (Word-by-Word Response)

Use `/api/v1/stream` with the same request body — returns the answer word-by-word like ChatGPT.

### Launch the Gradio Chat UI

```bash
# Open a new terminal (keep docker running)
source .venv/bin/activate       # Mac/Linux
# .venv\Scripts\activate        # Windows

python gradio_launcher.py
```

Open http://localhost:7861 — a full chat interface with model selector (`gpt-4o-mini`, `gpt-4o`).

### Phase 5 Checklist

- [ ] `/api/v1/ask` returning an OpenAI-generated answer
- [ ] Response includes `sources` and `chunks_used`
- [ ] `/api/v1/stream` returning a streaming response
- [ ] Gradio UI accessible at http://localhost:7861
- [ ] Can chat with the system and get answers about research papers

---

## Phase 6 — Production Monitoring & Caching

**Goal:** Observe the pipeline via Langfuse Cloud and see Redis caching make repeated queries instant.

### Open the Phase 6 Notebook

```bash
uv run jupyter notebook notebooks/phase6/phase6_cache_testing.ipynb
```

### Langfuse Cloud is Already Configured

No setup needed — Langfuse Cloud credentials are already in your `.env`. Traces appear automatically.

1. Ask a question via http://localhost:8000/docs → `/api/v1/ask`
2. Open Langfuse → https://us.cloud.langfuse.com → your `agentic-rag` project → **Traces**
3. Click on a trace to see every step:
   - Embedding generation latency
   - OpenSearch query latency
   - Prompt construction
   - LLM generation time and token count
   - End-to-end latency

### See Caching in Action (Upstash Redis)

```bash
# Ask the exact same question twice
# First call:  ~3-5 seconds (OpenAI API)
# Second call: <50ms (Upstash Redis cache hit — 100x+ faster)
```

The cache key is a SHA256 hash of the query + parameters. Exact match only — even a single character difference bypasses the cache (as intended).

### Phase 6 Checklist

- [ ] Langfuse Cloud showing traces after each `/ask` call
- [ ] Each trace shows embedding, search, prompt, and generation spans
- [ ] Second call to the same query returns in under 100ms (cache hit)
- [ ] Langfuse dashboard shows latency and token usage metrics

---

## Phase 7 — Agentic RAG with LangGraph

**Goal:** Replace the simple RAG chain with a LangGraph agent that reasons, validates, grades, retries, and adapts.

### Open the Phase 7 Notebook

```bash
uv run jupyter notebook notebooks/phase7/phase7_agentic_rag.ipynb
```

### Try the Agentic Endpoint

http://localhost:8000/docs → `/api/v1/ask-agentic`:

```json
{
  "query": "What are the latest advances in transformer efficiency?",
  "top_k": 5,
  "use_hybrid": true,
  "model": "gpt-4o-mini",
  "categories": []
}
```

The response includes `reasoning_steps` — the agent's full decision trace:

```json
{
  "answer": "...",
  "sources": [...],
  "reasoning_steps": [
    "Validated query scope (score: 85/100)",
    "Retrieved documents (1 attempt(s))",
    "Graded documents (4 relevant)",
    "Generated answer from context"
  ],
  "retrieval_attempts": 1,
  "trace_id": "abc123"
}
```

### Test the Guardrail (Off-Topic Query)

```json
{
  "query": "What is the best pizza recipe?",
  "top_k": 3,
  "use_hybrid": true,
  "model": "gpt-4o-mini",
  "categories": []
}
```

The guardrail scores this as out-of-scope (low score) and returns a polite refusal without ever calling the retriever or spending tokens on generation.

### Test the Retry Loop

Ask a vague or poorly worded question. Watch `reasoning_steps` — if grading fails:
- A `rewrite_query` step appears
- `retrieval_attempts` becomes 2
- Agent rewrites the query and retries automatically

### Set Up Telegram Bot (Optional)

1. Open Telegram → search for `@BotFather`
2. Send `/newbot` → follow prompts → copy the bot token
3. Update `.env`:

```dotenv
TELEGRAM__BOT_TOKEN=your-bot-token-here
TELEGRAM__ENABLED=true
```

4. Restart the API:

```bash
docker compose restart api
```

5. Open Telegram → find your bot → ask it a research question

### Phase 7 Checklist

- [ ] `/api/v1/ask-agentic` returning answer with `reasoning_steps`
- [ ] Guardrail correctly blocking off-topic queries
- [ ] `retrieval_attempts` visible in response
- [ ] Query rewriting visible when retrieval fails
- [ ] Trace visible in Langfuse Cloud with full agent graph trace
- [ ] (Optional) Telegram bot responding to research questions

---

## All Commands — Quick Reference

```bash
# ── Service Management ─────────────────────────────────────────
make start                          # start all 4 containers
make stop                           # stop all containers
make restart                        # restart all containers
make status                         # show container statuses
make health                         # check all service health
make logs                           # stream all logs

# ── Individual Service Logs ────────────────────────────────────
docker compose logs -f api
docker compose logs -f airflow
docker compose logs -f opensearch
docker compose logs -f opensearch-dashboards

# ── Restart a Single Service ───────────────────────────────────
docker compose restart api
docker compose restart airflow

# ── API Connectivity Check ─────────────────────────────────────
uv run python scripts/test_connections.py   # checks all 5 cloud APIs

# ── Testing ────────────────────────────────────────────────────
make test                           # run all tests
uv run pytest tests/unit/ -v        # unit tests only
uv run pytest tests/api/ -v         # API tests only
uv run pytest tests/unit/services/agents/ -v   # agent tests only
uv run pytest -k "test_guardrail"   # run tests matching a name

# ── Code Quality ───────────────────────────────────────────────
make format                         # auto-format code (ruff)
make lint                           # lint + type check (ruff + mypy)

# ── Database (Neon) ────────────────────────────────────────────
uv run python -c "
import psycopg2, os; from dotenv import load_dotenv; load_dotenv()
conn = psycopg2.connect(os.environ['POSTGRES_DATABASE_URL'])
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM papers'); print('Papers:', cur.fetchone()[0])
conn.close()
"

# ── Nuclear Reset (deletes local OpenSearch data) ─────────────
docker compose down --volumes
docker compose up --build -d
# Note: Neon and Upstash data is cloud-managed — not deleted by the above
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| OpenSearch won't start | Not enough memory | Increase Docker Desktop RAM to 8GB+ |
| `rag-api` stays unhealthy | Startup error | Run `docker compose logs api` to see the error |
| `test_connections.py` shows OpenAI ❌ | Invalid or missing API key | Check `OPENAI_API_KEY` in `.env` |
| `test_connections.py` shows Neon ❌ | Wrong connection string | Check `POSTGRES_DATABASE_URL` — must use `postgresql+psycopg2://` prefix |
| `test_connections.py` shows Redis ❌ | Wrong token or URL format | In Upstash console, use **TCP tab** (not REST tab) for the URL |
| `test_connections.py` shows Langfuse ❌ | Wrong keys or host | Check `LANGFUSE__HOST=https://us.cloud.langfuse.com` (double underscore) |
| Search returns 0 results | Papers not indexed | Trigger `arxiv_paper_ingestion` DAG in Airflow first |
| Can't log into Airflow | Wrong credentials | Default is admin / admin |
| Slow first response | Cold start on OpenAI | Normal for first request — subsequent are faster |
| Langfuse traces not appearing | Single-underscore env vars | Use `LANGFUSE__PUBLIC_KEY` (double underscore) not `LANGFUSE_PUBLIC_KEY` |
| Port already in use | Another service on same port | Run `docker compose down` then try again |
| WSL/Ubuntu permission error | User ID mismatch | Uncomment `user: "50000:0"` in `compose.yml` under the airflow service |
| Jina API errors | Invalid or missing key | Check `JINA_API_KEY` in `.env` |

---

## Service URLs — All in One Place

| Service | URL | Credentials |
|---------|-----|------------|
| API + Swagger Docs | http://localhost:8000/docs | none |
| Gradio Chat UI | http://localhost:7861 | none |
| Airflow Pipelines | http://localhost:8080 | admin / admin |
| OpenSearch Dashboards | http://localhost:5601 | none |
| Langfuse Tracing | https://us.cloud.langfuse.com | your Langfuse credentials |
| Neon Database | https://console.neon.tech | your Neon credentials |
| Upstash Redis | https://console.upstash.com | your Upstash credentials |

---

## Cloud Services — Free Tier Limits

| Service | Free Limit | Notes |
|---------|-----------|-------|
| **Neon** | 512MB storage, 191h compute/month | More than enough for course |
| **Upstash Redis** | 10k commands/day, 256MB | Plenty for dev/testing |
| **Langfuse Cloud** | 50k traces/month | ~1,600 queries/day |
| **OpenAI** | Pay-per-use | `gpt-4o-mini` is very cheap (~$0.00015/1k tokens) |
| **Jina AI** | 1M tokens free | More than enough for indexing |

---

## The Full Architecture

```
Phase 1   Docker (4 containers) + FastAPI + Neon PostgreSQL + OpenSearch + Airflow
            ↓
Phase 2   + arXiv fetching + PDF parsing (Docling) → Neon PostgreSQL storage
            ↓
Phase 3   + OpenSearch BM25 indexing → keyword search API
            ↓
Phase 4   + Jina embeddings + vector chunks → hybrid BM25+vector search with RRF
            ↓
Phase 5   + OpenAI API (gpt-4o-mini) + RAG prompt builder → /ask + /stream + Gradio UI
            ↓
Phase 6   + Langfuse Cloud tracing + Upstash Redis caching → observability + 100x speedup
            ↓
Phase 7   + LangGraph agent (guardrail → retrieve → grade → rewrite → generate)
           + Telegram Bot → mobile conversational access
```

**Local (Docker):** OpenSearch, OpenSearch Dashboards, FastAPI, Airflow
**Cloud:** Neon (Postgres), Upstash (Redis), OpenAI (LLM), Jina AI (embeddings), Langfuse (tracing)
