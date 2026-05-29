# Complete Infrastructure Teardown Guide

> This guide explains **every resource** that was created during the Agentic RAG deployment and **how to destroy each one safely**, along with the reason why it must be destroyed to avoid AWS charges.

---

## Table of Contents

1. [What Gets Deployed](#what-gets-deployed)
2. [Prerequisites](#prerequisites)
3. [Teardown Sequence](#teardown-sequence)
4. [Step-by-Step Manual Commands](#step-by-step-manual-commands)
5. [What Remains After Teardown](#what-remains-after-teardown)
6. [Troubleshooting](#troubleshooting)
7. [Cost Impact](#cost-impact)

---

## What Gets Deployed

The following AWS resources are created when you deploy the Agentic RAG system. Each row shows the resource, why it costs money, and what destroys it.

| Resource | Why It Costs | Destroyed By |
|---|---|---|
| **EKS Control Plane** | $0.10/hour ($73/month) | `eksctl delete cluster` |
| **EC2 Worker Nodes** (2 x t3.medium) | $0.0416/hour each ($60/month total) | Node group deletion (part of `eksctl delete cluster`) |
| **Elastic Load Balancers** (3 Classic ELBs) | $0.0225/hour each ($49/month total) | Deleted automatically when K8s Services are deleted |
| **ECR Repositories** (api + airflow) | $0.10/GB/month for stored images | `aws ecr delete-repository --force` |
| **EBS Volumes** (OpenSearch PVC) | $0.10/GB/month | Deleted with node group |
| **NAT Gateway** (if VPC has one) | $0.045/hour ($32/month) | Deleted with VPC (part of `eksctl delete cluster`) |
| **VPC + Subnets** | Free, but NAT/ELB inside it cost money | Deleted with cluster |
| **IAM Roles & Policies** | Free, but security risk if left behind | Deleted with CloudFormation stacks |

**Total running cost**: ~$210/month if left running 24/7.

---

## Prerequisites

Before running teardown, ensure you have:

| Tool | Purpose | Install |
|---|---|---|
| `aws` CLI | Talk to AWS APIs | `brew install awscli` or `pip install awscli` |
| `eksctl` | Manage EKS clusters | `brew install eksctl` |
| `kubectl` | Manage Kubernetes resources | `brew install kubectl` |
| `helm` | Manage Helm releases | `brew install helm` |

And configure AWS credentials:

```bash
aws configure
# OR
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_REGION=us-east-1
```

---

## Teardown Sequence

**Order matters.** We delete from the "inside out" — innermost resources first, then outer infrastructure. This prevents orphaned resources that cost money but are hard to find.

```
┌─────────────────────────────────────────────────────────────┐
│  1. Helm Releases    (Grafana monitoring inside K8s)        │
│  2. K8s Namespaces   (production + monitoring)              │
│  3. EKS Cluster      (control plane + worker nodes + VPC)   │
│  4. ECR Repositories (container images)                     │
│  5. Orphaned ELBs    (safety net for any leftover LBs)      │
│  6. CloudFormation   (safety net for any leftover stacks)    │
└─────────────────────────────────────────────────────────────┘
```

**Why this order?**
- If you delete the EKS cluster first, Helm and K8s resources inside it vanish automatically — but sometimes ELBs are left behind. We prefer explicit cleanup.
- If you delete namespaces before Helm releases, Helm may leave orphaned ConfigMaps ("release secrets") in the cluster.

---

## Step-by-Step Manual Commands

You can run these commands one-by-one, or use `scripts/tear_down.sh` which automates the entire sequence.

### Step 1: Uninstall Helm Releases

**Why:** Grafana Cloud Kubernetes Monitoring was installed via Helm in the `monitoring` namespace. It deploys Alloy collectors, kube-state-metrics, node-exporter, OpenCost, and Kepler pods. These pods consume CPU/memory on worker nodes, which costs money.

```bash
# Delete the sub-chart releases first
helm uninstall grafana-k8s-monitoring-alloy-logs      -n monitoring 2>/dev/null
helm uninstall grafana-k8s-monitoring-alloy-metrics   -n monitoring 2>/dev/null
helm uninstall grafana-k8s-monitoring-alloy-singleton  -n monitoring 2>/dev/null

# Delete the parent umbrella release
helm uninstall grafana-k8s-monitoring                  -n monitoring 2>/dev/null
```

**Verify:** `helm list --all-namespaces` should show no releases.

---

### Step 2: Delete Kubernetes Namespaces

**Why:** The `production` namespace contains:
- **rag-api Deployment** — FastAPI app (runs on EC2, costs money)
- **airflow Deployment** — Airflow webserver + scheduler (runs on EC2, costs money)
- **opensearch Deployment** — Search engine (runs on EC2 + EBS, costs money)
- **opensearch-dashboards Deployment** — OpenSearch UI (runs on EC2, costs money)
- **LoadBalancer Services** — Create Classic ELBs ($0.0225/hour each)
- **Secrets, ConfigMaps, PVCs** — Stored in etcd (free, but part of the cluster)

Deleting the namespace cascades and destroys everything inside it.

```bash
kubectl delete namespace production --ignore-not-found=true --grace-period=0 --force
kubectl delete namespace monitoring --ignore-not-found=true --grace-period=0 --force
```

**What this destroys:**
- All pods (rag-api, airflow, opensearch, opensearch-dashboards)
- All services (including LoadBalancer-type services that created ELBs)
- All deployments, replica sets, config maps, secrets
- All persistent volume claims (PVCs) and their EBS volumes

**Verify:**
```bash
kubectl get namespaces | grep -E "production|monitoring"
# Should return nothing
```

---

### Step 3: Delete the EKS Cluster

**Why:** The EKS cluster itself costs $0.10/hour ($73/month) just for the control plane. The worker node group (2 x t3.medium) costs ~$60/month. The VPC, subnets, NAT gateway, and security groups are all managed by `eksctl` and are destroyed as part of this step.

```bash
eksctl delete cluster --name agentic-rag-cluster --region us-east-1 --wait
```

**What this destroys:**
- EKS control plane (the Kubernetes API server)
- EC2 Auto Scaling Group (and thus the 2 worker nodes)
- VPC, subnets, route tables, internet gateway, NAT gateway
- Security groups for the cluster and nodes
- IAM roles for the cluster and node group
- CloudWatch log group for cluster logs

**Time:** 10–15 minutes. The `--wait` flag blocks until CloudFormation finishes.

**Verify:**
```bash
eksctl get cluster --region us-east-1
# Should show "No clusters found"
```

**If it fails:**
Sometimes `eksctl delete` fails because a dependency (e.g., a security group) is still in use. The error message will tell you which CloudFormation stack failed. You can:
1. Go to AWS Console → CloudFormation → find the failed stack → delete it manually
2. Or retry: `eksctl delete cluster --name agentic-rag-cluster --region us-east-1 --force`

---

### Step 4: Delete ECR Repositories

**Why:** ECR charges $0.10 per GB per month for stored images. The `agentic-rag/api` and `agentic-rag/airflow` images are ~2–4 GB combined.

```bash
aws ecr delete-repository --repository-name agentic-rag/api     --region us-east-1 --force
aws ecr delete-repository --repository-name agentic-rag/airflow --region us-east-1 --force
```

The `--force` flag deletes all image tags inside the repository before deleting the repository itself.

**Verify:**
```bash
aws ecr describe-repositories --region us-east-1
# Should not list agentic-rag/api or agentic-rag/airflow
```

---

### Step 5: Clean Up Orphaned Load Balancers (Safety Net)

**Why:** Kubernetes Services of type `LoadBalancer` create AWS Classic ELBs. In most cases, deleting the namespace or cluster automatically deletes these ELBs. However, if a deletion was interrupted, ELBs can be left behind and continue to cost $0.0225/hour each.

```bash
# List all Classic ELBs
aws elb describe-load-balancers --region us-east-1 \
    --query 'LoadBalancerDescriptions[*].LoadBalancerName' --output table

# If any are left, delete them one by one:
aws elb delete-load-balancer --load-balancer-name <NAME> --region us-east-1
```

**Verify:** The Classic ELB list should be empty.

---

### Step 6: Check for Leftover CloudFormation Stacks (Safety Net)

**Why:** `eksctl` creates CloudFormation stacks for every component (cluster, node group, add-ons, IAM service accounts). These are usually deleted automatically with the cluster, but if something went wrong, they may remain.

```bash
aws cloudformation list-stacks --region us-east-1 \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --query 'StackSummaries[*].StackName' --output table
```

**If stacks with `agentic-rag` in the name remain:**
```bash
aws cloudformation delete-stack --stack-name <STACK_NAME> --region us-east-1
```

**Verify:** No stacks with `agentic-rag` in the name should remain.

---

## What Remains After Teardown

The following resources are **NOT** AWS resources and are **NOT** destroyed by this teardown. They are managed on their own platforms and do not incur AWS charges:

| Service | Platform | Why It Survives | Cost |
|---|---|---|---|
| **Neon PostgreSQL** | Neon (serverless) | Stores paper metadata | Free tier |
| **Upstash Redis** | Upstash (serverless) | Query cache | Free tier |
| **Langfuse Cloud** | Langfuse SaaS | Tracing & observability | Free tier |
| **OpenAI API** | OpenAI | LLM generation | Pay-per-use |
| **Jina AI Embeddings** | Jina AI | Vector embeddings | Pay-per-use |
| **Grafana Cloud** | Grafana Labs | Kubernetes monitoring | Free tier |
| **GitHub repository** | GitHub | Source code | Free (public) |

> **Note:** If you want to completely wipe the project, you must manually delete the Neon database, Upstash Redis instance, and Langfuse project from their respective web consoles. The teardown script only handles **AWS** resources.

---

## Troubleshooting

### "aws configure" not set up
```bash
export AWS_ACCESS_KEY_ID=YOUR_KEY
export AWS_SECRET_ACCESS_KEY=YOUR_SECRET
export AWS_REGION=us-east-1
```

### "eksctl delete" times out
The node group deletion can take 10–15 minutes. If it times out:
1. Check AWS Console → CloudFormation for stacks in `DELETE_IN_PROGRESS`
2. Wait for them to finish, then retry the command
3. If stuck, manually delete the stack in CloudFormation console

### ELBs won't delete
ELBs may refuse to delete if their security groups are still referenced. Delete the security group first (in EC2 console), then retry ELB deletion.

### ECR repository has images
Use `--force` flag: `aws ecr delete-repository --repository-name NAME --force`

---

## Cost Impact

| Resource | Monthly Cost | Saved After Teardown? |
|---|---|---|
| EKS Control Plane | ~$73 | Yes |
| EC2 Nodes (2 x t3.medium) | ~$60 | Yes |
| Classic ELBs (3) | ~$49 | Yes |
| ECR Storage (~4 GB) | ~$0.40 | Yes |
| EBS Volumes | ~$1 | Yes |
| **Total AWS savings** | **~$183/month** | **Yes** |

External services (Neon, Upstash, Langfuse, OpenAI) remain but are on free tiers or pay-per-use.

---

## Quick Reference: One-Liner Teardown

If you have `scripts/tear_down.sh`:

```bash
chmod +x scripts/tear_down.sh
./scripts/tear_down.sh
```

With custom settings:

```bash
export CLUSTER_NAME=agentic-rag-cluster
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=123456789012
./scripts/tear_down.sh
```

Or with arguments:

```bash
./scripts/tear_down.sh my-cluster us-west-2 123456789012
```
