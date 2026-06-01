# 05 — CI/CD Pipeline: GitHub Actions to EKS

This sequence diagram shows the complete flow from `git push` on the `agentops` branch to a rolling update on the EKS cluster.

```mermaid
sequenceDiagram
    actor DEV as Developer
    participant GH as GitHub
    participant ACT as GitHub Actions
    participant AWS as AWS (ECR + EKS)
    participant K8S as EKS Cluster

    DEV->>GH: git push origin agentops
    GH->>ACT: trigger workflow<br/>cd.yml

    rect rgb(230, 245, 255)
        Note over ACT,AWS: Job 1: Build & Push Docker Images
        ACT->>ACT: Checkout code
        ACT->>AWS: Configure credentials
        ACT->>AWS: ECR login
        ACT->>ACT: Free disk space<br/>rm dotnet/ghc/android
        ACT->>ACT: Set up Docker Buildx
        ACT->>AWS: docker/build-push-action<br/>rag-api image<br/>cache-from/to: gha
        AWS-->>ACT: Image pushed<br/>sha: 6bbc34b
        ACT->>AWS: docker/build-push-action<br/>rag-airflow image<br/>cache-from/to: gha
        AWS-->>ACT: Image pushed<br/>sha: 6bbc34b
    end

    rect rgb(255, 245, 230)
        Note over ACT,K8S: Job 2: Deploy to EKS
        ACT->>AWS: aws eks update-kubeconfig
        AWS-->>ACT: kubectl connected
        ACT->>K8S: kubectl apply namespace
        K8S-->>ACT: production namespace ready
        ACT->>K8S: kubectl create secret generic<br/>rag-app-secrets<br/>(all env vars from GitHub Secrets)
        K8S-->>ACT: Secret updated
        ACT->>K8S: kubectl apply<br/>OpenSearch StatefulSet + Service
        K8S-->>ACT: OpenSearch rollout complete
        ACT->>K8S: kubectl apply<br/>OpenSearch Dashboards Deployment
        ACT->>K8S: kubectl create configmap<br/>airflow-dags
        ACT->>ACT: sed replace<br/>image placeholder → ECR URI
        ACT->>K8S: kubectl apply<br/>rag-api Deployment + Service + HPA
        K8S-->>ACT: Deployment accepted
        ACT->>K8S: kubectl apply<br/>airflow Deployment + Service
        K8S-->>ACT: Deployment accepted
        ACT->>K8S: kubectl rollout status<br/>rag-api --timeout=300s
        K8S-->>ACT: 2/2 replicas ready
        ACT->>K8S: kubectl rollout status<br/>airflow --timeout=600s
        K8S-->>ACT: 1/1 replica ready
        ACT->>DEV: Print summary<br/>ELB URLs + pod status
    end
```

## Why Two Jobs?

| Job | Runs on | Purpose | Output |
|---|---|---|---|
| **build-and-push** | `ubuntu-latest` | Build Docker images, push to ECR | `api-image` + `airflow-image` URIs |
| **deploy** | `ubuntu-latest` | Run kubectl against EKS | Live cluster updated |
| **needs** dependency | — | Deploy waits for build to finish | Prevents deploying a failed build |

## Concurrency Protection

```yaml
concurrency:
  group: deploy-production
  cancel-in-progress: true
```

This means if you push twice in quick succession, the **older run is cancelled** and the newer one takes over. This prevents two deployments from fighting each other.

## Rolling Update Strategy

When the deployment is applied, Kubernetes does a **rolling update**:
1. Create 1 new pod with the new image
2. Wait for it to be Ready
3. Delete 1 old pod
4. Repeat until all pods are new

This ensures **zero downtime** — the old pods keep serving traffic until the new ones are healthy.

## The Disk-Space Fix

Our first CI run failed with:
```
System.IO.IOException: No space left on device
```

The fix was three-fold:
1. **Free up disk** — remove pre-installed .NET, GHC, Android SDK (~10 GB)
2. **Switch to `docker/build-push-action`** — uses GitHub Actions cache backend (`type=gha`) instead of storing layers on disk
3. **Buildx** — enables advanced caching without intermediate layer bloat
