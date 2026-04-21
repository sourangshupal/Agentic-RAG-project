# Step-by-Step Local Development Guide
## arXiv Paper Curator — Phase by Phase Setup

---

## Prerequisites — Install These First

| Tool | Why Needed | How to Install |
|------|-----------|---------------|
| **Docker Desktop** | Runs all 13 services | Download from docker.com |
| **Python 3.12+** | Local dev & notebooks | `brew install python@3.12` (Mac) / python.org (Windows) |
| **UV** | Package manager | See Step 1 below |
| **Jina AI API Key** | Vector embeddings (Phase 4+) | Sign up free at jina.ai |

**Hardware minimums:**
- 8GB RAM (10GB+ recommended)
- 10GB free disk space
- Docker Desktop with memory set to 8GB+ (Docker Desktop → Settings → Resources → Memory)

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
```

### Step 3 — Create Your `.env` File

```bash
cp .env.example .env
```

Open `.env` and update only these 4 values:

```dotenv
# Free key from jina.ai
JINA_API_KEY=jina_xxxxxxxxxxxxxxxx

# Run this in terminal → paste output here:  openssl rand -base64 32
LANGFUSE_NEXTAUTH_SECRET=<paste output>
LANGFUSE_SALT=<paste output>

# Run this in terminal → paste output here:  openssl rand -hex 32
LANGFUSE_ENCRYPTION_KEY=<paste output>
```

Leave everything else as-is. The defaults work for local development.

### Step 4 — Install Python Dependencies

```bash
uv sync
```

Creates `.venv/` and installs all packages. Takes 2–3 minutes the first time.

---

## Phase 1 — Infrastructure Foundation

**Goal:** Start all services and verify the infrastructure is working.

### Start All Containers

```bash
docker compose up --build -d
```

> First run downloads ~3GB of Docker images. This takes 10–15 minutes.

### Watch Startup Progress

```bash
docker compose ps         # check all container statuses
docker compose logs -f    # stream live logs (Ctrl+C to stop)
```

Wait until these containers show `healthy`:

```
rag-api           healthy
rag-postgres      healthy
rag-opensearch    healthy
rag-redis         healthy
rag-ollama        healthy
rag-airflow       healthy
```

The Langfuse containers take the longest (up to 5 minutes).

### Pull the LLM Model — One-Time Step

Ollama starts empty. Pull the model manually:

```bash
docker exec -it rag-ollama ollama pull llama3.2:1b
```

Downloads ~1.3GB. Wait for `success`.

### Verify Health

```bash
make health
# or:
curl http://localhost:8000/api/v1/health
# Expected response: {"status":"ok"}
```

### Open the Phase 1 Notebook

```bash
uv run jupyter notebook notebooks/phase1/phase1_setup.ipynb
```

Follow the notebook to verify each service one by one.

### Services Available This Phase

| Service | URL | What to Explore |
|---------|-----|----------------|
| API Docs | http://localhost:8000/docs | Try the `/health` endpoint |
| Airflow | http://localhost:8080 | See the `hello_world_dag` |
| OpenSearch Dashboards | http://localhost:5601 | Explore the empty index |

> **Airflow login:** Check `airflow/simple_auth_manager_passwords.json.generated` for auto-generated credentials.

### Phase 1 Checklist

- [ ] All containers showing `healthy` in `docker compose ps`
- [ ] `curl http://localhost:8000/api/v1/health` returns `{"status":"ok"}`
- [ ] Airflow UI accessible at http://localhost:8080
- [ ] `hello_world_dag` visible in Airflow
- [ ] OpenSearch Dashboards accessible at http://localhost:5601
- [ ] Ollama model pulled successfully

---

## Phase 2 — Data Ingestion Pipeline

**Goal:** Automatically fetch papers from arXiv, parse their PDFs, and store them in PostgreSQL.

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
  → Parse with Docling (extracts text + sections + references)
  → Store in PostgreSQL
  → Generate run statistics report
