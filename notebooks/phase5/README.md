# Phase 5: Complete RAG System with LLM Integration

## Overview

Phase 5 completes our **production-grade RAG system** by integrating OpenAI `gpt-4o-mini` with hybrid search. The system delivers fast responses (1–5 seconds), real-time streaming, and includes a Gradio web interface.

## What We Built

- **OpenAI API Integration**: `gpt-4o-mini` for answer generation (replaces local Ollama)
- **Performance**: 1–5s end-to-end (vs 120s with local Ollama)
- **Streaming API**: Real-time responses via Server-Sent Events
- **Gradio Interface**: Interactive web UI with streaming support
- **Production Ready**: Clean API design with two focused endpoints

## Architecture

<p align="center">
  <img src="../../static/phase5_rag_architecture.png" alt="Phase 5 Complete RAG System Architecture" width="900">
  <br>
  <em>Complete RAG system with LLM generation layer (OpenAI gpt-4o-mini), hybrid retrieval pipeline, and Gradio interface</em>
</p>

## Quick Start

### 1. Start Services
```bash
docker compose up --build -d
```

### 2. Test RAG Endpoint
```bash
curl -X POST "http://localhost:8000/api/v1/ask" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are transformers?", "top_k": 3, "use_hybrid": true}'
```

### 3. Launch Gradio Interface
```bash
uv run python gradio_launcher.py
# Open http://localhost:7861
```

## API Endpoints

### Standard RAG - `/api/v1/ask`
- **Purpose**: Complete response with metadata
- **Response Time**: 1–5 seconds
- **Use Case**: Batch processing, API integrations

### Streaming RAG - `/api/v1/stream`
- **Purpose**: Real-time token generation
- **Time to First Token**: 1–2 seconds
- **Use Case**: Interactive UIs, better UX

### Request Format
```json
{
    "query": "Your question",
    "top_k": 3,              // Chunks to retrieve (1-10)
    "use_hybrid": true,      // BM25 + vector search
    "model": "gpt-4o-mini",  // OpenAI model
    "categories": ["cs.AI"]  // Optional filter
}
```

## Performance

| Configuration | Response Time | Use Case |
|--------------|---------------|----------|
| `top_k=1, BM25` | ~1s | Quick answers |
| `top_k=3, Hybrid` | ~2-4s | Balanced quality |
| `top_k=5, Hybrid` | ~4-6s | Comprehensive |

**Key Optimizations**:
- Cloud LLM — no local GPU or model download
- Shared code architecture (DRY principles)
- 300-word response limit for focused answers
- Automatic source deduplication

## Configuration

```bash
# .env file
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o-mini
JINA_API_KEY=jina_...   # For embeddings
```

## Testing

### Run the Notebook
```bash
jupyter notebook notebooks/phase5/phase5_complete_rag_system.ipynb
```

### Test Streaming
```bash
curl -X POST "http://localhost:8000/api/v1/stream" \
  -H "Content-Type: application/json" \
  -d '{"query": "Explain attention mechanism", "top_k": 2}' \
  --no-buffer
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 404 on `/stream` | Rebuild API: `docker compose build api && docker compose restart api` |
| Slow responses | Reduce `top_k` or check OpenAI API key |
| No Gradio | Port changed to 7861: `http://localhost:7861` |
| LLM errors | Check `OPENAI_API_KEY` in `.env`; verify at https://platform.openai.com/usage |

## Project Structure

```
src/
├── routers/
│   └── ask.py                  # RAG endpoints
├── services/
│   └── openai_llm/
│       ├── client.py           # OpenAI LLM client
│       └── factory.py          # Factory function
├── gradio_app.py               # Web interface
└── gradio_launcher.py          # Launcher script

notebooks/phase5/
├── README.md               # This file
└── phase5_complete_rag_system.ipynb
```

## Next Steps

- **Enhance**: Add conversation memory, feedback loops
- **Optimize**: Implement caching, model fine-tuning
- **Deploy**: Add authentication, monitoring, load balancing

## Resources

- [Notebook Tutorial](./phase5_complete_rag_system.ipynb)
- [API Documentation](http://localhost:8000/docs)
- [Gradio Interface](http://localhost:7861)
- [OpenAI Models](https://platform.openai.com/docs/models)
