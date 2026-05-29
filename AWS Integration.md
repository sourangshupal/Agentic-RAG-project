# AWS Integration — Bedrock Gateway & Guardrails

Branch: `aws`  
Date: 2026-05-25

---

## Overview

Two AWS Bedrock features added on top of the existing arXiv RAG pipeline:

1. **Bedrock Gateway** — swap the LLM provider from OpenAI to any AWS Bedrock model via a single env var
2. **Bedrock Guardrails** — replace the custom LLM-based guardrail scoring with AWS Bedrock's native guardrail API

---

## Feature 1 — Bedrock Gateway

### What it does

Adds a `PROVIDER=openai|bedrock` config switch. When set to `bedrock`, the API uses AWS Bedrock for all LLM generation instead of OpenAI. The switch is transparent — all agent nodes work without modification.

### How it works

A shared `LLMClientProtocol` (Python `Protocol` / structural subtyping) defines the interface:

```python
class LLMClientProtocol(Protocol):
    def get_langchain_model(self, model: str, temperature: float) -> BaseChatModel: ...
    async def generate_rag_answer(self, query, chunks, model, **kwargs) -> dict: ...
    async def generate_rag_answer_stream(self, query, chunks, model) -> AsyncIterator[dict]: ...
    async def health_check(self) -> dict: ...
```

Both `OpenAILLMClient` (existing) and `BedrockLLMClient` (new) satisfy this protocol. At startup, `main.py` picks the right client:

```python
if settings.provider == "bedrock":
    app.state.llm_client = make_bedrock_llm_client(settings)
else:
    app.state.llm_client = make_openai_llm_client()
```

### BedrockLLMClient details

- Uses `boto3.client("bedrock-runtime")` directly
- `get_langchain_model()` returns `langchain_aws.ChatBedrock` for LangGraph nodes
- `generate_rag_answer()` calls the Bedrock `converse` API
- `generate_rag_answer_stream()` calls `converse_stream` (tokens collected in a thread, then yielded)
- Same error handling pattern as `OpenAILLMClient`

### Default model

`meta.llama3-1-70b-instruct-v1:0` — configurable via `BEDROCK__MODEL_ID`.

Any Bedrock model ID works (Claude, Nova, Titan, Llama, Mistral, etc.).

### New files

| File | Purpose |
|------|---------|
| `src/services/llm_client_protocol.py` | Shared `LLMClientProtocol` |
| `src/services/bedrock_llm/client.py` | `BedrockLLMClient` implementation |
| `src/services/bedrock_llm/factory.py` | `make_bedrock_llm_client()` factory |

### Modified files

| File | Change |
|------|--------|
| `src/config.py` | Added `BedrockSettings` class + `provider` field to `Settings` |
| `src/main.py` | Provider switch at startup |
| `src/services/agents/context.py` | `llm_client` type → `LLMClientProtocol` |
| `src/services/agents/factory.py` | Model ID picked based on provider |
| `src/dependencies.py` | `LLMDep` type → `LLMClientProtocol` |
| `src/exceptions.py` | Added `BedrockLLMException`, `BedrockConnectionError`, `BedrockTimeoutError` |
| `pyproject.toml` | Added `boto3>=1.34.0`, `langchain-aws>=0.2.0` |

### Configuration

Add to `.env`:

```dotenv
# Switch provider
PROVIDER=bedrock

# AWS credentials
BEDROCK__AWS_ACCESS_KEY_ID=your_access_key
BEDROCK__AWS_SECRET_ACCESS_KEY=your_secret_key
BEDROCK__AWS_REGION=us-east-1

# Model (any Bedrock model ID)
BEDROCK__MODEL_ID=meta.llama3-1-70b-instruct-v1:0
```

---

## Feature 2 — Bedrock Guardrails

### What it does

Replaces the existing LLM-based guardrail node (which used a prompt to score queries 0–100) with AWS Bedrock's native `ApplyGuardrail` API. Also adds a new **output guardrail node** that runs after answer generation to verify the answer is grounded in retrieved sources.

### Guardrail capabilities used

| Capability | Where applied | What it catches |
|-----------|--------------|-----------------|
| Topic denial | INPUT (query) | Queries outside CS/AI/ML scope |
| Content filters | INPUT + OUTPUT | Hate speech, violence, misconduct, sexual content |
| PII detection | INPUT + OUTPUT | Email, phone, name, address — anonymised or blocked |
| Grounding check | OUTPUT (answer) | Answers not supported by retrieved documents |

### How it works

#### BedrockGuardrailsService

Two methods:

```python
# Check the user query before RAG pipeline
result = await guardrails_service.check_input(query)
# result.allowed = True / False

# Check the generated answer against source documents
result = await guardrails_service.check_output(answer, source_doc_texts)
# result.allowed = True / False
```

Calls `bedrock-runtime.apply_guardrail()` wrapped in `asyncio.to_thread` (boto3 is sync).

#### Graceful degradation

When `BEDROCK__GUARDRAIL_ID` is empty (not configured), `check_input()` and `check_output()` both return `allowed=True` immediately (fail-open). The API works normally — guardrails are simply skipped.

#### LangGraph graph change