```

Takes ~5–10 minutes for 15 papers.

### Verify Papers Are Stored

```bash
docker exec -it rag-postgres psql -U rag_user -d rag_db \
  -c "SELECT arxiv_id, title, pdf_processed FROM papers LIMIT 5;"
```

You should see paper rows with titles and `pdf_processed = true`.

### Phase 2 Checklist

- [ ] `arxiv_paper_ingestion` DAG ran successfully in Airflow
- [ ] Papers visible in PostgreSQL (query above)
- [ ] No failed tasks in the Airflow DAG run
- [ ] At least 10 papers stored with `pdf_processed = true`

---

## Phase 3 — BM25 Keyword Search

**Goal:** Index papers into OpenSearch and search them using BM25 keyword matching.

### Open the Phase 3 Notebook

```bash
uv run jupyter notebook notebooks/phase3/phase3_opensearch.ipynb
```

### Try the Search API

Open http://localhost:8000/docs → find `/api/v1/hybrid-search/` → click **Try it out** → paste:

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

### What to Observe

- Results are ranked by keyword relevance score
- Papers with your query terms in title/abstract rank higher
- Try different queries and compare scores

### Phase 3 Checklist

- [ ] OpenSearch index `arxiv-papers-chunks` created
- [ ] Papers indexed (check OpenSearch Dashboards at http://localhost:5601)
- [ ] BM25 search returning results via `/api/v1/hybrid-search/`
- [ ] Results ranked by relevance score

---

## Phase 4 — Hybrid Search (BM25 + Vector Embeddings)

**Goal:** Add semantic vector search on top of BM25 using Jina AI embeddings and RRF fusion.

> **Requires `JINA_API_KEY` set in your `.env` file.**

### Open the Phase 4 Notebook

```bash
uv run jupyter notebook notebooks/phase4/phase4_hybrid_search.ipynb
```

### What Changes This Phase

Papers are re-indexed with vector embeddings per chunk:

```
Paper text
  → TextChunker splits into 600-word chunks (with 100-word overlap)
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

### Compare BM25 vs Hybrid

Run the same query twice — once with `use_hybrid: false` and once with `use_hybrid: true`. Notice:
- Hybrid finds semantically related papers even without exact keyword matches
- BM25 only matches papers with the exact words you typed
- RRF (Reciprocal Rank Fusion) combines both scores into one ranking

### Phase 4 Checklist

- [ ] Jina API key set in `.env`
- [ ] Papers re-indexed with vector embeddings
- [ ] Hybrid search returning results with `search_mode: "hybrid"` in response
- [ ] Semantic queries finding relevant papers without exact keyword matches

---

## Phase 5 — Complete RAG Pipeline

**Goal:** Connect hybrid search to Ollama LLM to answer natural language questions.

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
  "model": "llama3.2:1b",
  "categories": []
}
```

Response includes:
- `answer` — LLM-generated answer using retrieved paper content
- `sources` — which papers were used
- `chunks_used` — how many text chunks provided as context
- `search_mode` — `hybrid` or `bm25`

First response takes 10–30 seconds (LLM generation). Be patient.

### Try Streaming (Word-by-Word Response)

Use `/api/v1/stream` with the same request body — returns the answer word-by-word like ChatGPT.

### Launch the Gradio Chat UI

```bash
# Open a new terminal (keep docker running)
source .venv/bin/activate       # Mac/Linux
# .venv\Scripts\activate        # Windows

