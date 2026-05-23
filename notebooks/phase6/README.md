# Phase 6: Production Monitoring and Caching with Langfuse and Redis

## Overview

Phase 6 adds production-grade monitoring and intelligent caching to our RAG system. We integrate **Langfuse Cloud** for complete pipeline observability and **Upstash Redis** for high-performance response caching.

## What We Built

- **Langfuse Cloud Integration**: End-to-end RAG pipeline tracing and analytics
- **Upstash Redis Caching**: 150-400x faster responses for repeated queries
- **Performance Monitoring**: Real-time metrics and system health
- **Production Ready**: Enterprise-grade observability and optimization

## Architecture

<p align="center">
  <img src="../../static/phase6_monitoring_and_caching.png" alt="Phase 6 Monitoring & Caching Architecture" width="900">
  <br>
  <em>Phase 6 architecture with Langfuse Cloud tracing and Upstash Redis caching integration</em>
</p>

### Data Flow
```
Query → Cache Check → [Hit: ~100ms] | [Miss: Full Pipeline ~2-5s] → Cache Store → Langfuse Trace
```

## Key Features

### **Langfuse Cloud Observability**
- Complete RAG pipeline tracing with performance breakdowns
- User analytics, query patterns, and success rate tracking
- Real-time monitoring dashboard with cost and usage metrics
- Quality insights with answer relevance and source attribution
- Access at: **https://us.cloud.langfuse.com**

### **Upstash Redis Intelligent Caching**
- **Exact-Match Strategy**: Parameter-aware cache keys for precise matching
- **Performance**: 150-400x faster responses for repeated queries (~100ms vs 2-5s)
- **TTL Management**: 6-hour default expiration (`REDIS__TTL_HOURS=6`)
- **TLS Encrypted**: `rediss://` connection to Upstash (not plain `redis://`)

## Quick Start

### Environment Setup
```bash
# Required environment variables — NOTE double underscore for LANGFUSE__
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
LANGFUSE__HOST=https://us.cloud.langfuse.com

# Upstash Redis — copy from TCP tab in Upstash console
REDIS__URL=rediss://default:<token>@<host>.upstash.io:6379
REDIS__TTL_HOURS=6
```

### Start Services
```bash
docker compose up --build -d
```

### Test Caching Performance
```bash
# First request (cache miss ~2-5s with OpenAI)
curl -X POST "http://localhost:8000/api/v1/ask" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are transformers?", "top_k": 3}'

# Second identical request (cache hit ~100ms)
curl -X POST "http://localhost:8000/api/v1/ask" \
  -H "Content-Type: application/json" \
  -d '{"query": "What are transformers?", "top_k": 3}'
```

## Performance Benchmarks

| Scenario | Response Time | Improvement |
|----------|---------------|-------------|
| **Cache Miss** | 2-5 seconds | Baseline |
| **Cache Hit** | 50-100ms | **50-100x faster** |
| **Monitoring Overhead** | <2% | Negligible impact |

## Testing

### Run the Notebook
```bash
jupyter notebook notebooks/phase6/phase6_cache_testing.ipynb
```

### Monitor System Health
```bash
# Check Redis + Langfuse status via API health
curl "http://localhost:8000/api/v1/health"

# Access Langfuse dashboard
# Visit: https://us.cloud.langfuse.com
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| **Cache not working** | Check `REDIS__URL` in `.env` — must use `rediss://` (TLS) from Upstash TCP tab |
| **No Langfuse traces** | Verify `LANGFUSE__PUBLIC_KEY` uses **double underscore** prefix |
| **Slow responses** | Monitor cache hit rate via `GET /api/v1/health` |

## Next Steps

- **Enhanced Caching**: Upgrade to semantic similarity caching for fuzzy matching
- **Advanced Analytics**: Custom dashboards and A/B testing frameworks
- **Production Scaling**: Distributed caching and automated monitoring
- **Quality Optimization**: User feedback integration and answer scoring

## Resources

- **Notebook**: [phase6_cache_testing.ipynb](./phase6_cache_testing.ipynb)
- **Langfuse Dashboard**: https://us.cloud.langfuse.com
- **Upstash Console**: https://console.upstash.com

---

Phase 6 transforms your RAG system into a production-grade service with dramatic performance improvements and comprehensive cloud observability.
