# System Overview — arXiv Paper Curator (All 7 Phases)

This diagram shows the complete system across all phases. Each phase adds a distinct architectural layer on top of the previous one.

---

## Full System Architecture

```mermaid
flowchart TD
    subgraph INGESTION["Phase 2: Data Ingestion (Airflow DAG — Mon–Fri 6 AM UTC)"]
        ARXIV[arXiv API\ncs.AI papers] --> DOWNLOADER[PDF Downloader\n5 concurrent workers]
        DOWNLOADER --> DOCLING[Docling Parser\ntext + sections]
        DOCLING --> PG[(Neon PostgreSQL\nPaper metadata)]
    end

    subgraph INDEXING["Phase 4: Chunking & Hybrid Indexing"]
        PG --> CHUNKER[TextChunker\n600w chunks / 100w overlap\nsection-based preferred]
        CHUNKER --> JINA[Jina AI\njina-embeddings-v3\n1024-dim vectors]
        JINA --> OS_IDX[(OpenSearch\narxiv-papers-chunks\nBM25 + knn_vector)]
    end

    subgraph SEARCH["Phase 3 & 4: Search Layer"]
        OS_IDX --> BM25[BM25 Query\nchunk_text×3 title×2 abstract×1]
        OS_IDX --> KNN[KNN Vector Query\ncosine similarity]
        BM25 & KNN --> RRF[RRF Pipeline\nrank_constant=60]
    end

    subgraph RAG["Phase 5: RAG Pipeline"]
        QUERY[User Query] --> EMBED_Q[embed_query\ntask=retrieval.query]
        EMBED_Q --> RRF
        RRF --> PROMPT[RAGPromptBuilder]
        PROMPT --> OPENAI[OpenAI\ngpt-4o-mini]
        OPENAI --> ANSWER[AskResponse\nanswer + sources]
    end

    subgraph CACHE["Phase 6: Caching & Observability"]
        QUERY -->|SHA256 key| REDIS[(Upstash Redis\n6hr TTL)]
        REDIS -->|cache hit| ANSWER
        OPENAI --> LANGFUSE[Langfuse Cloud\ntracing per request]
        FEEDBACK[POST /feedback] --> LANGFUSE
    end

    subgraph AGENTIC["Phase 7: Agentic RAG (LangGraph)"]
        AGENT_Q[User Query] --> GUARDRAIL{Guardrail Node\nscore 0–100}
        GUARDRAIL -->|score >= 60| RETRIEVE[Retrieve Node\ntool call]
        GUARDRAIL -->|score < 60| OOS[Out of Scope\nNode]
        RETRIEVE --> TOOL[ToolNode\nOpenSearch hybrid search]
        TOOL --> GRADE{Grade Documents\nNode}
        GRADE -->|relevant| GEN[Generate Answer\nNode]
        GRADE -->|not relevant\nattempts < 2| REWRITE[Rewrite Query\nNode]
        REWRITE --> RETRIEVE
        GEN --> AGENTIC_RESP[AgenticAskResponse\nanswer + reasoning_steps + trace_id]
    end

    subgraph TELEGRAM["Phase 7: Telegram Bot"]
        TG_MSG[Telegram Message] --> TG_CACHE{Cache check}
        TG_CACHE -->|miss| TG_EMBED[embed_query]
        TG_EMBED --> TG_SEARCH[Hybrid Search]
        TG_SEARCH --> TG_LLM[LLM Answer]
        TG_LLM --> TG_REPLY[Formatted Reply\nwith source URLs]
        TG_CMD[/search command] --> TG_SEARCH
    end

    subgraph INFRA["Phase 1: Infrastructure (Docker — 4 containers)"]
        API[FastAPI :8000] --- OPENSEARCH[OpenSearch :9200]
        API --- AIRFLOW_SVC[Airflow :8080]
        OPENSEARCH --- DASHBOARDS[OpenSearch\nDashboards :5601]
    end

    INFRA -.->|hosts| RAG
    INFRA -.->|hosts| AGENTIC
    INFRA -.->|hosts| TELEGRAM
    OS_IDX -.->|same index| TOOL
```

---

## Phase Build-up Summary

| Phase | What Gets Added | Key Technology |
|-------|----------------|----------------|
| **1** | Docker stack, FastAPI, PostgreSQL, OpenSearch, Airflow | Docker Compose, Neon |
| **2** | Automated paper ingestion DAG | Airflow, Docling, arXiv API |
| **3** | BM25 keyword search endpoint | OpenSearch Query DSL |
| **4** | Vector embeddings + hybrid RRF search + text chunking | Jina AI, OpenSearch KNN |
| **5** | Full RAG pipeline (search → LLM → answer) | OpenAI gpt-4o-mini, Gradio |
| **6** | Exact-match caching + end-to-end tracing | Upstash Redis, Langfuse |
| **7** | Agentic reasoning loop + Telegram bot | LangGraph, python-telegram-bot |