python gradio_launcher.py
```

Open http://localhost:7861 — a full chat interface for your RAG system.

### Phase 5 Checklist

- [ ] `/api/v1/ask` returning an LLM-generated answer
- [ ] Response includes `sources` and `chunks_used`
- [ ] `/api/v1/stream` returning a streaming response
- [ ] Gradio UI accessible at http://localhost:7861
- [ ] Can chat with the system and get answers about research papers

---

## Phase 6 — Production Monitoring & Caching

**Goal:** Add Langfuse tracing so you can observe the pipeline, and Redis caching so repeated queries are instant.

### Open the Phase 6 Notebook

```bash
uv run jupyter notebook notebooks/phase6/phase6_cache_testing.ipynb
```

### Set Up Langfuse

1. Open http://localhost:3001
2. Login with: `admin@example.com` / `admin123`
3. Go to **Settings → API Keys → Create new key**
4. Copy the Public Key (`pk-lf-...`) and Secret Key (`sk-lf-...`)
5. Open your `.env` file and update:

```dotenv
LANGFUSE_PUBLIC_KEY=pk-lf-your-actual-key-here
LANGFUSE_SECRET_KEY=sk-lf-your-actual-key-here
LANGFUSE_ENABLED=true
```

6. Restart the API to pick up the new keys:

```bash
docker compose restart api
```

### See Tracing in Action

1. Ask a question via http://localhost:8000/docs → `/api/v1/ask`
2. Open Langfuse at http://localhost:3001 → click **Traces**
3. Click on the trace to see every step:
   - Time taken for embedding generation
   - Time taken for OpenSearch query
   - Prompt construction details
   - LLM generation time
   - Total end-to-end latency

### See Caching in Action

```bash
# Ask the exact same question twice via the API
# First call:  ~10-30 seconds (LLM generation)
# Second call: <100ms (Redis cache hit — 150-400x faster)
```

The `trace_id` in the response links back to Langfuse for debugging.

### Phase 6 Checklist

- [ ] Langfuse UI accessible and showing traces after each `/ask` call
- [ ] Each trace shows embedding, search, prompt, and generation spans
- [ ] Second call to same query returns in under 100ms (cache hit)
- [ ] Langfuse dashboard shows latency metrics

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
  "model": "llama3.2:1b",
  "categories": []
}
```

The response now includes `reasoning_steps` — the agent's full thought process:

```json
{
  "answer": "...",
  "sources": [...],
  "reasoning_steps": [
    {"step": "guardrail",        "score": 8.5, "decision": "valid query"},
    {"step": "retrieve",         "decision": "called retriever tool"},
    {"step": "grade_documents",  "relevant": 4, "total": 5, "decision": "sufficient"},
    {"step": "generate",         "decision": "answer generated"}
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
  "model": "llama3.2:1b",
  "categories": []
}
```

The guardrail node detects this is not about research papers and returns a polite refusal. The LLM never runs — saves cost and prevents hallucination.

### Test the Retry Loop

Ask a very obscure or poorly worded question. Watch `reasoning_steps` — if grading fails, you'll see:
- `rewrite_query` step appears
- `retrieval_attempts` becomes 2 or 3
- Agent rewrites and retries automatically

### Set Up Telegram Bot (Optional)

1. Open Telegram → search for `@BotFather`
2. Send `/newbot` → follow the prompts → copy the bot token
3. Update `.env`:

```dotenv
TELEGRAM__BOT_TOKEN=your-bot-token-here
TELEGRAM__ENABLED=true
```

4. Restart the API:

```bash
docker compose restart api
```

5. Open Telegram → find your new bot → ask it a research question

### Phase 7 Checklist

- [ ] `/api/v1/ask-agentic` returning answer with `reasoning_steps`
- [ ] Guardrail correctly blocking off-topic queries
- [ ] `retrieval_attempts` visible in response
- [ ] Query rewriting visible when retrieval fails
- [ ] (Optional) Telegram bot responding to research questions

---

## Switching Between Phases

The repository tags each phase's code as a release. To go back to a specific phase's state:

```bash
# Clone a specific phase (fresh start)
git clone --branch phase3.0 https://github.com/jamwithai/Agentic-RAG-project
cd Agentic-RAG-project
uv sync
docker compose down -v
docker compose up --build -d
```

Available tags: `phase1.0`, `phase2.0`, `phase3.0`, `phase4.0`, `phase5.0`, `phase6.0`, `phase7.0`

---

## All Commands — Quick Reference

