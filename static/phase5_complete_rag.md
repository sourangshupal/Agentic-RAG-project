```mermaid
flowchart TD
    CLIENT[Client] -->|POST /api/v1/ask\nAskRequest| ROUTER[ask.py\nask_question handler]

    ROUTER --> CACHE_CHECK{Redis\ncache check\nSHA256 key}
    CACHE_CHECK -->|HIT| CACHED[Return cached\nAskResponse\n0 LLM cost]
    CACHE_CHECK -->|MISS| PREP[_prepare_chunks_and_sources]

    subgraph PREP["_prepare_chunks_and_sources()"]
        PREP_EMB[embed_query\nJina AI\n1024-dim] --> PREP_SEARCH[search_unified\nuse_hybrid=True\nBM25 + KNN + RRF]
        PREP_SEARCH --> PREP_CHUNKS[Extract top_k chunks\nExtract source PDF URLs]
    end

    PREP_CHUNKS --> PROMPT_B[RAGPromptBuilder\ncreate_rag_prompt\nquery + chunk texts]
    PROMPT_B --> LLM[OpenAILLMClient\ngenerate_rag_answer\nmodel: gpt-4o-mini\ntemperature: 0.0]
    LLM --> LLM_RESP[answer text\nsources list\nconfidence\ncitations]
    LLM_RESP --> CACHE_STORE[Redis SET\nSHA256 key\nTTL: 6 hours]
    CACHE_STORE --> RESP[AskResponse\nquery, answer\nsources, chunks_used\nsearch_mode]
    RESP --> CLIENT

    CLIENT2[Client] -->|POST /api/v1/stream\nAskRequest| STREAM_R[ask.py\nstream_question handler]
    STREAM_R --> SAME_PREP[Same preparation\nembed + hybrid search\nRAGPromptBuilder]
    SAME_PREP --> STREAM_LLM[OpenAILLMClient\ngenerate_rag_answer_stream\nasync generator]
    STREAM_LLM --> SSE[StreamingResponse\ntext/event-stream]
    SSE -->|yield chunk| CLIENT2
    SSE -->|yield done=true| CLIENT2

    TRACE_REQ["RAGTracer.trace_request()\ntrace root span\nuser_id, query"] --> TRACE_EMB["trace_embedding()\nspan: embedding\nquery text"]
    TRACE_EMB --> TRACE_SEARCH["trace_search()\nspan: search\nquery, top_k"]
    TRACE_SEARCH --> TRACE_PROMPT["trace_prompt_construction()\nspan: prompt\nchunks list"]
    TRACE_PROMPT --> TRACE_GEN["trace_generation()\nspan: generation\nmodel, prompt text"]

    TRACE_GEN -->|end_generation| END_GEN["end_generation()\nresponse text\nmodel used"]
    TRACE_SEARCH -->|end_search| END_SEARCH["end_search()\nchunk count\narxiv_ids\ntotal_hits"]
    TRACE_PROMPT -->|end_prompt| END_PROMPT["end_prompt()\nfinal prompt string"]
    TRACE_REQ -->|end_request| END_REQ["end_request()\nAskResponse\ntotal duration ms"]

    END_REQ --> LANGFUSE["Langfuse Cloud\ntrace visible at\nus.cloud.langfuse.com"]

    AREQ["AskRequest\nquery: str 1-1000 chars\ntop_k: int 1-10 default 3\nuse_hybrid: bool default true\nmodel: str default gpt-4o-mini\ncategories: list optional"] --> HANDLER[ask_question]
    HANDLER --> ARESP["AskResponse\nquery: str\nanswer: str\nsources: list of PDF URLs\nchunks_used: int\nsearch_mode: bm25 or hybrid"]

    USER[User\nbrowser] -->|http://localhost:7861| GRADIO[Gradio App\nsrc/gradio_app.py\ngradio_launcher.py]
    GRADIO -->|POST /api/v1/ask\nPOST /api/v1/stream| API[FastAPI :8000]
    GRADIO --> MODEL_SEL[Model selector\ngpt-4o-mini\ngpt-4o\netc.]
    GRADIO --> HYBRID_TOG[Hybrid toggle\nBM25 only vs BM25+vector]
    API --> GRADIO
    GRADIO --> USER
```
