# Kubernetes Architecture Diagrams

This folder contains Mermaid diagrams that document the entire AWS EKS deployment built for the arXiv Paper Curator system. Each diagram focuses on one layer so students can understand how Docker containers move from a laptop into production-grade Kubernetes.

---

## Diagram Index

| # | Diagram | What It Shows |
|---|---|---|
| 01 | [EKS Cluster Architecture](01-eks-cluster-architecture.md) | Managed control plane + 2 worker nodes (m5.xlarge) in VPC |
| 02 | [Pod Layout](02-pod-layout.md) | Every pod running in the `production` namespace with CPU / memory boxes |
| 03 | [Services & Ingress](03-services-and-ingress.md) | LoadBalancer vs ClusterIP services and how external traffic enters |
| 04 | [HPA Scaling](04-hpa-scaling.md) | How Horizontal Pod Autoscaler reacts to load and scales 2 → 6 replicas |
| 05 | [CI/CD Pipeline](05-cicd-pipeline.md) | GitHub Actions → ECR → kubectl apply → rolling update on EKS |
| 06 | [Monitoring Stack](06-monitoring.md) | Grafana Cloud receiving metrics from Alloy, node-exporter, kube-state-metrics |
| 07 | [Request Flow](07-request-flow.md) | A single user query's journey through ELB → Service → Pod → Bedrock |

---

## How to Read These Diagrams

All diagrams are written in [Mermaid](https://mermaid.js.org/) syntax. If you open any `.md` file on GitHub, the diagram renders automatically. If you are reading locally, you can paste the code block into the [Mermaid Live Editor](https://mermaid.live/).

**Key conventions used across diagrams:**
- `subgraph` = a logical boundary (namespace, node, or service group)
- `([ ])` = start / end nodes
- `{ }` = decision points (if / else)
- Dashed arrows `-.->` = optional or background paths