```bash
# ── Service Management ─────────────────────────────────────────
make start                          # start all services
make stop                           # stop all services
make restart                        # restart all services
make status                         # show container statuses
make health                         # check all service health endpoints
make logs                           # stream all logs

# ── Individual Service Logs ────────────────────────────────────
docker compose logs -f api
docker compose logs -f airflow
docker compose logs -f opensearch
docker compose logs -f ollama

# ── Restart a Single Service ───────────────────────────────────
docker compose restart api
docker compose restart airflow

# ── Testing ────────────────────────────────────────────────────
make test                           # run all tests
uv run pytest tests/unit/ -v        # unit tests only
uv run pytest tests/api/ -v         # API tests only
uv run pytest tests/unit/services/agents/ -v   # agent tests only
uv run pytest -k "test_guardrail"   # run tests matching a name
make test-cov                       # tests with coverage report

# ── Code Quality ───────────────────────────────────────────────
make format                         # auto-format code (ruff)
make lint                           # lint + type check (ruff + mypy)

# ── LLM Model Management ───────────────────────────────────────
docker exec -it rag-ollama ollama list          # see installed models
docker exec -it rag-ollama ollama pull llama3.2:1b    # small, fast
docker exec -it rag-ollama ollama pull llama3.1:8b    # bigger, smarter

# ── Database ───────────────────────────────────────────────────
docker exec -it rag-postgres psql -U rag_user -d rag_db
# Inside psql:
#   \dt               list tables
#   SELECT COUNT(*) FROM papers;
#   SELECT arxiv_id, title FROM papers LIMIT 5;
#   \q                quit

# ── Nuclear Reset (deletes all data) ──────────────────────────
docker compose down --volumes
docker compose up --build -d
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| OpenSearch won't start | Not enough memory | Increase Docker Desktop RAM to 10GB+ |
| `rag-api` stays unhealthy | Startup error | Run `docker compose logs api` to see the error |
| Can't log into Airflow | Wrong credentials | Check `airflow/simple_auth_manager_passwords.json.generated` |
| Search returns 0 results | Papers not indexed | Trigger `arxiv_paper_ingestion` DAG in Airflow first |
| Ollama returns empty answer | Model not pulled | Run `docker exec -it rag-ollama ollama pull llama3.2:1b` |
| Port already in use | Another service on same port | Run `docker compose down` then try again |
| Slow LLM responses | Small model on limited hardware | Normal — llama3.2:1b is minimal; use llama3.1:8b for better quality |
| WSL/Ubuntu permission error | User ID mismatch | Uncomment `user: "50000:0"` in `compose.yml` under the airflow service |
| Jina API errors | Invalid or missing key | Check `JINA_API_KEY` in `.env` is correct |
| Langfuse not showing traces | Keys not configured | Follow Phase 6 Langfuse setup steps, restart API after updating `.env` |

---

## Service URLs — All in One Place

| Service | URL | Credentials |
|---------|-----|------------|
| API + Swagger Docs | http://localhost:8000/docs | none |
| Gradio Chat UI | http://localhost:7861 | none |
| Langfuse Tracing | http://localhost:3001 | admin@example.com / admin123 |
| Airflow Pipelines | http://localhost:8080 | see `airflow/simple_auth_manager_passwords.json.generated` |
| OpenSearch Dashboards | http://localhost:5601 | none |
| Ollama API | http://localhost:11434 | none |
| PostgreSQL | localhost:5432 | rag_user / rag_password / rag_db |
| Redis | localhost:6379 | no password |

---

## The Full Architecture Progression

```
Phase 1   Docker + FastAPI + PostgreSQL + OpenSearch + Airflow
            ↓
Phase 2   + arXiv fetching + PDF parsing (Docling) → PostgreSQL storage
            ↓
Phase 3   + OpenSearch BM25 indexing → keyword search API
            ↓
Phase 4   + Jina embeddings + vector chunks → hybrid BM25+vector search with RRF
            ↓
Phase 5   + Ollama LLM + RAG prompt builder → /ask + /stream + Gradio UI
            ↓
Phase 6   + Langfuse tracing + Redis caching → observability + 150x speedup
            ↓
Phase 7   + LangGraph agent (guardrail → retrieve → grade → rewrite → generate)
           + Telegram Bot → mobile conversational access
```

Each phase adds to the previous — nothing gets replaced until Phase 7 where the simple RAG chain is upgraded to a full LangGraph agent.
