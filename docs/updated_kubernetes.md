# Manual EKS Deployment Guide — Step by Step

> **WARNING:** This file contains sensitive credentials. Do NOT commit it.
> It is listed in `.gitignore` and should stay local only.

Complete step-by-step manual guide for deploying the arXiv Paper Curator application to AWS EKS.
All commands are copy-paste ready. Follow every step in order.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [AWS Configuration](#2-aws-configuration)
3. [Create ECR Repositories](#3-create-ecr-repositories)
4. [Create Bedrock IAM Policy](#4-create-bedrock-iam-policy)
5. [Build & Push Docker Images](#5-build-and-push-docker-images)
6. [Create the EKS Cluster](#6-create-the-eks-cluster)
7. [Create IRSA Service Account for Bedrock](#7-create-irsa-service-account-for-bedrock)
8. [Create Kubernetes Secret](#8-create-kubernetes-secret)
9. [Install EBS CSI Driver + gp3 StorageClass](#9-install-ebs-csi-driver-and-gp3-storageclass)
10. [Deploy OpenSearch](#10-deploy-opensearch)
11. [Deploy OpenSearch Dashboards](#11-deploy-opensearch-dashboards)
12. [Create Airflow DAGs ConfigMap](#12-create-airflow-dags-configmap)
13. [Deploy RAG API](#13-deploy-rag-api)
14. [Deploy Airflow](#14-deploy-airflow)
15. [Install Metrics Server](#15-install-metrics-server-for-hpa)
16. [Verify Everything Works](#16-verify-everything-works)
17. [Troubleshooting](#17-troubleshooting)
18. [Teardown](#18-teardown)

---

## 1. Prerequisites

### Installed Tools (verified on this machine)

```bash
aws --version           # aws-cli/2.34.32
kubectl version --client  # v1.34.1
docker --version        # 29.5.2
git --version           # 2.33.0
python3 --version       # 3.12.9
```

### Install eksctl (the only missing tool)

```bash
brew tap weaveworks/tap
brew install weaveworks/tap/eksctl

# Verify
eksctl version
```

### Export Constants

Run these once at the start of every terminal session:

```bash
export AWS_REGION=us-east-1
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
export CLUSTER_NAME=agentic-rag-cluster
export K8S_NAMESPACE=production

echo "Account ID:  ${AWS_ACCOUNT_ID}"
echo "Region:      ${AWS_REGION}"
echo "ECR:         ${ECR_REGISTRY}"
echo "Cluster:     ${CLUSTER_NAME}"
```

---

## 2. AWS Configuration

Configure AWS CLI with credentials from `.env`:

```bash
aws configure
```

Enter when prompted:
```
AWS Access Key ID:     <YOUR_ACCESS_KEY_ID>
AWS Secret Access Key: <your-secret-from-.env>
Default region name:   us-east-1
Default output format: json
```

Verify it works:
```bash
aws sts get-caller-identity
```

> **Note:** Enable Bedrock model access in AWS Console before proceeding.
> Go to AWS Console -> Bedrock -> Model access -> Manage model access -> Enable "Meta Llama 3.1 70B Instruct"

---

## 3. Create ECR Repositories

ECR stores the Docker images. The EKS cluster pulls images from here.

```bash
# API image repository
aws ecr create-repository \
  --repository-name agentic-rag/api \
  --image-scanning-configuration scanOnPush=true \
  --region ${AWS_REGION}

# Airflow image repository
aws ecr create-repository \
  --repository-name agentic-rag/airflow \
  --image-scanning-configuration scanOnPush=true \
  --region ${AWS_REGION}

# Verify
aws ecr describe-repositories --region ${AWS_REGION} \
  --query 'repositories[].repositoryUri' --output table
```

---

## 4. Create Bedrock IAM Policy

This policy allows API pods to call AWS Bedrock for LLM inference and guardrails.

```bash
cat > /tmp/bedrock-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockInference",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ApplyGuardrail"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/*",
        "arn:aws:bedrock:us-east-1:*:inference-profile/*",
        "arn:aws:bedrock:us-east-1:*:guardrail/*"
      ]
    },
    {
      "Sid": "BedrockManagement",
      "Effect": "Allow",
      "Action": [
        "bedrock:ListFoundationModels",
        "bedrock:DescribeGuardrail"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name AgenticRAGBedrockPolicy \
  --policy-document file:///tmp/bedrock-policy.json \
  --description "Allows Agentic RAG API pods to call Bedrock LLM and guardrails"

export BEDROCK_POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGBedrockPolicy"
echo "Bedrock Policy ARN: ${BEDROCK_POLICY_ARN}"
```

---

## 5. Build and Push Docker Images

Make sure you are in the repo root (`/Users/sourangshupal/Downloads/Agentic-RAG-project`) and on the `deployment` branch.

```bash
cd /Users/sourangshupal/Downloads/Agentic-RAG-project
git checkout deployment

# Login to ECR
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REGISTRY}
```

### 5.1 Build API Image

EKS nodes run on `linux/amd64` (x86_64). If you are on a Mac with Apple Silicon, you **must** specify `--platform linux/amd64` otherwise the image will be `arm64` and will crash on EKS.

```bash
export IMAGE_TAG=manual

docker buildx build \
  --platform linux/amd64 \
  -t ${ECR_REGISTRY}/agentic-rag/api:${IMAGE_TAG} \
  -f Dockerfile \
  --push \
  .
```

### 5.2 Build Airflow Image

The Airflow Dockerfile references files at the repo root level. The files `requirements-airflow.txt` and `entrypoint.sh` already exist at repo root, so no manual copying is needed — just build with the repo root as the context:

```bash
docker buildx build \
  --platform linux/amd64 \
  -t ${ECR_REGISTRY}/agentic-rag/airflow:${IMAGE_TAG} \
  -f airflow/Dockerfile \
  --push \
  .
```

### 5.3 Verify Both Images Exist in ECR

```bash
aws ecr describe-images --repository-name agentic-rag/api --region ${AWS_REGION}
aws ecr describe-images --repository-name agentic-rag/airflow --region ${AWS_REGION}
```

---

## 6. Create the EKS Cluster

This step takes approximately **15-20 minutes**.
It creates: VPC, subnets, security groups, 2 EC2 nodes, and the EKS control plane.

```bash
eksctl create cluster -f deployment/eks/cluster.yaml
```

Expected output:
```
[+]  EKS cluster "agentic-rag-cluster" in "us-east-1" region is ready
```

> **Cost note:** This starts AWS billing immediately (~$0.10/hr for control plane + EC2 nodes).

### Verify Cluster

```bash
# Should show 2 nodes in Ready state
kubectl get nodes

# Check the correct context is active
kubectl config current-context
# Expected: arn:aws:eks:us-east-1:ACCOUNT_ID:cluster/agentic-rag-cluster
```

---

## 7. Create IRSA Service Account for Bedrock

IRSA (IAM Roles for Service Accounts) lets pods assume IAM roles without embedding static AWS credentials.

### 7.1 Create the Namespace

```bash
kubectl apply -f deployment/eks/namespace.yaml
```

### 7.2 Create the Service Account with IAM Role Attached

```bash
eksctl create iamserviceaccount \
  --cluster ${CLUSTER_NAME} \
  --region ${AWS_REGION} \
  --namespace ${K8S_NAMESPACE} \
  --name rag-api-sa \
  --attach-policy-arn ${BEDROCK_POLICY_ARN} \
  --approve \
  --override-existing-serviceaccounts
```

### 7.3 Verify the Service Account

```bash
kubectl get serviceaccount rag-api-sa -n ${K8S_NAMESPACE} -o yaml
```

You should see an annotation like:
```yaml
annotations:
  eks.amazonaws.com/role-arn: arn:aws:iam::${AWS_ACCOUNT_ID}:role/eksctl-agentic-rag-cluster-...
```

---

## 8. Create Kubernetes Secret

This Secret holds all application credentials inside the cluster.
**Replace all `REPLACE_ME_...` placeholders below with real values from your `.env` file before running.**

```bash
kubectl create secret generic rag-app-secrets \
  --namespace ${K8S_NAMESPACE} \
  --from-literal=DEBUG="false" \
  --from-literal=ENVIRONMENT="production" \
  --from-literal=PROVIDER="bedrock" \
  --from-literal=OPENSEARCH__HOST="http://opensearch:9200" \
  --from-literal=OPENSEARCH__INDEX_NAME="arxiv-papers" \
  --from-literal=OPENSEARCH__CHUNK_INDEX_SUFFIX="chunks" \
  --from-literal=OPENSEARCH__VECTOR_DIMENSION="1024" \
  --from-literal=POSTGRES_DATABASE_URL="REPLACE_ME_POSTGRES_DATABASE_URL" \
  --from-literal=REDIS__URL="REPLACE_ME_REDIS_URL" \
  --from-literal=REDIS__TTL_HOURS="6" \
  --from-literal=BEDROCK__AWS_ACCESS_KEY_ID="REPLACE_ME_BEDROCK_ACCESS_KEY_ID" \
  --from-literal=BEDROCK__AWS_SECRET_ACCESS_KEY="REPLACE_ME_BEDROCK_SECRET_KEY" \
  --from-literal=BEDROCK__AWS_REGION="us-east-1" \
  --from-literal=BEDROCK__MODEL_ID="REPLACE_ME_BEDROCK_MODEL_ID" \
  --from-literal=BEDROCK__GUARDRAIL_ID="REPLACE_ME_BEDROCK_GUARDRAIL_ID" \
  --from-literal=BEDROCK__GUARDRAIL_VERSION="DRAFT" \
  --from-literal=LANGFUSE__PUBLIC_KEY="REPLACE_ME_LANGFUSE_PUBLIC_KEY" \
  --from-literal=LANGFUSE__SECRET_KEY="REPLACE_ME_LANGFUSE_SECRET_KEY" \
  --from-literal=LANGFUSE__HOST="https://us.cloud.langfuse.com" \
  --from-literal=LANGFUSE__ENABLED="true" \
  --from-literal=LANGFUSE__FLUSH_AT="15" \
  --from-literal=LANGFUSE__FLUSH_INTERVAL="1.0" \
  --from-literal=LOGFIRE__TOKEN="REPLACE_ME_LOGFIRE_TOKEN" \
  --from-literal=LOGFIRE__ENABLED="true" \
  --from-literal=LOGFIRE__SERVICE_NAME="arxiv-rag" \
  --from-literal=LOGFIRE__ENVIRONMENT="production" \
  --from-literal=JINA_API_KEY="REPLACE_ME_JINA_API_KEY" \
  --from-literal=OPENAI_API_KEY="REPLACE_ME_OPENAI_API_KEY" \
  --from-literal=OPENAI_MODEL="gpt-4o-mini" \
  --from-literal=OPENAI_TIMEOUT="300" \
  --from-literal=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="REPLACE_ME_POSTGRES_DATABASE_URL" \
  --from-literal=AIRFLOW__CORE__EXECUTOR="LocalExecutor" \
  --from-literal=AIRFLOW__WEBSERVER__SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=AIRFLOW__API__AUTH_BACKENDS="airflow.api.auth.backend.basic_auth" \
  --from-literal=AIRFLOW__WEBSERVER__UPDATE_FAB_PERMS="False" \
  --from-literal=PYTHONWARNINGS="ignore::FutureWarning:airflow,ignore::DeprecationWarning:airflow" \
  --from-literal=ARXIV__MAX_RESULTS="2" \
  --from-literal=AIRFLOW__CORE__DAG_IGNORE_FILE_SYNTAX="regexp" \
  --dry-run=client -o yaml | kubectl apply -f -
```

> **IMPORTANT:** You MUST replace the following placeholders with real values from your `.env` file before running the command above:
> - `REPLACE_ME_POSTGRES_DATABASE_URL`
> - `REPLACE_ME_REDIS_URL`
> - `REPLACE_ME_BEDROCK_ACCESS_KEY_ID`
> - `REPLACE_ME_BEDROCK_SECRET_KEY`
> - `REPLACE_ME_BEDROCK_MODEL_ID`
> - `REPLACE_ME_BEDROCK_GUARDRAIL_ID`
> - `REPLACE_ME_LANGFUSE_PUBLIC_KEY`
> - `REPLACE_ME_LANGFUSE_SECRET_KEY`
> - `REPLACE_ME_LOGFIRE_TOKEN`
> - `REPLACE_ME_JINA_API_KEY`
> - `REPLACE_ME_OPENAI_API_KEY`
>
> **Tip:** Use the `scripts/secrets.sh` helper to automatically read values from `.env` and create the Secret. See `.github/workflows/cd.yml` for the exact Secret keys the CI/CD pipeline creates.

### Verify the Secret

```bash
kubectl get secret rag-app-secrets -n ${K8S_NAMESPACE}
# Expected: NAME               TYPE     DATA   AGE
#           rag-app-secrets    Opaque   34     5s
```

---

## 9. Install EBS CSI Driver and gp3 StorageClass

**CRITICAL:** The EBS CSI driver addon must be installed BEFORE deploying OpenSearch. Without it, the `gp3` StorageClass cannot provision PersistentVolumes, and the OpenSearch PVC will be stuck in `Pending` forever.

On EKS 1.23+, the in-tree `aws-ebs` provisioner was removed. The EBS CSI driver runs as a managed addon, but the driver pods need permission to create EBS volumes. We must attach the `AmazonEBSCSIDriverPolicy` to the **node IAM role** first.

### 9.1 Attach EBS CSI Policy to Node Role

```bash
export NODE_ROLE_NAME=$(aws eks describe-nodegroup \
  --cluster-name ${CLUSTER_NAME} \
  --nodegroup-name rag-workers \
  --region ${AWS_REGION} \
  --query 'nodegroup.nodeRole' --output text | awk -F'/' '{print $NF}')

aws iam attach-role-policy \
  --role-name ${NODE_ROLE_NAME} \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy

echo "Attached AmazonEBSCSIDriverPolicy to ${NODE_ROLE_NAME}"
```

### 9.2 Install the EBS CSI Driver Addon

```bash
aws eks create-addon \
  --cluster-name ${CLUSTER_NAME} \
  --addon-name aws-ebs-csi-driver \
  --region ${AWS_REGION} \
  --resolve-conflicts OVERWRITE
```

Wait ~2-3 minutes for the addon to deploy, then verify:

```bash
kubectl get pods -n kube-system | grep ebs
# Expected: ebs-csi-controller-xxx and ebs-csi-node-xxx pods in Running state
```

### 9.3 Create the gp3 StorageClass

The OpenSearch StatefulSet explicitly requests `storageClassName: gp3`. We must create this StorageClass because EKS does not create it automatically.

```bash
kubectl apply -f - <<'EOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: ebs.csi.aws.com
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
parameters:
  type: gp3
  encrypted: "true"
EOF
```

Verify:
```bash
kubectl get storageclass
# Expected: gp3 (default)
```

---

## 10. Deploy OpenSearch

OpenSearch must be deployed **first** because all other services depend on it.

```bash
# Apply services first (StatefulSet needs the headless service)
kubectl apply -f deployment/k8s/opensearch/service.yaml
kubectl apply -f deployment/k8s/opensearch/statefulset.yaml
```

> **Note:** The StatefulSet manifest already includes `fsGroup: 1000` in the pod security context. OpenSearch runs as user `1000`, and `fsGroup` ensures the EBS volume is chowned correctly on mount. No manual patching is needed.

### 10.1 Wait for OpenSearch to Be Ready

```bash
kubectl rollout status statefulset/opensearch -n ${K8S_NAMESPACE} --timeout=300s
```

OpenSearch takes about **2-3 minutes** to start on first boot (the init container sets kernel params, then OpenSearch itself initializes).

### 10.2 Verify OpenSearch Health

```bash
kubectl port-forward -n ${K8S_NAMESPACE} pod/opensearch-0 9200:9200 &
curl http://localhost:9200/_cluster/health | python3 -m json.tool
# Expected: {"status": "green" or "yellow", ...}
kill %1
```

---

## 11. Deploy OpenSearch Dashboards

```bash
kubectl apply -f deployment/k8s/opensearch-dashboards/service.yaml
kubectl apply -f deployment/k8s/opensearch-dashboards/deployment.yaml
```

---

## 12. Create Airflow DAGs ConfigMap

In Kubernetes, Airflow DAGs are loaded from a ConfigMap (not bind-mounted like in Docker Compose).

```bash
kubectl create configmap airflow-dags \
  --namespace ${K8S_NAMESPACE} \
  --from-file=airflow/dags/ \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## 13. Deploy RAG API

### 13.1 Update Image Tags in Deployment Manifests

The deployment YAMLs have placeholder image names. Replace them with the actual ECR image URI.

```bash
# macOS
sed -i '' "s|image: REPLACE_WITH_ECR_URI/agentic-rag/api:latest|image: ${ECR_REGISTRY}/agentic-rag/api:${IMAGE_TAG}|g" \
  deployment/k8s/api/deployment.yaml

# Linux
# sed -i "s|image: REPLACE_WITH_ECR_URI/agentic-rag/api:latest|image: ${ECR_REGISTRY}/agentic-rag/api:${IMAGE_TAG}|g" \
#   deployment/k8s/api/deployment.yaml
```

### 13.2 Deploy API Service, Deployment, and HPA

```bash
kubectl apply -f deployment/k8s/api/service.yaml
kubectl apply -f deployment/k8s/api/deployment.yaml
kubectl apply -f deployment/k8s/api/hpa.yaml
```

### 13.3 Wait for API Rollout

```bash
kubectl rollout status deployment/rag-api -n ${K8S_NAMESPACE} --timeout=300s
```

---

## 14. Deploy Airflow

### 14.1 Update Airflow Image Tag

```bash
# macOS
sed -i '' "s|image: REPLACE_WITH_ECR_URI/agentic-rag/airflow:latest|image: ${ECR_REGISTRY}/agentic-rag/airflow:${IMAGE_TAG}|g" \
  deployment/k8s/airflow/deployment.yaml

# Linux
# sed -i "s|image: REPLACE_WITH_ECR_URI/agentic-rag/airflow:latest|image: ${ECR_REGISTRY}/agentic-rag/airflow:${IMAGE_TAG}|g" \
#   deployment/k8s/airflow/deployment.yaml
```

### 14.2 Apply Airflow Manifests

```bash
kubectl apply -f deployment/k8s/airflow/service.yaml
kubectl apply -f deployment/k8s/airflow/deployment.yaml
```

### 14.3 Wait for Airflow Rollout

```bash
# Airflow takes 5+ minutes on first boot (runs db migrate)
kubectl rollout status deployment/airflow -n ${K8S_NAMESPACE} --timeout=600s
```

---

## 15. Install Metrics Server (for HPA)

The Horizontal Pod Autoscaler (HPA) needs Metrics Server to read CPU/memory usage.

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

Wait 1 minute, then verify HPA:
```bash
kubectl get hpa -n ${K8S_NAMESPACE}
# Expected:
# NAME          REFERENCE           TARGETS   MINPODS   MAXPODS   REPLICAS
# rag-api-hpa   Deployment/rag-api  15%/70%   2         6         2
```

---

## 16. Verify Everything Works

### 16.1 Check All Pods Are Running

```bash
kubectl get pods -n ${K8S_NAMESPACE}

# Expected output (all should be Running):
# NAME                                    READY   STATUS    RESTARTS   AGE
# airflow-xxxxxxxxx-xxxxx                 1/1     Running   0          5m
# opensearch-0                            1/1     Running   0          8m
# opensearch-dashboards-xxxxxxxxx-xxxxx   1/1     Running   0          6m
# rag-api-xxxxxxxxx-xxxxx                 1/1     Running   0          4m
# rag-api-xxxxxxxxx-xxxxx                 1/1     Running   0          4m
```

> **Note:** Airflow may take 3-5 minutes to start on first boot. This is normal.

### 16.2 Get Service URLs

```bash
export API_URL=$(kubectl get service rag-api -n ${K8S_NAMESPACE} \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
export AIRFLOW_URL=$(kubectl get service airflow -n ${K8S_NAMESPACE} \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
export DASHBOARDS_URL=$(kubectl get service opensearch-dashboards -n ${K8S_NAMESPACE} \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "RAG API:    http://${API_URL}"
echo "Airflow:    http://${AIRFLOW_URL}:8080"
echo "Dashboards: http://${DASHBOARDS_URL}:5601"
```

> It may take 2-3 minutes for AWS to provision the Classic Load Balancers.

### 16.3 Test the Health Endpoint

```bash
curl http://${API_URL}/api/v1/health | python3 -m json.tool
```

Expected response:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "production",
  "service_name": "rag-api",
  "services": {
    "database": {"status": "healthy", "message": "Connected successfully"},
    "opensearch": {"status": "healthy", "message": "Index 'arxiv-papers' with 0 documents"}
  }
}
```

### 16.4 Test the Agentic RAG Endpoint

```bash
curl -X POST http://${API_URL}/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is vector policy?"}' | python3 -m json.tool
```

### 16.5 Test Guardrail Filters

```bash
# Should be blocked (off-topic)
curl -X POST http://${API_URL}/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the best pasta recipe?"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('filter:', d['guardrail_filter'])"
# Expected: topic_blocked: off-topic-queries

# Should be blocked (misconduct)
curl -X POST http://${API_URL}/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I use ML to plagiarize research papers?"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('filter:', d['guardrail_filter'])"
# Expected: content_blocked: MISCONDUCT
```

### 16.6 Verify OpenSearch

```bash
kubectl port-forward -n ${K8S_NAMESPACE} pod/opensearch-0 9200:9200 &
curl http://localhost:9200/_cat/indices?v
kill %1
```

### 16.7 Open UIs in Browser

- **API Swagger Docs**: `http://${API_URL}/docs`
- **Airflow UI**: `http://${AIRFLOW_URL}:8080` (login: `admin` / `admin`)
- **OpenSearch Dashboards**: `http://${DASHBOARDS_URL}:5601`

---

## 17. Troubleshooting

### OpenSearch PVC stuck in `Pending`

**Symptom:** `kubectl get pvc -n ${K8S_NAMESPACE}` shows `opensearch-data-opensearch-0` stuck in `Pending`.

**Root cause 1:** The EBS CSI driver addon is not installed. The `gp3` StorageClass exists in the manifest, but the `ebs.csi.aws.com` provisioner isn't running.

**Fix:** Install the addon (see [Step 9](#9-install-ebs-csi-driver-and-gp3-storageclass)).

```bash
kubectl get pvc -n ${K8S_NAMESPACE}
kubectl get storageclass
kubectl describe pvc opensearch-data-opensearch-0 -n ${K8S_NAMESPACE}
# If Events show "Waiting for a volume to be created by the external provisioner 'ebs.csi.aws.com':"
aws eks create-addon --name aws-ebs-csi-driver --cluster ${CLUSTER_NAME} --region ${AWS_REGION} --force
```

**Root cause 2:** The node IAM role does not have the `AmazonEBSCSIDriverPolicy` attached. The driver pods are running but cannot call EC2 APIs to create volumes.

**Fix:** Attach the policy (see [Step 9.1](#91-attach-ebs-csi-policy-to-node-role)).

```bash
aws iam attach-role-policy \
  --role-name ${NODE_ROLE_NAME} \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy
```

**Root cause 3:** The `gp3` StorageClass does not exist. OpenSearch requests `storageClassName: gp3`, but if the StorageClass was never created, the PVC has nowhere to bind.

**Fix:** Create the StorageClass (see [Step 9.3](#93-create-the-gp3-storageclass)).

### OpenSearch pod Running but not Ready (restarts loop)

**Symptom:** `kubectl get pods -n ${K8S_NAMESPACE}` shows `opensearch-0` with `0/1` Ready and increasing `RESTARTS`.

**Root cause:** OpenSearch runs as user `1000`, but the EBS volume is mounted with `root` ownership. OpenSearch crashes with `AccessDeniedException: /usr/share/opensearch/data/nodes`.

**Fix:** The `deployment/k8s/opensearch/statefulset.yaml` manifest already includes `fsGroup: 1000` in the pod security context. If you are using an older/modified manifest, verify it has this setting:

```bash
kubectl get statefulset opensearch -n ${K8S_NAMESPACE} -o jsonpath='{.spec.template.spec.securityContext}'
# Expected: {"fsGroup":1000}
```

If missing, apply it:
```bash
kubectl patch statefulset opensearch -n ${K8S_NAMESPACE} --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/securityContext", "value": {"fsGroup": 1000}}]'
kubectl delete pod opensearch-0 -n ${K8S_NAMESPACE}
kubectl rollout status statefulset/opensearch -n ${K8S_NAMESPACE} --timeout=300s
```

### Pod stuck in `Pending`

```bash
kubectl describe pod <pod-name> -n ${K8S_NAMESPACE}
# Common cause: "Insufficient memory" -> scale up node group
```

### Pod in `CrashLoopBackOff`

```bash
kubectl logs <pod-name> -n ${K8S_NAMESPACE} --previous
# Common cause: missing Secret key or OpenSearch not ready
```

### API returns 500 errors

```bash
kubectl logs -n ${K8S_NAMESPACE} -l app=rag-api --tail=100
# Check: POSTGRES_DATABASE_URL, BEDROCK__MODEL_ID, OpenSearch index exists
```

### Airflow Docker build fails with "not found"

**Symptom:** `docker buildx build` fails with `failed to compute cache key: "/entrypoint.sh": not found`.

**Root cause:** The build context is `.` (repo root), but `requirements-airflow.txt` and `entrypoint.sh` are expected at repo root. These files exist at repo root by default. If they are missing, the build will fail.

**Fix:** Verify the files exist at repo root:
```bash
ls -la requirements-airflow.txt entrypoint.sh
```

If missing, check them out from git or copy them from `airflow/`:
```bash
cp airflow/requirements-airflow.txt .
cp airflow/entrypoint.sh .
```

### HPA shows `<unknown>/70%`

**Symptom:** `kubectl get hpa -n ${K8S_NAMESPACE}` shows `TARGETS` as `<unknown>/70%`.

**Root cause:** Metrics Server is not installed. HPA cannot read pod CPU/memory metrics.

**Fix:** Install Metrics Server (see [Step 15](#15-install-metrics-server-for-hpa)).

### View all logs

```bash
# API logs
kubectl logs -n ${K8S_NAMESPACE} -l app=rag-api --tail=50 --prefix=true

# Airflow logs
kubectl logs -n ${K8S_NAMESPACE} -l app=airflow --tail=100

# OpenSearch logs
kubectl logs opensearch-0 -n ${K8S_NAMESPACE} --tail=50

# All events
kubectl get events -n ${K8S_NAMESPACE} --sort-by='.lastTimestamp' | tail -20
```

---

## 18. Teardown

> **WARNING:** These commands permanently delete all AWS resources and data.

Use the battle-tested teardown script:

```bash
./scripts/tear_down.sh
```

Or run the manual commands:

```bash
# 1. Delete all Kubernetes resources
kubectl delete namespace ${K8S_NAMESPACE}

# 2. Delete the EKS cluster (~10-15 minutes)
eksctl delete cluster --name ${CLUSTER_NAME} --region ${AWS_REGION}

# 3. Delete ECR repositories and all images
aws ecr delete-repository --repository-name agentic-rag/api --force --region ${AWS_REGION}
aws ecr delete-repository --repository-name agentic-rag/airflow --force --region ${AWS_REGION}

# 4. Delete IAM policy (must detach from roles first)
aws iam detach-role-policy \
  --role-name $(aws iam list-entities-for-policy \
    --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGBedrockPolicy" \
    --entity-filter Role --query 'PolicyRoles[0].RoleName' --output text) \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGBedrockPolicy" 2>/dev/null || true
aws iam delete-policy --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGBedrockPolicy"
```

---

## Quick Reference

```bash
# Check all pods
kubectl get pods -n ${K8S_NAMESPACE}

# View live API logs
kubectl logs -n ${K8S_NAMESPACE} -l app=rag-api -f

# Get service URLs
kubectl get services -n ${K8S_NAMESPACE}

# Restart API (rolling, zero-downtime)
kubectl rollout restart deployment/rag-api -n ${K8S_NAMESPACE}

# Scale API manually (overrides HPA temporarily)
kubectl scale deployment/rag-api --replicas=3 -n ${K8S_NAMESPACE}

# Execute shell inside a running pod
kubectl exec -it PODNAME -n ${K8S_NAMESPACE} -- /bin/bash

# Port-forward OpenSearch locally
kubectl port-forward -n ${K8S_NAMESPACE} pod/opensearch-0 9200:9200

# Decode a secret value
kubectl get secret rag-app-secrets -n ${K8S_NAMESPACE} \
  -o jsonpath='{.data.POSTGRES_DATABASE_URL}' | base64 -d

# Save money: scale nodes to 0
eksctl scale nodegroup --cluster ${CLUSTER_NAME} --name rag-workers --nodes 0

# Restore nodes
eksctl scale nodegroup --cluster ${CLUSTER_NAME} --name rag-workers --nodes 2
```
