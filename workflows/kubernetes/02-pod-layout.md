# 02 — Pod Layout in the Production Namespace

This diagram shows every pod that runs inside the `production` namespace, its container image, and its resource request / limit boxes. Notice that only `rag-api` is managed by HPA (can grow from 2 to 6 replicas).

```mermaid
flowchart TB
    subgraph NS["Namespace: production"]
        subgraph HPA["rag-api (Deployment + HPA)"]
            P1["rag-api-xxx-hq8lq<br/>image: agentic-rag/api:latest<br/>req: 500m CPU / 6Gi RAM<br/>lim: 2000m CPU / 8Gi RAM"]
            P2["rag-api-xxx-k7jkq<br/>image: agentic-rag/api:latest<br/>req: 500m CPU / 6Gi RAM<br/>lim: 2000m CPU / 8Gi RAM"]
            P3["rag-api-xxx-pd7sw<br/>image: agentic-rag/api:latest<br/>req: 500m CPU / 6Gi RAM<br/>lim: 2000m CPU / 8Gi RAM"]
            P4["... up to 6 replicas"]
        end

        subgraph AF["airflow (Deployment)"]
            A1["airflow-xxx-5zb7h<br/>image: agentic-rag/airflow:latest<br/>req: 250m CPU / 1Gi RAM<br/>lim: 1000m CPU / 2Gi RAM"]
        end

        subgraph OS["opensearch (StatefulSet)"]
            O1["opensearch-0<br/>image: opensearchproject/opensearch:2.19.1<br/>req: 500m CPU / 2Gi RAM<br/>lim: 1000m CPU / 4Gi RAM"]
        end

        subgraph DB["opensearch-dashboards (Deployment)"]
            D1["dashboards-xxx-j6q2l<br/>image: opensearchproject/opensearch-dashboards:2.19.1<br/>req: 100m CPU / 512Mi RAM<br/>lim: 500m CPU / 1Gi RAM"]
        end

        subgraph INIT["Init Container (rag-api only)"]
            I1["wait-for-opensearch<br/>sleeps until OpenSearch:9200 is ready<br/>ensures dependency order"]
        end
    end

    P1 --> I1
    P2 --> I1
    P3 --> I1
    I1 -.->|ready| O1
```

## Resource Math for Students

| Pod | Request CPU | Request RAM | Limit CPU | Limit RAM |
|---|---|---|---|---|
| rag-api (×2 min) | 500m | **6 Gi** | 2000m | **8 Gi** |
| airflow | 250m | 1 Gi | 1000m | 2 Gi |
| opensearch | 500m | 2 Gi | 1000m | 4 Gi |
| dashboards | 100m | 512 Mi | 500m | 1 Gi |
| **Total minimum** | **1350m** | **~9.5 Gi** | — | — |

## Why the rag-api Pod Is Special

1. **It has an init container** (`wait-for-opensearch`) that delays startup until OpenSearch is healthy. This prevents connection errors on first boot.
2. **It is the only HPA-managed pod** — it can scale from 2 to 6 replicas under load.
3. **It has the highest resource footprint** because it loads PyTorch, LangGraph, and boto3 into memory at startup (~2.7 GB baseline).

## Why We Hit a Ceiling

With **6 Gi RAM request** per `rag-api` pod and **16 Gi total** per node:
- Node 1: 6 + 2 (OpenSearch) + system = ~9 GB used → ~7 GB free
- Node 2: 6 + 1 (airflow) + 0.5 (dashboards) + system = ~8 GB used → ~8 GB free

A **3rd rag-api pod needs 6 Gi free**, but neither node has that much contiguous free memory. This is why HPA gets stuck at 2 replicas unless we lower the request.
