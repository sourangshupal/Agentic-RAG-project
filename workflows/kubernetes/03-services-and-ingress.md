# 03 — Services & Ingress

This diagram shows how external traffic from the internet reaches our pods. Some services are exposed via AWS ELB (`LoadBalancer` type) and some are internal-only (`ClusterIP` type).

```mermaid
flowchart LR
    subgraph INTERNET["Internet"]
        USER["Student / API Client"]
        ADMIN["Admin (you)"]
    end

    subgraph AWS["AWS us-east-1"]
        subgraph ELBS["Load Balancers (AWS ELB)"]
            ELB_API["rag-api LB<br/>ae1898...elb.amazonaws.com<br/>port 80"]
            ELB_AF["airflow LB<br/>ab56be...elb.amazonaws.com<br/>port 8080"]
            ELB_DB["dashboards LB<br/>a0b0c5...elb.amazonaws.com<br/>port 5601"]
        end

        subgraph SVC["Kubernetes Services"]
            S_API["rag-api Service<br/>Type: LoadBalancer<br/>port: 80 → target: 8000"]
            S_AF["airflow Service<br/>Type: LoadBalancer<br/>port: 8080 → target: 8080"]
            S_DB["dashboards Service<br/>Type: LoadBalancer<br/>port: 5601 → target: 5601"]
            S_OS["opensearch Service<br/>Type: ClusterIP<br/>port: 9200"]
            S_OSH["opensearch-headless<br/>Type: ClusterIP<br/>port: 9200 / 9300"]
        end

        subgraph PODS["Target Pods"]
            P_API["rag-api pods<br/>port: 8000"]
            P_AF["airflow pod<br/>port: 8080"]
            P_DB["dashboards pod<br/>port: 5601"]
            P_OS["opensearch-0<br/>port: 9200"]
        end
    end

    USER -->|GET /api/v1/health| ELB_API
    USER -->|POST /api/v1/ask-agentic| ELB_API
    ADMIN -->|Airflow UI| ELB_AF
    ADMIN -->|OpenSearch Dashboards| ELB_DB

    ELB_API --> S_API
    ELB_AF --> S_AF
    ELB_DB --> S_DB

    S_API -->|round-robin| P_API
    S_AF -->|single target| P_AF
    S_DB -->|single target| P_DB
    S_OS -->|single target| P_OS
    S_OSH -->|StatefulSet peer| P_OS

    P_API -->|internal| S_OS
    P_AF -->|internal| S_OS
```

## Service Types Explained

| Type | External IP | Use Case | Our Services |
|---|---|---|---|
| **LoadBalancer** | Yes — AWS creates an ELB | User-facing endpoints | rag-api, airflow, dashboards |
| **ClusterIP** | No — internal only | Pod-to-pod communication | opensearch, opensearch-headless |

## Why opensearch-headless?

OpenSearch is a **StatefulSet** (not a Deployment). It needs a stable network identity so that:
- Each pod keeps the same hostname after restart
- Peer discovery inside the cluster works via DNS
- Data stored on the persistent volume is re-attached to the same pod

The `opensearch-headless` service is `ClusterIP` with `clusterIP: None` — this creates a DNS record for every pod individually (`opensearch-0.opensearch-headless.production.svc.cluster.local`), which is required for StatefulSet peer discovery.

## Round-Robin Load Balancing

The `rag-api` Service is a `LoadBalancer` with **multiple pods** behind it. Kubernetes Services use `iptables` or `IPVS` to distribute traffic evenly across all ready pods. When HPA scales from 2 → 6 replicas, the Service automatically starts sending traffic to the new pods without any manual config change.
