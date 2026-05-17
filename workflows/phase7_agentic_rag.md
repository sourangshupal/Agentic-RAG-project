# Phase 7: Agentic RAG with LangGraph & Telegram Bot

Phase 7 replaces the single-shot RAG call with an intelligent multi-step agent. A LangGraph state machine decides whether to retrieve, grade retrieved docs, rewrite the query, or reject the question — before generating an answer. A Telegram bot also wraps the full pipeline for mobile access.

---

## 1. LangGraph State Machine — Full Node Graph

```mermaid
flowchart TD
    START([START]) --> GUARD[guardrail_node\nLLM scores query 0-100\nIs this about CS/AI/ML papers?]

    GUARD --> GC{guardrail score\nvs threshold 60}
    GC -->|score >= 60\nin-domain query| RETRIEVE[retrieve_node\nCreate tool call\ntool: retrieve_papers\nargs: query text]
    GC -->|score < 60\nout-of-domain| OOS[out_of_scope_node\nReturn polite refusal\nno retrieval attempted]
    OOS --> END1([END])

    RETRIEVE --> TC{tools_condition\nhas tool_calls?}
    TC -->|yes| TOOL[tool_retrieve\nToolNode executes retrieve_papers\ncalls OpenSearch hybrid search\nreturns ToolMessage with chunks]
    TC -->|no| END2([END])

    TOOL --> GRADE[grade_documents_node\nLLM evaluates relevance\nof each retrieved chunk]
    GRADE --> RD{routing_decision}
    RD -->|relevant chunks found| GEN[generate_answer_node\nLLM generates final answer\nusing relevant context]
    RD -->|not relevant\nretrieval_attempts < 2| REWRITE[rewrite_query_node\nLLM rewrites query\nfor better retrieval\ntemperature: 0.3]
    RD -->|not relevant\nretrieval_attempts >= 2| GEN

    REWRITE -->|new HumanMessage\nwith rewritten query| RETRIEVE
    GEN --> END3([END])
```

---

## 2. AgentState — Data Flowing Through the Graph

```mermaid
flowchart TD
    subgraph STATE["AgentState (TypedDict) — src/services/agents/state.py"]
        MSG["messages\nAnnotated list with add_messages reducer\nHumanMessage / AIMessage / ToolMessage"]
        OQ["original_query\nset by retrieve_node on first attempt"]
        RQ["rewritten_query\nset by rewrite_query_node"]
        RA["retrieval_attempts\nincremented by retrieve_node\nmax: 2 from Context"]
        GR_RES["guardrail_result\nGuardrailScoring\nscore: int, reason: str"]
        RD2["routing_decision\nRoutingDecision\nroute: generate_answer or rewrite_query"]
        SRC["sources\nDict tool_call_id to ToolMessage output"]
        REL_SRC["relevant_sources\nList of SourceItem\narxiv_id, title, authors, url, score"]
        GD["grading_results\nList of GradingResult\ndocument_id, is_relevant, score, reasoning"]
        META["metadata\nruntime analytics / tracing info"]
    end

    GUARD2[guardrail_node] -->|writes| GR_RES
    RETRIEVE2[retrieve_node] -->|writes| OQ & RA & MSG
    TOOL2[tool_retrieve] -->|writes| SRC & MSG
    GRADE2[grade_documents_node] -->|writes| RD2 & REL_SRC & GD
    REWRITE2[rewrite_query_node] -->|writes| RQ & MSG
    GEN2[generate_answer_node] -->|writes| MSG
```

---

## 3. Runtime Context — Dependency Injection into Nodes

Nodes do not use global state. All clients are injected via `Runtime[Context]`.

```mermaid
flowchart LR
    subgraph CTX["Context dataclass — src/services/agents/context.py"]
        LLC[llm_client\nOpenAILLMClient]
        OSC[opensearch_client\nOpenSearchClient]
        EMB3[embeddings_client\nJinaEmbeddingsClient]
        LFT[langfuse_tracer\nOptional LangfuseTracer]
        TR[trace\nOptional LangfuseSpan]
        CFG["model_name: gpt-4o-mini\ntemperature: 0.0\ntop_k: 3\nmax_retrieval_attempts: 2\nguardrail_threshold: 60"]
    end

    CTX -->|injected via context_schema| GRAPH[StateGraph\nAgentState\ncontext_schema=Context]
    GRAPH --> NODES[All nodes receive\nruntime.context\nas second parameter]
```

---

## 4. Node-by-Node Logic Summary

