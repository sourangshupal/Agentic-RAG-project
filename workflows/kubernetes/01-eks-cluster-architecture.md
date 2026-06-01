# 01 — EKS Cluster Architecture

This diagram shows the managed EKS control plane and the two worker nodes that actually run our pods.

```mermaid
flowchart TB
    subgraph AWS["AWS Cloud (us-east-1)"]
        subgraph CP["EKS Control Plane (managed by AWS)"]
            API_S["API Server"]
            SCH["Scheduler"]
            CM["Controller Manager"]
            ETCD[(etcd cluster)]
        end

        subgraph VPC["VPC + Subnets"]
            subgraph NODE1["Worker Node 1<br/>m5.xlarge<br/>4 vCPU / 16 GB"]
                K1[kubelet]
                K1P["rag-api pod"]
                K1O["OpenSearch pod"]
                K1A["Alloy pod<br/>(DaemonSet)"]
            end

            subgraph NODE2["Worker Node 2<br/>m5.xlarge<br/>4 vCPU / 16 GB"]
                K2[kubelet]
                K2P["rag-api pod"]
                K2A["airflow pod"]
                K2D["dashboards pod"]
                K2Al["Alloy pod<br/>(DaemonSet)"]
            end
        end

        subgraph MGMT["Management Services"]
            ECR[(Amazon ECR<br/>agentic-rag/api:latest)]
            ELB1["AWS ELB<br/>rag-api (:80)"]
            ELB2["AWS ELB<br/>airflow (:8080)"]
            ELB3["AWS ELB<br/>dashboards (:5601)"]
        end
    end

    DEV["Developer<br/>agentops branch"] -->|git push| CP
    CP -->|schedules pods| SCH
    SCH -->|assigns to Node 1| NODE1
    SCH -->|assigns to Node 2| NODE2
    ECR -->|image pull| K1P
    ECR -->|image pull| K2P
    ELB1 -->|external traffic| K1P
    ELB1 -->|external traffic| K2P
    ELB2 -->|external traffic| K2A
    ELB3 -->|external traffic| K2D
```

## Key Concepts for Students

| Component | What It Does |
|---|---|
| **Control Plane** | Managed by AWS — you do not maintain the API server or etcd. You only interact via `kubectl`. |
| **Worker Node** | An EC2 instance (m5.xlarge) that runs kubelet and your containers. We have 2 of them. |
| **kubelet** | The agent on each node that talks to the control plane and starts/stops containers. |
| **Scheduler** | Decides which node a new pod should land on based on CPU, memory, and anti-affinity rules. |
| **ECR** | Docker image registry. Images built in GitHub Actions are pushed here, then pulled by nodes. |
| **ELB** | AWS Load Balancer created automatically when you apply a `LoadBalancer` service in Kubernetes. |

## Why m5.xlarge?

We chose `m5.xlarge` (4 vCPU, 16 GB) over `t3.medium` (2 vCPU, 4 GB) because:
- Each `rag-api` pod requests **6 GB memory** at baseline
- A single OpenSearch pod needs **~3 GB**
- `t3.medium` (4 GB total) cannot even fit one `rag-api` pod
- `m5.xlarge` fits ~2 `rag-api` pods + OpenSearch + system overhead per node
