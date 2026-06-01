# arXiv Paper Curator

<div align="center">
  <h3>Production-grade Agentic RAG system for academic research</h3>
  <p>Ingests arXiv papers, indexes them for hybrid search, and answers natural-language questions using OpenAI — built across 7 phases from raw infrastructure to a full LangGraph agent.</p>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/OpenSearch-2.19.5-orange.svg" alt="OpenSearch">
  <img src="https://img.shields.io/badge/OpenAI-gpt--4o--mini-412991.svg" alt="OpenAI">
  <img src="https://img.shields.io/badge/Docker-4%20containers-blue.svg" alt="Docker">
  <img src="https://img.shields.io/badge/AWS%20EKS-Deployed-FF9900.svg" alt="AWS EKS">
  <img src="https://img.shields.io/badge/Kubernetes-1.29+-326CE5.svg" alt="Kubernetes">
  <img src="https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF.svg" alt="CI/CD">
  <img src="https://img.shields.io/badge/Status-Phase%207%20Complete-brightgreen.svg" alt="Status">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

---

## What This System Does

- **Hybrid search** — BM25 + semantic vector search over arXiv papers via OpenSearch RRF fusion
- **Agentic retrieval** — LangGraph agent with guardrails, document grading, and automatic query rewriting
- **Streaming RAG** — OpenAI `gpt-4o-mini` with Server-Sent Events for real-time responses
- **Automated ingestion** — daily Airflow DAG fetching, parsing (Docling), and indexing arXiv papers
- **Production observability** — end-to-end Langfuse tracing + Upstash Redis exact-match caching
- **Telegram bot** — conversational mobile access to the full RAG pipeline
- **Gradio interface** — browser-based chat UI with model selector

---

## 🏗️ System Architecture

The system is built incrementally across 7 phases — each phase adds a distinct architectural layer on top of the previous one.

### Phase 1: Infrastructure Foundation



**Components introduced:**
- **FastAPI** — API framework with health checks and automatic docs
- **OpenSearch** — search engine (BM25 + vector in later phases)
- **Apache Airflow** — workflow orchestration for daily ingestion
- **Neon PostgreSQL** — serverless cloud database for paper metadata

---

### Phase 2: Data Ingestion Pipeline



**Components introduced:**
- **ArxivClient** — rate-limited paper fetching with retry logic
- **PDFParserService** — Docling-powered scientific document extraction
- **MetadataFetcher** — orchestrator coordinating the full ingestion flow
- **Airflow DAG** — scheduled Monday–Friday, 6 AM UTC

---

### Phase 3: Keyword Search (BM25)



**Components introduced:**
- **OpenSearch index** — text mappings with BM25 relevance tuning
- **Query DSL** — support for filters, field boosting, and pagination
- **`/api/v1/hybrid-search/`** — first search endpoint (keyword mode)

---

### Phase 4: Hybrid Search (BM25 + Vectors)



**Components introduced:**
- **Jina AI embeddings** — `jina-embeddings-v3`, 1024-dim vectors via cloud API
- **Text chunker** — section-aware chunking (600-word chunks, 100-word overlap)
- **RRF fusion** — Reciprocal Rank Fusion combines BM25 + vector scores
- **Dense vector index** — `arxiv-papers-chunks` with cosine similarity

---

### Phase 5: Complete RAG Pipeline



**Request flow:**
```
User query
  → Jina AI embeddings
  → OpenSearch hybrid search (BM25 + vector + RRF)
  → RAGPromptBuilder
  → OpenAI gpt-4o-mini
  → streamed answer + source citations
```

**Components introduced:**
- **OpenAI LLM client** — async chat completions with streaming (SSE)
- **RAGPromptBuilder** — prompt templates optimized for academic Q&A
- **`/api/v1/ask`** and **`/api/v1/stream`** endpoints
- **Gradio interface** — browser chat UI with model selector

---

### Phase 6: Production Monitoring & Caching



**Components introduced:**
- **Langfuse Cloud** — automatic trace per request (latency, tokens, cost)
- **Upstash Redis** — SHA256-keyed exact-match cache with 6hr TTL; cache hit skips OpenAI entirely
- **Cache-first pattern** — 100x+ speedup on repeated queries

---

### Phase 7: Agentic RAG with LangGraph & Telegram Bot



#### LangGraph Agent Workflow



