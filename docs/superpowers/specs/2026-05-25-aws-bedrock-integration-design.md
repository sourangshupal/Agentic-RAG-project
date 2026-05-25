# AWS Bedrock Integration — Design Spec

**Date:** 2026-05-25  
**Branch:** `aws`  
**Status:** Implemented

---

## Problem

The arXiv RAG system was coupled exclusively to OpenAI for LLM inference and used a homegrown LLM-based guardrail (scoring queries 0-100 via a prompt). Both choices had limitations:

- **OpenAI lock-in**: No way to swap models without code changes
- **LLM guardrails**: Extra LLM call per query, scoring variability, no native grounding check

---

## Solution

Two AWS Bedrock features on a new `aws` branch:

1. **Bedrock Gateway** — config-switchable LLM provider (`PROVIDER=openai|bedrock`)
2. **Bedrock Guardrails** — replace LLM scoring with native `ApplyGuardrail` API

---

## Architecture

### Provider switch

```
PROVIDER=openai  →  OpenAILLMClient   (existing)
PROVIDER=bedrock →  BedrockLLMClient  (new)
```

Both satisfy `LLMClientProtocol` (Python structural subtyping via `Protocol`). Agent nodes call `runtime.context.llm_client.get_langchain_model()` — zero node changes needed.

### Graph change

```
Before: guardrail → retrieve → grade → generate_answer → END
After:  guardrail → retrieve → grade → generate_answer → output_guardrail → END
```

- `guardrail` node now calls `BedrockGuardrailsService.check_input()` (INPUT side: topic denial, content filters, PII)
- `output_guardrail` node calls `BedrockGuardrailsService.check_output()` (OUTPUT side: content filters, grounding)

---

## New Files

| Path | Purpose |
|------|---------|
| `src/services/llm_client_protocol.py` | Shared `LLMClientProtocol` Protocol |
| `src/services/bedrock_llm/client.py` | `BedrockLLMClient` using boto3 `converse` API |
| `src/services/bedrock_llm/factory.py` | `make_bedrock_llm_client()` |
| `src/services/bedrock_guardrails/service.py` | `BedrockGuardrailsService` wrapping `apply_guardrail` |
| `src/services/bedrock_guardrails/factory.py` | `make_bedrock_guardrails_service()` |
| `src/services/agents/nodes/output_guardrail_node.py` | New `output_guardrail` LangGraph node |
| `scripts/create_bedrock_guardrail.py` | One-shot AWS guardrail resource creation script |

---

## Configuration

```dotenv
# Provider switch
PROVIDER=openai   # or: bedrock

# Bedrock credentials (used when PROVIDER=bedrock)
BEDROCK__AWS_ACCESS_KEY_ID=
BEDROCK__AWS_SECRET_ACCESS_KEY=
BEDROCK__AWS_REGION=us-east-1
BEDROCK__MODEL_ID=meta.llama3-1-70b-instruct-v1:0

# Guardrails (optional — fail-open when empty)
BEDROCK__GUARDRAIL_ID=
BEDROCK__GUARDRAIL_VERSION=DRAFT
```

---

## Bedrock Guardrails Features

The guardrail resource (created via `scripts/create_bedrock_guardrail.py`) configures:

| Feature | Config | Applies to |
|---------|--------|-----------|
| Topic denial | Deny non-CS/AI/ML queries | INPUT |
| Content filters | HIGH: hate/sexual/misconduct, MEDIUM: insults/violence | INPUT + OUTPUT |
| PII detection | ANONYMIZE: email/phone/name/address | INPUT + OUTPUT |
| Grounding check | Threshold ≥0.7 | OUTPUT |

---

## Graceful Degradation

- **`BEDROCK__GUARDRAIL_ID` empty** → `BedrockGuardrailsService` returns `allowed=True` (fail-open)
- **`PROVIDER=openai`** → `OpenAILLMClient` used; `BedrockGuardrailsService` initialized but guardrails pass-through
- **Bedrock API unreachable** → exception caught, fail-open with log warning

---

## Setup Steps

1. Set credentials in `.env`
2. Run `uv run python scripts/create_bedrock_guardrail.py` once
3. Copy printed `guardrailId` → `BEDROCK__GUARDRAIL_ID` in `.env`
4. Set `PROVIDER=bedrock`
5. Restart the API

---

## Testing

```bash
# Unit tests (mock boto3)
uv run pytest tests/unit/ -q

# Smoke test with OpenAI (default)
PROVIDER=openai uv run python -c "from src.services.openai_llm.client import OpenAILLMClient; print('OK')"

# Smoke test Bedrock client import
uv run python -c "from src.services.bedrock_llm.client import BedrockLLMClient; print('OK')"

# Integration test
curl -X POST http://localhost:8000/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is transformer architecture?"}'

# Guardrail test (should return out_of_scope)
curl -X POST http://localhost:8000/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the weather today?"}'
```