```mermaid
flowchart TD
    subgraph N1["guardrail_node"]
        G_IN[Latest HumanMessage] --> G_LLM[LLM with GUARDRAIL_PROMPT\nreturns GuardrailScoring\nfail-open: default score=100 on LLM error]
        G_LLM --> G_OUT[guardrail_result written to state]
    end

    subgraph N2["retrieve_node"]
        R_IN[Latest query from messages] --> R_CHK{attempts >= max?}
        R_CHK -->|yes| R_FALL[Return fallback AIMessage\nno tool call]
        R_CHK -->|no| R_TOOL[AIMessage with tool_calls\nname: retrieve_papers\nargs: query string]
    end

    subgraph N3["tool_retrieve / ToolNode"]
        T_IN[Tool call from retrieve_node] --> T_EXEC[Execute retrieve_papers tool\nOpenSearch hybrid search\nBM25 + KNN + RRF]
        T_EXEC --> T_OUT[ToolMessage\nformatted paper chunks + metadata]
    end

    subgraph N4["grade_documents_node"]
        GD_IN[Latest query + ToolMessage context] --> GD_LLM[LLM with GRADE_DOCUMENTS_PROMPT\nlooks for binary_score: no in response]
        GD_LLM --> GD_ROUTE[routing_decision: generate_answer or rewrite_query]
    end

    subgraph N5["rewrite_query_node"]
        RW_IN[original_query from state] --> RW_LLM[Structured LLM output\nQueryRewriteOutput Pydantic model\ntemperature: 0.3\nfail-open: keyword expansion]
        RW_LLM --> RW_OUT[New HumanMessage\nwith rewritten_query]
    end

    subgraph N6["generate_answer_node"]
        GA_IN[Latest query + context from ToolMessage] --> GA_LLM[LLM with GENERATE_ANSWER_PROMPT\ntemperature: 0.0\nfail-open: error message]
        GA_LLM --> GA_OUT[AIMessage with final answer]
    end
```

---

## 5. AgenticAskResponse Schema

```mermaid
flowchart LR
    GEN_NODE[generate_answer_node\nfinal AIMessage] --> EXTRACT[ask method extracts\nresult from graph state]
    EXTRACT --> ARESP2["AgenticAskResponse\nquery: str\nanswer: str\nsources: list of SourceItem\nchunks_used: int\nsearch_mode: str\nreasoning_steps: list of str\nretrieval_attempts: int\nrewritten_query: optional str\ntrace_id: optional str for feedback"]
```

---

## 6. Telegram Bot — Handler Flow

```mermaid
flowchart TD
    TG_USER[Telegram User] -->|sends message| BOT[TelegramBot\npython-telegram-bot\nasync polling]

    BOT --> CMD_START["/start command\nWelcome message\nusage instructions"]
    BOT --> CMD_HELP["/help command\nexamples and tips"]
    BOT --> CMD_SEARCH["/search keywords\nhybrid search only\nno LLM generation"]
    BOT --> TEXT_MSG[Text message\nfull RAG pipeline]

    CMD_SEARCH --> SEARCH_FLOW[embed_query\nsearch_unified hybrid=true\ndeduplicate by arxiv_id\nreturn top 5 unique papers\nwith PDF URLs]

    TEXT_MSG --> TG_CACHE{Cache check\nSHA256 key}
    TG_CACHE -->|hit| TG_CACHED[Return cached answer]
    TG_CACHE -->|miss| TG_EMB[embed_query]
    TG_EMB --> TG_SEARCH[hybrid search\ntop_k chunks]
    TG_SEARCH --> TG_LLM[generate_rag_answer\ngpt-4o-mini]
    TG_LLM --> TG_STORE[Cache response]
    TG_STORE --> TG_FORMAT[Format response\nmarkdown\nAnswer section\nSources section with numbered URLs]
    TG_FORMAT --> TG_REPLY[Send reply to user]

    SEARCH_FLOW --> TG_REPLY
    TG_CACHED --> TG_REPLY
```

---

## 7. Full Phase 7 End-to-End Flow

```mermaid
flowchart TD
    subgraph CLIENTS["Clients"]
        API_CLIENT[API Client\nPOST /api/v1/ask-agentic]
        TG_CLIENT[Telegram User]
    end

    subgraph AGENTIC_SVC["AgenticRAGService.ask()"]
        INIT_STATE[Init AgentState\nmessages: HumanMessage\nretrieval_attempts: 0]
        INIT_CTX[Create Runtime Context\nall clients injected]
        GRAPH_INV[graph.ainvoke\nthread_id per user\nLangfuse callback handler]
    end

    subgraph GRAPH_EXEC["LangGraph Execution"]
        GN[guardrail] --> RN[retrieve] --> TN[tool_retrieve] --> GDN[grade_documents]
        GDN -->|pass| GAN[generate_answer]
        GDN -->|fail| RWN[rewrite_query]
        RWN --> RN
    end

    subgraph OBSERVABILITY["Langfuse Tracing"]
        TRACE_WRAP[trace_langgraph_agent\ncontext manager] --> SPANS[Spans per node\nlatency + metadata]
        SPANS --> FLUSH3[flush on completion]
        FLUSH3 --> LF_CLOUD2[Langfuse Cloud]
    end

    API_CLIENT --> INIT_STATE
    TG_CLIENT -->|text message| TG_BOT[Telegram Bot\nwraps same pipeline]
    INIT_STATE & INIT_CTX --> GRAPH_INV
    GRAPH_INV --> GRAPH_EXEC
    GRAPH_EXEC -.->|instrumented by| OBSERVABILITY
    GAN --> RESULT[Extract answer\nsources, reasoning_steps\nexecution_time, trace_id]
    RESULT --> API_CLIENT
    RESULT --> TG_BOT
```