**Agent flow:**
```
guardrail_node       → blocks out-of-domain queries before retrieval
  → retrieve_node    → calls OpenSearch retriever tool
  → grade_documents_node  → LLM scores each chunk for relevance
      pass → generate_answer_node → END
      fail → rewrite_query_node → retrieve_node (retry loop)
```

**Components introduced:**
- **LangGraph state machine** — `Runtime[Context]` dependency injection into nodes
- **Guardrail node** — domain boundary detection, prevents hallucination
- **Document grading node** — per-chunk relevance scoring via LLM
- **Query rewrite node** — reformulates query when retrieved docs are insufficient
- **Telegram bot** — async command handlers wired to the full agentic pipeline
- **`/api/v1/ask-agentic`** endpoint

---

## 🚀 Quick Start

### Prerequisites

**Tools:**
- **Docker Desktop** (with Docker Compose)
- **Python 3.12+**
- **UV Package Manager** ([Install Guide](https://docs.astral.sh/uv/getting-started/installation/))

**Cloud Accounts (all free tiers):**
- **OpenAI** — LLM generation → [platform.openai.com](https://platform.openai.com)
- **Jina AI** — Vector embeddings (Phase 4+) → [jina.ai](https://jina.ai)
- **Neon** — Serverless PostgreSQL → [console.neon.tech](https://console.neon.tech)
- **Upstash** — Serverless Redis → [console.upstash.com](https://console.upstash.com)
- **Langfuse Cloud** — Tracing & observability → [cloud.langfuse.com](https://cloud.langfuse.com)

**Hardware:** 6GB+ RAM, 5GB+ free disk space

> **Why cloud services?** Running PostgreSQL, Redis, Langfuse, and a local LLM simultaneously requires 16GB+ RAM. By moving these to managed cloud free tiers, the local stack shrinks to **4 containers** — accessible on any machine.

### Get Started

```bash
# 1. Clone the repository
git clone https://github.com/sourangshupal/Agentic-RAG-project
cd Agentic-RAG-project
git checkout develop

# 2. Install dependencies
uv sync

# 3. Create your .env file with real credentials
# (See step-by-step.md → Step 3 for the full template)
# Key variables needed:
#   OPENAI_API_KEY, POSTGRES_DATABASE_URL (Neon),
#   REDIS__URL (Upstash TCP), LANGFUSE__PUBLIC_KEY,
#   LANGFUSE__SECRET_KEY, JINA_API_KEY

# 4. Verify all cloud APIs are reachable
uv run python scripts/test_connections.py

# 5. Start the 4 local containers
docker compose up --build -d

# 6. Verify everything works
curl http://localhost:8000/api/v1/health
```

> **Important:** Do not `cp .env.example .env` — the example contains placeholder values. Create `.env` fresh with your real credentials. See [step-by-step.md](step-by-step.md) for the exact template.

### Access Your Services

| Service | URL | Purpose |
|---------|-----|---------|
| **API Documentation** | http://localhost:8000/docs | Interactive API testing |
| **Gradio RAG Interface** | http://localhost:7861 | User-friendly chat interface |
| **Airflow Dashboard** | http://localhost:8080 | Workflow management (admin/admin) |
| **OpenSearch Dashboards** | http://localhost:5601 | Search engine UI |
| **Langfuse Cloud** | https://us.cloud.langfuse.com | RAG pipeline tracing |

---

## 📚 Phase 1: Infrastructure Foundation

### Objectives
- Complete infrastructure setup with Docker Compose (4 local containers)
- FastAPI development with automatic documentation and health checks
- Cloud database configuration — Neon serverless PostgreSQL
- OpenSearch hybrid search engine setup
- Service orchestration and health monitoring
- Professional development environment with code quality tools

```bash
uv run jupyter notebook notebooks/phase1/phase1_setup.ipynb
```

---

## 📚 Phase 2: Data Ingestion Pipeline

### Objectives
- arXiv API integration with rate limiting and retry logic
- Scientific PDF parsing using Docling
- Automated data ingestion pipelines with Apache Airflow
- Metadata extraction and storage workflows
- Complete paper processing from API to database

```bash
uv run jupyter notebook notebooks/phase2/phase2_arxiv_integration.ipynb
```

---

## 📚 Phase 3: Keyword Search — The Critical Foundation

### Objectives
- Why keyword search is essential for RAG systems
- OpenSearch index management, mappings, and search optimization
- BM25 algorithm and the math behind effective keyword search
- Query DSL for complex search queries with filters and boosting
- Search analytics for measuring relevance and performance

```bash
uv run jupyter notebook notebooks/phase3/phase3_opensearch.ipynb
```

---

## 📚 Phase 4: Chunking & Hybrid Search — The Semantic Layer

### Objectives
- Section-based chunking with intelligent document segmentation
- Production embeddings with Jina AI (1024-dimensional vectors)
- Hybrid search using RRF fusion for keyword + semantic retrieval
- Unified API design with single endpoint supporting multiple search modes
- Performance analysis between search approaches

```bash
uv run jupyter notebook notebooks/phase4/phase4_hybrid_search.ipynb
```

---

## 📚 Phase 5: Complete RAG Pipeline with OpenAI

### Objectives
- OpenAI API integration (`gpt-4o-mini`) for high-quality, fast generation
- Streaming implementation using Server-Sent Events for real-time responses
- Dual API design with standard and streaming endpoints
- Prompt engineering for academic paper Q&A
- Interactive Gradio interface with model selection

```bash
uv run jupyter notebook notebooks/phase5/phase5_complete_rag_system.ipynb

# Launch Gradio interface
uv run python gradio_launcher.py
# Open http://localhost:7861
```

**Try it:** POST to `/api/v1/ask` with:
```json
{
  "query": "What are the main challenges in training large language models?",
  "top_k": 3,
  "use_hybrid": true,
  "model": "gpt-4o-mini"
}
```

---

## 📚 Phase 6: Production Monitoring and Caching

### Objectives
- Langfuse Cloud integration for end-to-end RAG pipeline tracing
- Upstash Redis caching with intelligent cache keys and TTL management
- Performance monitoring with real-time dashboards for latency and token usage
- Production patterns for observability and optimization
- 100x+ speedup on repeated queries via exact-match cache

```bash
uv run jupyter notebook notebooks/phase6/phase6_cache_testing.ipynb
```

No extra configuration needed — Langfuse Cloud and Upstash are already wired up in your `.env`. Traces appear in your Langfuse project automatically after the first `/ask` call.

---

## 📚 Phase 7: Agentic RAG with LangGraph and Telegram Bot

### Objectives
- LangGraph workflows for state-based agent orchestration
- Guardrail implementation for query validation and domain boundary detection
- Document grading with semantic relevance evaluation
- Query rewriting for automatic query refinement and better retrieval
- Adaptive retrieval with multi-attempt strategies and intelligent fallback
- Telegram bot integration with async operations
- Reasoning transparency by exposing agent decision-making process

```bash
uv run jupyter notebook notebooks/phase7/phase7_agentic_rag.ipynb
```

**Try the guardrail:** POST to `/api/v1/ask-agentic` with `"query": "What is the best pizza recipe?"` — it blocks the query without calling the retriever.

---

## 🌐 AWS EKS Production Deployment

Beyond the local Docker Compose stack, the system is fully deployable to **AWS EKS** (Elastic Kubernetes Service) with automated CI/CD, production-grade monitoring, and infrastructure-as-code scripts.

### Architecture on AWS

```
┌─────────────────────────────────────────────────────────────┐
│                        AWS EKS Cluster                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   API Pod       │  │  Airflow Pod    │  │ OpenSearch   │ │
│  │   (rag-api)     │  │  (airflow)      │  │ + Dashboards │ │
│  │   FastAPI +     │  │  Scheduler +    │  │              │ │
│  │   LangGraph     │  │  Webserver      │  │              │ │
│  └────────┬────────┘  └────────┬────────┘  └──────┬───────┘ │
│           │                    │                    │         │
│  ┌────────┴────────────────────┴────────────────────┴───────┐ │
│  │              LoadBalancer Services (AWS ELB)           │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                     External Cloud Services                  │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ Neon Postgres│ │ Upstash Redis│ │ Langfuse Cloud       │ │
│  │ Grafana Cloud│ │ OpenAI API   │ │ Jina AI Embeddings   │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### What's Included

| Component | What It Does | File |
|---|---|---|
| **EKS Cluster** | Managed Kubernetes with 2x `t3.medium` nodes | `deployment/eks/cluster.yaml` |
| **ECR Repositories** | Private Docker registry for API + Airflow images | `agentic-rag/api`, `agentic-rag/airflow` |
| **CI/CD Pipeline** | GitHub Actions: build images → push to ECR → deploy to EKS | `.github/workflows/cd.yml` |
| **Grafana Cloud** | Kubernetes monitoring: CPU, memory, logs, cost (OpenCost) | `docs/grafana_integration.md` |
| **IRSA** | IAM Roles for Service Accounts (Bedrock access without static keys) | `deployment/eks/` |
| **tear_down.sh** | One-command destruction of all AWS resources | `scripts/tear_down.sh` |
| **infra_start.sh** | One-command creation of the full EKS stack | `scripts/infra_start.sh` |
| **insert_papers_by_id.py** | On-demand ingestion of specific arXiv papers by ID | `scripts/insert_papers_by_id.py` |

### Deploy to AWS

**Option A: Automated script (recommended)**

```bash
chmod +x scripts/infra_start.sh
./scripts/infra_start.sh
```

The script handles: EKS cluster creation → ECR setup → Docker build/push → K8s namespace/secrets → manifest deployment → health verification.

**Option B: CI/CD pipeline**

Push to the `deployment` branch. GitHub Actions automatically:
1. Builds and pushes Docker images to ECR
2. Creates/updates the Kubernetes Secret from GitHub Secrets
3. Applies all deployment manifests
4. Waits for rollouts and prints service endpoints

**Option C: Step-by-step manual**

See `docs/kubernetes.md` for the complete manual deployment guide (copy-paste ready commands for every step).

### Destroy Everything

```bash
chmod +x scripts/tear_down.sh
./scripts/tear_down.sh
```

The script uninstalls Helm releases → deletes K8s namespaces → deletes the EKS cluster → deletes ECR repositories → verifies nothing is left behind. If any step fails, it tells you exactly what needs manual cleanup in the AWS Console.

### Production Monitoring (Grafana Cloud)

The Kubernetes Monitoring Helm chart (`k8s-monitoring-helm` v4) deploys:
- **Grafana Alloy** — metrics and logs collector
- **kube-state-metrics** — Kubernetes object metrics
- **node-exporter** — node-level hardware metrics
- **OpenCost** — per-namespace cost visibility
- **Kepler** — energy consumption tracking

Setup guide: `docs/grafana_integration.md`

### On-Demand Paper Ingestion

Instead of waiting for the scheduled Airflow DAG, ingest specific papers immediately:

```bash
# Inside the Airflow pod
python scripts/insert_papers_by_id.py 1706.03762 1512.03385 1409.1556
```

Fetches metadata from arXiv, downloads PDFs, parses with Docling, chunks, embeds, and indexes to OpenSearch — all in one command.

### Deployment Documentation

| Document | Covers |
|---|---|
| `docs/infra_start.md` | Complete startup guide with architecture, prerequisites, step-by-step deployment, troubleshooting |
| `docs/tear_down.md` | Complete teardown guide with cost analysis, resource-by-resource destruction commands |
| `docs/grafana_integration.md` | Grafana Cloud Kubernetes Monitoring setup, values.yaml, verification, LogQL queries |
| `docs/kubernetes.md` | Manual EKS deployment guide (git-ignored, contains real credentials after use) |

---

## ⚙️ Configuration

**Key environment variables** (see `.env.example` for the full template):

| Variable | Required | Context | Where to get it |
|----------|----------|---------|----------------|
| `OPENAI_API_KEY` | ✅ | All | platform.openai.com → API Keys |
| `JINA_API_KEY` | ✅ | All | jina.ai → API Keys |
| `POSTGRES_DATABASE_URL` | ✅ | All | Neon console → Connection string |
| `REDIS__URL` | ✅ | All | Upstash console → **TCP tab** |
| `LANGFUSE__PUBLIC_KEY` | ✅ | All | Langfuse Cloud → Project Settings → API Keys |
| `LANGFUSE__SECRET_KEY` | ✅ | All | Langfuse Cloud → Project Settings → API Keys |
| `TELEGRAM__BOT_TOKEN` | Optional | 7 | Telegram @BotFather |
| `CLUSTER_NAME` | ✅ | EKS | Your choice (e.g., `agentic-rag-cluster`) |
| `AWS_REGION` | ✅ | EKS | e.g., `us-east-1` |
| `AWS_ACCOUNT_ID` | ✅ | EKS | `aws sts get-caller-identity --query Account` |

> **Double underscore is required** for nested settings (`LANGFUSE__HOST`, `REDIS__URL`, `OPENSEARCH__HOST`). Single-underscore variants are silently ignored by pydantic-settings.

---

## 🔧 Reference

### Technology Stack

| Component | Technology | Where |
|-----------|-----------|-------|
| **API Framework** | FastAPI 0.115+ | Docker / EKS |
| **Search Engine** | OpenSearch 2.19.5 | Docker / EKS |
| **Workflow Orchestration** | Apache Airflow 2.10.3 | Docker / EKS |
| **Search UI** | OpenSearch Dashboards 2.19.5 | Docker / EKS |
| **Database** | Neon (serverless PostgreSQL 17) | Cloud |
| **Cache** | Upstash Redis (serverless) | Cloud |
| **LLM Generation** | OpenAI API (gpt-4o-mini) | Cloud |
| **Embeddings** | Jina AI (1024-dim) | Cloud |
| **Observability** | Langfuse Cloud | Cloud |
| **K8s Monitoring** | Grafana Cloud + Alloy + OpenCost | Cloud |
| **Container Orchestration** | AWS EKS (managed Kubernetes) | AWS |
| **Container Registry** | Amazon ECR | AWS |
| **PDF Parsing** | Docling | In-process |
| **Agent Orchestration** | LangGraph | In-process |

**Dev Tools:** UV, Ruff, MyPy, Pytest  
**CI/CD:** GitHub Actions → Docker Build → ECR Push → EKS Deploy  
**IaC:** `eksctl` + `kubectl` + `helm` + bash scripts

### Project Structure

```
Agentic-RAG-project/
├── src/                         # Main application code
│   ├── routers/                 # API endpoints (search, ask, agentic_ask)
│   ├── services/
│   │   ├── openai_llm/          # OpenAI LLM client (Phase 5+)
│   │   ├── agents/              # LangGraph nodes + workflow (Phase 7)
│   │   ├── opensearch/          # Search client + query builder
│   │   ├── embeddings/          # Jina AI embeddings
│   │   ├── cache/               # Upstash Redis cache
│   │   ├── langfuse/            # Langfuse Cloud tracing
│   │   └── telegram/            # Telegram bot (Phase 7)
│   ├── models/                  # SQLAlchemy models
│   ├── schemas/                 # Pydantic schemas
│   └── config.py                # pydantic-settings configuration
├── airflow/                     # Airflow Dockerfile + DAGs
│   ├── Dockerfile               # Uses uv for fast installs
│   ├── dags/                    # arxiv_paper_ingestion DAG
│   └── entrypoint.sh
├── deployment/                  # AWS EKS Kubernetes manifests
│   ├── eks/                     # Cluster config, namespace, IRSA
│   ├── k8s/api/                 # API Deployment + Service + HPA
│   ├── k8s/airflow/             # Airflow Deployment + Service
│   ├── k8s/opensearch/          # OpenSearch StatefulSet + Service
│   └── k8s/opensearch-dashboards/ # Dashboards Deployment + Service
├── scripts/                     # Utility scripts
│   ├── tear_down.sh             # Destroy all AWS resources
│   ├── infra_start.sh           # Deploy full EKS stack
│   ├── insert_papers_by_id.py  # On-demand paper ingestion by arXiv ID
│   ├── insert_test_paper.py   # Insert a test paper for API validation
│   └── test_connections.py      # Verify all cloud APIs
├── docs/                        # Documentation
│   ├── infra_start.md           # Complete EKS startup guide
│   ├── tear_down.md             # Complete teardown guide
│   ├── grafana_integration.md   # Grafana Cloud K8s monitoring setup
│   └── kubernetes.md            # Manual EKS deployment (git-ignored)
├── .github/workflows/           # CI/CD pipelines
│   └── cd.yml                   # Build → Push → Deploy to EKS
├── opensearch_dashboards/       # OpenSearch Dashboards config
├── notebooks/                   # Phase notebooks (phase1–7)
├── tests/                       # Unit + API tests
├── compose.yml                  # 4-container Docker stack
├── step-by-step.md              # Detailed phase-by-phase guide
└── .env.example                 # Environment template (local + deployment)
```

### API Endpoints

| Endpoint | Method | Description | Phase |
|----------|--------|-------------|-------|
| `/api/v1/health` | GET | Service health check | 1 |
| `/api/v1/hybrid-search/` | POST | BM25 or hybrid search | 3–4 |
| `/api/v1/ask` | POST | RAG question answering | 5 |
| `/api/v1/stream` | POST | Streaming RAG response | 5 |
| `/api/v1/ask-agentic` | POST | Agentic RAG with LangGraph | 7 |
| `/api/v1/feedback` | POST | Submit Langfuse trace feedback | 7 |

**Full docs:** http://localhost:8000/docs

### Essential Commands

```bash
# ── Local Development (Docker Compose) ─────────────────────────
make start                          # start all 4 containers
make stop                           # stop all containers
make health                         # verify all services healthy

# ── AWS EKS Deployment ────────────────────────────────────────
./scripts/infra_start.sh            # deploy full EKS stack from scratch
./scripts/tear_down.sh              # destroy all AWS resources
kubectl get pods -n production -w   # watch live pod status

# ── Verify cloud APIs ──────────────────────────────────────────
uv run python scripts/test_connections.py

# ── Logs ───────────────────────────────────────────────────────
docker compose logs -f api
docker compose logs -f airflow
kubectl logs -n production -l app=rag-api --tail=100    # EKS API logs
kubectl logs -n production -l app=airflow --tail=100    # EKS Airflow logs

# ── Testing ────────────────────────────────────────────────────
make test                           # all tests
uv run pytest tests/unit/ -v        # unit tests
uv run pytest tests/api/ -v         # API tests

# ── Code Quality ───────────────────────────────────────────────
make format                         # ruff format
make lint                           # ruff check + mypy

# ── Nuclear Reset ──────────────────────────────────────────────
# Local:
docker compose down --volumes && docker compose up --build -d
# AWS:
./scripts/tear_down.sh
# Note: Neon and Upstash data is cloud-managed — not deleted by above
```

---

## 🛠️ Troubleshooting

| Problem | Fix |
|---------|-----|
| `test_connections.py` shows ❌ for any service | Check the corresponding credentials in `.env` |
| Langfuse traces not appearing | Use `LANGFUSE__PUBLIC_KEY` (double underscore) — single underscore is silently ignored |
| Upstash Redis connection fails | Use the **TCP tab** URL in Upstash console (`rediss://`), not the REST tab |
| Search returns 0 results | Trigger `arxiv_paper_ingestion` DAG in Airflow first |
| Airflow won't start | Run `docker compose logs airflow` — check Neon connection string |
| OpenSearch won't start | Increase Docker Desktop RAM to 8GB+ |
| `rag-api` stays unhealthy | Run `docker compose logs api` — usually a missing env var |
| Port already in use | Run `docker compose down` then try again |
| **EKS: Airflow `OOMKilled`** | Increase memory limit to `5Gi` in `deployment/k8s/airflow/deployment.yaml` |
| **EKS: API `OOMKilled`** | Increase memory limit to `4Gi` in `deployment/k8s/api/deployment.yaml` |
| **EKS: `ImagePullBackOff`** | Check ECR login and image tag in deployment manifest |
| **EKS: OpenSearch PVC `Pending`** | Install EBS CSI driver addon first (`eksctl create addon --name aws-ebs-csi-driver`) |
| **EKS: arXiv API 429 rate limit** | Wait 30–60 seconds between requests; increase `ARXIV__RATE_LIMIT_DELAY` |

**Resources:**
- Detailed setup: [step-by-step.md](step-by-step.md)
- EKS startup guide: [docs/infra_start.md](docs/infra_start.md)
- EKS teardown guide: [docs/tear_down.md](docs/tear_down.md)
- Phase notebooks: `notebooks/phase1` through `notebooks/phase7`
- Service logs (local): `docker compose logs [service-name]`
- Service logs (EKS): `kubectl logs -n production -l app=[rag-api|airflow|opensearch]`

---

## 💰 Cost

**Local Docker services:** Free  
**Cloud free tiers:** Free (Neon 512MB, Upstash 10k cmd/day, Langfuse 50k traces/month, Grafana Cloud 10k metrics)  
**OpenAI API:** Pay-per-use — `gpt-4o-mini` costs ~$0.00015 per 1k input tokens. A typical RAG question with 3 chunks of context costs under $0.001. With Redis caching, repeated queries cost $0.

**AWS EKS (when running):**

| Resource | Monthly Cost |
|---|---|
| EKS Control Plane | ~$73 |
| EC2 Nodes (2 x t3.medium) | ~$60 |
| Classic ELBs (3) | ~$49 |
| ECR Storage (~4 GB) | ~$0.40 |
| **Total AWS** | **~$183/month** |

> Run `./scripts/tear_down.sh` when not actively using the system to avoid AWS charges. The entire stack can be redeployed in ~20 minutes with `./scripts/infra_start.sh`.

---

## 🤝 Contributing

Issues and pull requests are welcome. For significant changes, open an issue first to discuss the approach.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.

---

<div align="center">
  <p>Built by <a href="https://github.com/sourangshupal">Sourangshu Pal</a></p>
</div>
