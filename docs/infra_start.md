# Complete Infrastructure Startup Guide

> This guide explains **every step** required to deploy the Agentic RAG system on AWS EKS from scratch, including why each resource is created, what commands to run, and how to verify success.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Step 1: Create the EKS Cluster](#step-1-create-the-eks-cluster)
4. [Step 2: Create ECR Repositories](#step-2-create-ecr-repositories)
5. [Step 3: Build and Push Docker Images](#step-3-build-and-push-docker-images)
6. [Step 4: Configure Kubernetes](#step-4-configure-kubernetes)
7. [Step 5: Deploy Applications](#step-5-deploy-applications)
8. [Step 6: Verify Deployment](#step-6-verify-deployment)
9. [Step 7: (Optional) Setup Grafana Cloud Monitoring](#step-7-optional-setup-grafana-cloud-monitoring)
10. [Step 8: Test the End-to-End Pipeline](#step-8-test-the-end-to-end-pipeline)
11. [Troubleshooting](#troubleshooting)
12. [Variable Management (No Secrets in Git)](#variable-management-no-secrets-in-git)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS EKS Cluster                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────┐ │
│  │   API Pod       │  │  Airflow Pod    │  │ OpenSearch Pods  │ │
│  │   (rag-api)     │  │  (airflow)      │  │ (opensearch)     │ │
│  │   FastAPI +     │  │  Scheduler +    │  │ BM25 + Vector    │ │
│  │   LangGraph     │  │  Webserver      │  │ Search Engine    │ │
│  └────────┬────────┘  └────────┬────────┘  └────────┬─────────┘ │
│           │                    │                    │           │
│  ┌────────┴────────────────────┴────────────────────┴─────────┐ │
│  │              Kubernetes Services (LoadBalancer)              │ │
│  │  Creates AWS Classic ELBs for external access               │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     External Cloud Services                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ Neon Postgres│ │ Upstash Redis│ │ Langfuse Cloud           │ │
│  │ (Paper DB)   │ │ (Query Cache)│ │ (Tracing & Observability)│ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │ OpenAI API   │ │ Jina AI      │ │ Grafana Cloud            │ │
│  │ (LLM)        │ │ (Embeddings) │ │ (K8s Monitoring)         │ │
│  └──────────────┘ └──────────────┘ └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Why EKS?** Kubernetes provides container orchestration, self-healing, rolling updates, and horizontal scaling. EKS is the managed Kubernetes service on AWS — it handles the control plane so you don't have to.

**Why separate pods?** Each service (API, Airflow, OpenSearch) has different resource needs, scaling patterns, and failure domains. Running them in separate pods allows independent scaling and rolling restarts.

---

## Prerequisites

### Tools

| Tool | Version | Purpose | Install |
|---|---|---|---|
| `aws` CLI | v2+ | AWS API access | `brew install awscli` |
| `eksctl` | v0.190+ | EKS cluster management | `brew install eksctl` |
| `kubectl` | v1.29+ | Kubernetes control | `brew install kubectl` |
| `docker` | v24+ | Image building | Docker Desktop |
| `helm` | v3.14+ | Helm chart deployment | `brew install helm` |
| `gh` | v2.40+ | GitHub CLI (for secrets) | `brew install gh` |

### AWS Configuration

```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, and default region (us-east-1)
```

Verify:
```bash
aws sts get-caller-identity
```

### Environment File

Create `.env` in the repo root. This file is **git-ignored** and stores sensitive configuration:

```bash
# AWS
CLUSTER_NAME=agentic-rag-cluster
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# Application secrets (same as your .env file)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
POSTGRES_DATABASE_URL=postgresql+psycopg2://...
REDIS__URL=rediss://...
REDIS__TTL_HOURS=6
LANGFUSE__HOST=https://cloud.langfuse.com
LANGFUSE__PUBLIC_KEY=pk-lf-...
LANGFUSE__SECRET_KEY=sk-lf-...
OPENSEARCH__HOST=http://opensearch:9200
JINA_API_KEY=...
```

> **Why `.env`?** It keeps secrets out of GitHub. The `.gitignore` already excludes `.env`. The `infra_start.sh` script sources this file automatically.

---

## Step 1: Create the EKS Cluster

**Why:** The EKS cluster is the foundation. It provides the Kubernetes control plane (API server, scheduler, etcd) and we attach a managed node group for running our containers.

**Command:**

```bash
eksctl create cluster \
    --name agentic-rag-cluster \
    --region us-east-1 \
    --node-type t3.medium \
    --nodes 2 \
    --managed \
    --with-oidc \
    --ssh-access \
    --ssh-public-key ~/.ssh/id_rsa.pub
```

**What this creates:**
- EKS control plane (managed by AWS)
- VPC with 2 public + 2 private subnets across 2 AZs
- Internet gateway + NAT gateway
- 2 EC2 `t3.medium` instances in an Auto Scaling Group
- IAM roles for cluster and node group
- Security groups for cluster and node communication

**Time:** 15–20 minutes.

**Verify:**
```bash
eksctl get cluster --region us-east-1
kubectl get nodes -o wide
```

---

## Step 2: Create ECR Repositories

**Why:** Amazon ECR (Elastic Container Registry) stores Docker images. We need one repository per service (API and Airflow) so Kubernetes can pull images when creating pods.

**Command:**

```bash
aws ecr create-repository --repository-name agentic-rag/api     --region us-east-1
aws ecr create-repository --repository-name agentic-rag/airflow --region us-east-1
```

**What this creates:**
- Two private Docker repositories in ECR
- IAM permissions for pushing/pulling images

**Verify:**
```bash
aws ecr describe-repositories --region us-east-1
```

---

## Step 3: Build and Push Docker Images

**Why:** Our application code (FastAPI + Airflow DAGs) must be packaged into Docker images and pushed to ECR so the EKS cluster can pull and run them.

### 3a. Login to ECR

```bash
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com
```

### 3b. Build and Push API Image

```bash
docker build -t agentic-rag/api:latest .
docker tag agentic-rag/api:latest \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/agentic-rag/api:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/agentic-rag/api:latest
```

**What the API image contains:**
- FastAPI application (`src/`)
- All Python dependencies (uv + requirements)
- Health check endpoints at `/api/v1/health`

### 3c. Build and Push Airflow Image

```bash
docker build -f airflow/Dockerfile -t agentic-rag/airflow:latest .
docker tag agentic-rag/airflow:latest \
    ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/agentic-rag/airflow:latest
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/agentic-rag/airflow:latest
```

**What the Airflow image contains:**
- Apache Airflow 2.10.3 with PostgreSQL backend
- Docling + PyTorch for PDF parsing
- DAG files from `airflow/dags/`
- Source code from `src/` (baked into image for K8s)

**Verify:**
```bash
aws ecr describe-images --repository-name agentic-rag/api     --region us-east-1
aws ecr describe-images --repository-name agentic-rag/airflow --region us-east-1
```

---

## Step 4: Configure Kubernetes

**Why:** Before deploying applications, we need to set up the Kubernetes environment: namespace, secrets, and ConfigMaps.

### 4a. Create Namespace

```bash
kubectl create namespace production
```

**Why a separate namespace?** It isolates project resources from other workloads, allows role-based access control, and makes cleanup easy (delete the namespace = delete everything).

### 4b. Create Secrets from .env

```bash
kubectl create secret generic rag-app-secrets \
    --from-env-file=.env \
    --namespace=production
```

**Why a Secret?** Environment variables like `OPENAI_API_KEY`, `POSTGRES_DATABASE_URL`, and `LANGFUSE__SECRET_KEY` are sensitive. Kubernetes Secrets encrypts them at rest and only injects them into the pods that need them.

### 4c. Create Airflow DAGs ConfigMap

```bash
kubectl create configmap airflow-dags \
    --from-file=airflow/dags/ \
    --namespace=production
```

**Why a ConfigMap?** In Docker Compose, DAGs are bind-mounted from the host. In Kubernetes, bind mounts from the host don't work because nodes don't share the same filesystem. A ConfigMap stores the DAG files as Kubernetes-native objects and mounts them into the Airflow pod.

**Verify:**
```bash
kubectl get namespace production
kubectl get secret rag-app-secrets -n production
kubectl get configmap airflow-dags -n production
```

---

## Step 5: Deploy Applications

**Why:** Now we apply the Kubernetes deployment manifests that define how our containers should run: resource limits, health checks, replica counts, and service exposure.

### 5a. Deploy OpenSearch

```bash
kubectl apply -f deployment/k8s/opensearch/ -n production
```

**What this deploys:**
- OpenSearch cluster (single-node for simplicity)
- OpenSearch Dashboards for visualizing index data
- Persistent volume claim for index data (survives pod restarts)

### 5b. Deploy API

```bash
# Replace the image placeholder with actual ECR URI
sed -i.bak "s|REPLACE_WITH_ECR_URI|${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com|g" \
    deployment/k8s/api/deployment.yaml

kubectl apply -f deployment/k8s/api/deployment.yaml -n production
kubectl apply -f deployment/k8s/api/service.yaml -n production
```

**What this deploys:**
- FastAPI container with 1Gi request / 4Gi memory limit
- LoadBalancer service (creates AWS Classic ELB)
- Readiness and liveness probes on `/api/v1/health`

### 5c. Deploy Airflow

```bash
# Replace the image placeholder with actual ECR URI
sed -i.bak "s|REPLACE_WITH_ECR_URI|${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com|g" \
    deployment/k8s/airflow/deployment.yaml

kubectl apply -f deployment/k8s/airflow/deployment.yaml -n production
kubectl apply -f deployment/k8s/airflow/service.yaml -n production
```

**What this deploys:**
- Airflow webserver + scheduler in a single pod
- Init container that waits for OpenSearch to be ready
- LoadBalancer service (creates AWS Classic ELB)
- 2Gi request / 5Gi memory limit (Docling + PyTorch need ~3.5GB peak)

**Verify all pods are running:**
```bash
kubectl get pods -n production -o wide
kubectl get services -n production
```

---

## Step 6: Verify Deployment

### 6a. Check Pod Health

```bash
kubectl get pods -n production
```

Expected:
```
NAME                           READY   STATUS    RESTARTS   AGE
rag-api-xxx                    1/1     Running   0          5m
airflow-xxx                    1/1     Running   0          5m
opensearch-xxx                 1/1     Running   0          5m
opensearch-dashboards-xxx      1/1     Running   0          5m
```

### 6b. Get API Endpoint

```bash
kubectl get service rag-api -n production -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'
```

This outputs the AWS ELB DNS name, e.g.:
`a21196a2cc1434634843479124b75beb-1768070890.us-east-1.elb.amazonaws.com`

### 6c. Test API Health

```bash
export API_URL=$(kubectl get service rag-api -n production -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
curl -s http://${API_URL}/api/v1/health | python3 -m json.tool
```

Expected response:
```json
{
    "status": "ok",
    "services": {
        "database": {"status": "healthy"},
        "opensearch": {"status": "healthy"},
        "openai": {"status": "healthy"}
    }
}
```

---

## Step 7: (Optional) Setup Grafana Cloud Monitoring

**Why:** Grafana Cloud Kubernetes Monitoring collects metrics (CPU, memory, pod status) and logs from your EKS cluster and sends them to Grafana Cloud for visualization.

**Prerequisites:**
1. Sign up at https://grafana.com (free forever tier available)
2. Create a Kubernetes Monitoring Access Policy token with `metrics:write` and `logs:write` scopes

**Commands:**

```bash
# Add Grafana Helm repo
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Create the monitoring namespace
kubectl create namespace monitoring

# Deploy the monitoring stack (replace PROM_URL, LOKI_URL, and TOKEN)
helm upgrade --install grafana-k8s-monitoring grafana/k8s-monitoring \
    --namespace monitoring \
    --set cluster.name="${CLUSTER_NAME}" \
    --set global.scrape_interval="60s" \
    --set prometheus.remote_write[0].url="${PROMETHEUS_REMOTE_WRITE_URL}" \
    --set prometheus.remote_write[0].auth.username="${PROMETHEUS_USER}" \
    --set prometheus.remote_write[0].auth.password="${GRAFANA_TOKEN}" \
    --set loki.host="${LOKI_URL}" \
    --set loki.basicAuth.username="${LOKI_USER}" \
    --set loki.basicAuth.password="${GRAFANA_TOKEN}"
```

**What this deploys:**
- Grafana Alloy (metrics and logs collector)
- kube-state-metrics (Kubernetes object metrics)
- node-exporter (node-level hardware metrics)
- OpenCost (cost visibility)
- Kepler (energy consumption)

**Verify:**
```bash
kubectl get pods -n monitoring
helm list -n monitoring
```

> **Full Grafana setup guide:** See `docs/grafana_integration.md` for the complete values.yaml and verification steps.

---

## Step 8: Test the End-to-End Pipeline

### 8a. Trigger Airflow DAG

```bash
AIRFLOW_POD=$(kubectl get pods -n production -l app=airflow -o jsonpath='{.items[0].metadata.name}')
kubectl exec "$AIRFLOW_POD" -n production -- airflow dags trigger arxiv_paper_ingestion
```

**What happens:**
- Airflow fetches 2 papers from arXiv API
- Downloads their PDFs
- Parses with Docling
- Stores metadata in Neon PostgreSQL
- Chunks and indexes into OpenSearch

### 8b. Monitor the DAG Run

```bash
kubectl logs -n production "$AIRFLOW_POD" -f --tail=50
```

Watch for:
- `papers_fetched: 2`
- `pdfs_downloaded: 2`
- `pdfs_parsed: 2`
- `papers_stored: 2`

### 8c. Test the API with Real Data

```bash
export API_URL=$(kubectl get service rag-api -n production -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

# Basic RAG query
curl -s -X POST "http://${API_URL}/api/v1/ask" \
    -H 'Content-Type: application/json' \
    -d '{"query": "What are transformer architectures used for?", "search_mode": "hybrid"}'

# Agentic RAG query
curl -s -X POST "http://${API_URL}/api/v1/ask-agentic" \
    -H 'Content-Type: application/json' \
    -d '{"query": "Explain self-attention mechanism in transformers"}'
```

---

## Troubleshooting

### Pod stuck in `Pending`
```bash
kubectl describe pod <pod-name> -n production
# Check: Insufficient CPU/memory? ImagePullBackOff? Node not ready?
```

### `ImagePullBackOff`
The pod can't pull the Docker image. Check:
1. ECR login: `aws ecr get-login-password | docker login ...`
2. Image tag in deployment.yaml matches the pushed tag
3. IAM permissions for the EKS node group to pull from ECR

### Airflow pod `OOMKilled`
The Airflow memory limit is too low. The `deployment/k8s/airflow/deployment.yaml` should have:
```yaml
limits:
  memory: "5Gi"
```

### API pod `OOMKilled`
The API memory limit is too low. The `deployment/k8s/api/deployment.yaml` should have:
```yaml
limits:
  memory: "4Gi"
```

### OpenSearch not reachable
Check the init container logs:
```bash
kubectl logs -n production <airflow-pod> -c wait-for-opensearch
```

---

## Variable Management (No Secrets in Git)

**The golden rule:** Never commit secrets, AWS account IDs, or API keys to GitHub.

### Strategy 1: `.env` File (Local Development)

Create `.env` in the repo root (already git-ignored):

```bash
CLUSTER_NAME=agentic-rag-cluster
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012
OPENAI_API_KEY=sk-...
# ... all other secrets
```

Both `infra_start.sh` and `tear_down.sh` automatically source `.env` if it exists.

### Strategy 2: Environment Variables (CI/CD)

In GitHub Actions, set repository secrets:
```bash
gh secret set AWS_ACCESS_KEY_ID
gh secret set AWS_SECRET_ACCESS_KEY
gh secret set OPENAI_API_KEY
gh secret set POSTGRES_DATABASE_URL
# ... etc
```

The CI/CD pipeline (`cd.yml`) reads from GitHub Secrets and injects them as environment variables.

### Strategy 3: Command-Line Arguments (One-offs)

```bash
./scripts/infra_start.sh my-cluster us-west-2 123456789012
./scripts/tear_down.sh  my-cluster us-west-2 123456789012
```

### Priority Order

Both scripts use this priority (highest to lowest):

1. **Command-line arguments** (most explicit)
2. **Environment variables** (good for CI/CD)
3. **`.env` file** (good for local development)
4. **Hard-coded defaults** (fallback only)

```bash
# Example: override with env vars
export CLUSTER_NAME=my-custom-cluster
export AWS_REGION=eu-west-1
./scripts/tear_down.sh

# Example: override with arguments (takes precedence over env vars)
./scripts/tear_down.sh another-cluster ap-south-1 999888777666
```

---

## Quick Reference: One-Liner Startup

If you have `scripts/infra_start.sh`:

```bash
chmod +x scripts/infra_start.sh
./scripts/infra_start.sh
```

With custom settings:

```bash
export CLUSTER_NAME=agentic-rag-cluster
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=123456789012
./scripts/infra_start.sh
```

Or with arguments:

```bash
./scripts/infra_start.sh my-cluster us-west-2 123456789012
```
