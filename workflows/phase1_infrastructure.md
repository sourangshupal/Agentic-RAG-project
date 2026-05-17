# Phase 1: Infrastructure Foundation

Phase 1 establishes the full local + cloud infrastructure that every later phase builds on. Four Docker containers run locally; four managed cloud services are accessed over the network.

---

## 1. Container & Cloud Topology

```mermaid
flowchart TD
    subgraph DOCKER["Docker Compose — rag-network (bridge)"]
        API["rag-api\nFastAPI :8000\n4 Uvicorn workers"]
        OS["rag-opensearch\nOpenSearch 2.19.5\n:9200 / :9600"]
        DASH["rag-dashboards\nOpenSearch Dashboards 2.19.5\n:5601"]
        AF["rag-airflow\nApache Airflow 2.10.3\n:8080"]

        API -->|depends_on healthy| OS
        AF -->|depends_on healthy| OS
        DASH --> OS
    end

    subgraph CLOUD["Cloud-Managed Services"]
        NEON["Neon\nServerless PostgreSQL 17\npaper metadata"]
        UPSTASH["Upstash\nServerless Redis\nexact-match cache"]
        LANGFUSE_C["Langfuse Cloud\nRAG pipeline tracing"]
        OPENAI_C["OpenAI API\ngpt-4o-mini\nJina AI embeddings"]
    end

    API -->|psycopg2 / SQLAlchemy| NEON
    API -->|rediss:// TLS| UPSTASH
    API -->|HTTPS| LANGFUSE_C
    API -->|HTTPS| OPENAI_C
    AF -->|psycopg2| NEON
```

---

## 2. FastAPI Application Startup Sequence

The `lifespan` context manager in `src/main.py` initialises every service in this exact order before the app begins accepting requests.

```mermaid
sequenceDiagram
    participant UV as Uvicorn
    participant MAIN as main.py lifespan
    participant DB as make_database()
    participant OS as make_opensearch_client()
    participant AX as make_arxiv_client()
    participant PDF as make_pdf_parser_service()
    participant EMB as make_embeddings_service()
    participant LLM as make_openai_llm_client()
    participant LF as make_langfuse_tracer()
    participant RC as make_cache_client()
    participant TG as make_telegram_service()

    UV->>MAIN: startup
    MAIN->>DB: connect to Neon PostgreSQL
    DB-->>MAIN: app.state.database
    MAIN->>OS: connect + setup_indices()
    note over OS: creates arxiv-papers-chunks index\ncreates hybrid-rrf-pipeline
    OS-->>MAIN: app.state.opensearch_client
    MAIN->>AX: init arXiv client
    AX-->>MAIN: app.state.arxiv_client
    MAIN->>PDF: init Docling parser
    PDF-->>MAIN: app.state.pdf_parser
    MAIN->>EMB: init Jina AI client
    EMB-->>MAIN: app.state.embeddings_service
    MAIN->>LLM: init OpenAI client
    LLM-->>MAIN: app.state.llm_client
    MAIN->>LF: init Langfuse tracer
    LF-->>MAIN: app.state.langfuse_tracer
    MAIN->>RC: init Redis cache
    RC-->>MAIN: app.state.cache_client
    MAIN->>TG: init Telegram bot (if enabled)
    TG-->>MAIN: app.state.telegram_service
    MAIN-->>UV: app ready — accepting requests
```

---

## 3. Dependency Injection Flow

FastAPI injects services per-request through `src/dependencies.py`. Every handler receives typed clients without touching `app.state` directly.

```mermaid
flowchart LR
    REQ[Incoming Request] --> ROUTER[FastAPI Router]
    ROUTER --> DEP[dependencies.py\nAnnotated aliases]

    DEP --> S[get_settings\nSettings]
    DEP --> D[get_database\nBaseDatabase]
    DEP --> SES[get_db_session\nSession generator]
    DEP --> OS2[get_opensearch_client\nOpenSearchClient]
    DEP --> EMB2[get_embeddings_service\nJinaEmbeddingsClient]
    DEP --> LLM2[get_llm_client\nOpenAILLMClient]
    DEP --> LF2[get_langfuse_tracer\nLangfuseTracer]
    DEP --> RC2[get_cache_client\nCacheClient]
    DEP --> AG[get_agentic_rag_service\nAgenticRAGService]

    S & D & OS2 & EMB2 & LLM2 & LF2 & RC2 --> HANDLER[Route Handler]
    AG --> HANDLER
```

---

## 4. Registered API Routes

```mermaid
flowchart LR
    APP[FastAPI app] --> R1["GET  /api/v1/health\nping.router"]
    APP --> R2["POST /api/v1/hybrid-search/\nhybrid_search.router"]
    APP --> R3["POST /api/v1/ask\nask_router"]
    APP --> R4["POST /api/v1/stream\nstream_router"]
    APP --> R5["POST /api/v1/ask-agentic\nagentic_ask.router"]
    APP --> R6["POST /api/v1/feedback\nagentic_ask.router"]
```
