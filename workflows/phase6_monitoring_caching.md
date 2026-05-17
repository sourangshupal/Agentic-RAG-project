# Phase 6: Production Monitoring & Caching

Phase 6 makes the RAG pipeline production-ready by adding two layers: exact-match response caching via Upstash Redis (100x+ speedup on repeated queries) and end-to-end pipeline tracing via Langfuse Cloud.

---

## 1. Cache-First Request Pattern

```mermaid
flowchart TD
    REQ[POST /api/v1/ask\nAskRequest] --> KEY[_generate_cache_key\nSHA256 hash of:\nquery + model + top_k\n+ use_hybrid + sorted categories\ntruncated to first 16 chars]
    KEY --> RGET[Redis GET\nexact_cache:{key}]

    RGET --> HIT{cache\nhit?}
    HIT -->|YES\nO1 Redis read| CACHED_RESP[Return cached AskResponse\n0 embedding cost\n0 search cost\n0 LLM cost]
    HIT -->|NO| PIPELINE[Full RAG pipeline\nembed + search + LLM]

    PIPELINE --> RSET[Redis SET\nexact_cache:{key}\nvalue: serialized AskResponse\nEX: 21600 seconds = 6 hours]
    RSET --> FRESH_RESP[Return fresh AskResponse]

    CACHED_RESP --> CLIENT[Client]
    FRESH_RESP --> CLIENT
```

---

## 2. Cache Key Generation Detail

```mermaid
flowchart LR
    Q[query string] --> HASH
    M[model name] --> HASH
    K[top_k int] --> HASH
    H[use_hybrid bool] --> HASH
    C[categories sorted list] --> HASH
    HASH[SHA256\ndigest] --> KEY2["exact_cache:{first 16 chars of hex digest}"]
    KEY2 --> REDIS[(Upstash Redis\nTLS rediss://\nTTL: 6h)]
```

---

## 3. Langfuse Trace Lifecycle

```mermaid
flowchart TD
    subgraph TRACER["LangfuseTracer — src/services/langfuse/"]
        INIT[Init Langfuse v3 client\npublic_key + secret_key + host] --> CB[get_callback_handler\nfor LangChain auto-tracing]
        INIT --> CTX[trace_langgraph_agent\ncontext manager\nwraps graph execution]
        INIT --> FB[submit_feedback\nclient.score\ntrace_id, score, comment]
        INIT --> FLUSH[flush / shutdown\nbatch send pending spans]
    end

    subgraph RAG_TRACER["RAGTracer — per-request spans"]
        TR[trace_request\nroot span] --> TE[trace_embedding]
        TE --> TS[trace_search]
        TS --> TP[trace_prompt_construction]
        TP --> TG[trace_generation]
        TG --> ER[end_request\nattach duration + response]
    end

    RAG_TRACER -->|flush on completion| LANGFUSE_CLOUD[Langfuse Cloud\nus.cloud.langfuse.com\nLatency / Tokens / Cost dashboard]
    FB -->|POST /api/v1/feedback| LANGFUSE_CLOUD
```

---

## 4. Feedback Loop

```mermaid
flowchart LR
    USER[User sees answer] -->|rates response| CLIENT3[Client]
    CLIENT3 -->|POST /api/v1/feedback\ntrace_id, score 0-1, comment| FEEDBACK_R[agentic_ask.py\nsubmit_feedback handler]
    FEEDBACK_R --> LF_TRACER[langfuse_tracer\nsubmit_feedback\nclient.score call]
    LF_TRACER --> LF_CLOUD[Langfuse Cloud\nscore attached to trace\nvisible in trace detail view]
    FEEDBACK_R --> FLUSH2[tracer.flush\nsend immediately]
    FEEDBACK_R --> RESP4[FeedbackResponse\nsuccess: true/false]
```

---

## 5. Observability Data Captured Per Request

```mermaid
flowchart TD
    SPAN_ROOT[Root Trace\nname: rag_request\nuser_id, query] --> SPAN1[Embedding Span\nlatency ms\nmodel: jina-embeddings-v3\nvector dimensions]
    SPAN_ROOT --> SPAN2[Search Span\nlatency ms\nquery text\ntop_k, use_hybrid\nresults count, arxiv_ids]
    SPAN_ROOT --> SPAN3[Prompt Span\nlatency ms\nchunks list\nfinal prompt string]
    SPAN_ROOT --> SPAN4[Generation Span\nlatency ms\nmodel: gpt-4o-mini\nprompt tokens\ncompletion tokens\ntotal tokens\nestimated cost]
    SPAN_ROOT --> META[Request Metadata\ntotal duration ms\ncache_hit: bool\nsearch_mode: hybrid/bm25]
```

---

## 6. Cost Comparison: Cache Hit vs Miss

```mermaid
flowchart LR
    subgraph HIT_PATH["Cache HIT"]
        H1[Redis GET\n~1ms] --> H2[Return response\n0 OpenAI tokens\n0 Jina API calls]
    end
    subgraph MISS_PATH["Cache MISS"]
        M1[Jina embed\n~100ms] --> M2[OpenSearch search\n~50-200ms]
        M2 --> M3[OpenAI gpt-4o-mini\n~1-3s\n~500-2000 tokens]
        M3 --> M4[Redis SET\n~1ms]
    end
```