```
Before:
  guardrail → retrieve → grade → generate_answer → END

After:
  guardrail → retrieve → grade → generate_answer → output_guardrail → END
```

- `guardrail` node: calls `check_input()` → maps to `GuardrailScoring(score=100)` allowed or `GuardrailScoring(score=0)` blocked → same routing logic as before
- `output_guardrail` node: calls `check_output()` → if blocked, replaces answer with a safe fallback message

#### GuardrailResult state mapping

The `AgentState.guardrail_result` field still uses `GuardrailScoring` for backward compatibility. Bedrock result is mapped:
- `action=NONE` (allowed) → `score=100`
- `action=INTERVENED` (blocked) → `score=0`

The existing `continue_after_guardrail` routing (`score >= threshold`) continues to work unchanged.

### One-time AWS setup

Run once to create the guardrail resource in AWS:

```bash
uv run python scripts/create_bedrock_guardrail.py
```

This creates a guardrail with:
- Topic denial: blocks non-CS/AI/ML queries
- Content filters: HIGH threshold for hate/sexual/misconduct
- PII: ANONYMIZE mode for email/phone/name/address
- Grounding: threshold 0.7 (answer must be ≥70% grounded)

Copy the printed `guardrailId` → `BEDROCK__GUARDRAIL_ID` in `.env`.

### New files

| File | Purpose |
|------|---------|
| `src/services/bedrock_guardrails/service.py` | `BedrockGuardrailsService` + `GuardrailResult` dataclass |
| `src/services/bedrock_guardrails/factory.py` | `make_bedrock_guardrails_service()` factory |
| `src/services/agents/nodes/output_guardrail_node.py` | New `output_guardrail` LangGraph node |
| `scripts/create_bedrock_guardrail.py` | One-shot guardrail resource creation script |

### Modified files

| File | Change |
|------|--------|
| `src/services/agents/context.py` | Added `guardrails_service: Optional[BedrockGuardrailsService]` field |
| `src/services/agents/nodes/guardrail_node.py` | Replaced LLM scoring with `check_input()` call |
| `src/services/agents/agentic_rag.py` | Added `output_guardrail` node + edge, passes `guardrails_service` to Context |
| `src/services/agents/nodes/__init__.py` | Export `ainvoke_output_guardrail_step` |
| `src/main.py` | Init `BedrockGuardrailsService` at startup (always, fail-open if unconfigured) |
| `src/dependencies.py` | Added `GuardrailsDep`, `get_guardrails_service()` |
| `src/exceptions.py` | Added `BedrockGuardrailsException` |

### Configuration

Add to `.env`:

```dotenv
# Guardrail ID from scripts/create_bedrock_guardrail.py
BEDROCK__GUARDRAIL_ID=abc123xyz
BEDROCK__GUARDRAIL_VERSION=DRAFT
```

> **Note:** `PROVIDER` does not need to be `bedrock` for guardrails to work. Guardrails are always initialized and always fail-open when `BEDROCK__GUARDRAIL_ID` is empty.

---

## Complete Setup Walkthrough

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure `.env`

```dotenv
# Switch to Bedrock
PROVIDER=bedrock

# AWS credentials
BEDROCK__AWS_ACCESS_KEY_ID=AKIA...
BEDROCK__AWS_SECRET_ACCESS_KEY=...
BEDROCK__AWS_REGION=us-east-1
BEDROCK__MODEL_ID=meta.llama3-1-70b-instruct-v1:0

# Guardrails (run step 3 first)
BEDROCK__GUARDRAIL_ID=
BEDROCK__GUARDRAIL_VERSION=DRAFT
```

### 3. Create the guardrail in AWS (once)

```bash
uv run python scripts/create_bedrock_guardrail.py
# Prints: BEDROCK__GUARDRAIL_ID=abc123xyz
# Paste that into .env
```

### 4. Start the API

```bash
make start
# or: docker compose up --build -d
```

### 5. Test

```bash
# Should answer using Bedrock model
curl -X POST http://localhost:8000/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the transformer architecture?"}'

# Should be blocked by topic denial guardrail
curl -X POST http://localhost:8000/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather today?"}'
```

---

## Architecture Diagram

```
User Query
    │
    ▼
[guardrail_node]  ←── BedrockGuardrailsService.check_input()
    │                  (topic denial, content filters, PII)
    ├── out_of_scope ──► "Sorry, out of scope" message
    │
    ▼ continue
[retrieve_node]
    │
    ▼
[tool_retrieve]  (OpenSearch hybrid BM25 + vector)
    │
    ▼
[grade_documents_node]
    │
    ├── rewrite_query ──► [rewrite_query_node] ──► [retrieve_node]  (retry loop)
    │
    ▼ generate_answer
[generate_answer_node]  ←── BedrockLLMClient.get_langchain_model()
    │                         or OpenAILLMClient (depending on PROVIDER)
    ▼
[output_guardrail_node]  ←── BedrockGuardrailsService.check_output()
    │                         (content filters, grounding check)
    ▼
  END  →  Answer returned to user
```

---

## Switching Back to OpenAI

Set `PROVIDER=openai` in `.env` and restart. No other changes needed. Guardrails remain active (fail-open if no guardrail_id, or apply Bedrock guardrails if configured).
