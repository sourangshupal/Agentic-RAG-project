# Agentic RAG — EKS Deployment Guide

Complete step-by-step guide for deploying the application to AWS EKS with GitHub Actions CI/CD.
Follow every step in order. Commands are copy-paste ready.

---

## Table of Contents

1. [Prerequisites — Install Tools](#1-prerequisites--install-tools)
2. [AWS Account Setup](#2-aws-account-setup)
3. [Create ECR Repositories](#3-create-ecr-repositories-docker-image-storage)
4. [Create IAM Policy for Bedrock](#4-create-iam-policy-for-bedrock)
5. [Create IAM User for CI/CD](#5-create-iam-user-for-cicd)
6. [Create the EKS Cluster](#6-create-the-eks-cluster)
7. [Create IAM Role for Bedrock (IRSA)](#7-create-irsa-service-account-for-bedrock)
8. [Set Up External Services](#8-set-up-external-services)
9. [Create AWS Bedrock Guardrail](#9-create-aws-bedrock-guardrail)
10. [Configure GitHub Actions Secrets](#10-configure-github-actions-secrets)
11. [Create Kubernetes Secret](#11-create-kubernetes-secret-first-time-only)
12. [Trigger the First Deployment](#12-trigger-the-first-deployment)
13. [Verify Everything Works](#13-verify-everything-works)
14. [How CI/CD Works Going Forward](#14-how-cicd-works-going-forward)
15. [Cost Management](#15-cost-management)
16. [Troubleshooting](#16-troubleshooting)
17. [Full Teardown](#17-full-teardown)

---

## 1. Prerequisites — Install Tools

Install these tools on your local machine before starting.

### macOS

```bash
# Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# AWS CLI — for managing AWS resources
brew install awscli

# eksctl — for creating and managing EKS clusters
brew tap weaveworks/tap
brew install weaveworks/tap/eksctl

# kubectl — for managing Kubernetes resources
brew install kubectl

# Verify all tools are installed
aws --version        # should print: aws-cli/2.x.x
eksctl version       # should print: 0.x.x
kubectl version --client  # should print: v1.31.x
```

### Linux (Ubuntu/Debian)

```bash
# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# eksctl
curl --silent --location \
  "https://github.com/weaveworks/eksctl/releases/latest/download/eksctl_$(uname -s)_amd64.tar.gz" \
  | tar xz -C /tmp
sudo mv /tmp/eksctl /usr/local/bin

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -sL https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl && sudo mv kubectl /usr/local/bin
```

---

## 2. AWS Account Setup

### 2.1 Sign in to AWS Console

Go to https://console.aws.amazon.com and sign in.

> If you don't have an AWS account: https://aws.amazon.com/free
> Credit card required but free tier available.

### 2.2 Enable AWS Bedrock Model Access

1. Go to AWS Console → search "Bedrock" → open **Amazon Bedrock**
2. In the left sidebar click **Model access**
3. Click **Manage model access**
4. Enable access for:
   - **Meta Llama 3.1 70B Instruct** (or whichever model you use)
   - **Anthropic Claude models** (optional fallback)
5. Click **Save changes**
6. Wait ~2 minutes for access to be approved

### 2.3 Configure AWS CLI

```bash
aws configure
```

Enter when prompted:
```
AWS Access Key ID:     [your root or IAM user key — we'll create a proper one in Step 5]
AWS Secret Access Key: [matching secret]
Default region name:   us-east-1
Default output format: json
```

> **Tip:** For now use your root credentials to bootstrap. After Step 5, switch to the dedicated IAM user.

### 2.4 Verify AWS CLI Works

```bash
# Should print your account ID, user ARN, and account ID
aws sts get-caller-identity

# Save your account ID — used in many commands below
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION=us-east-1
echo "Account ID: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
```

---

## 3. Create ECR Repositories (Docker Image Storage)

ECR (Elastic Container Registry) is where your Docker images are stored.
The CI/CD pipeline builds images and pushes them here; EKS pulls from here.

```bash
# Create repository for the FastAPI application image
aws ecr create-repository \
  --repository-name agentic-rag/api \
  --image-scanning-configuration scanOnPush=true \
  --region $AWS_REGION

# Create repository for the Airflow image
aws ecr create-repository \
  --repository-name agentic-rag/airflow \
  --image-scanning-configuration scanOnPush=true \
  --region $AWS_REGION

# Verify both repositories were created
aws ecr describe-repositories --region $AWS_REGION \
  --query 'repositories[].repositoryUri' --output table
```

Expected output:
```
---------------------------------------------------------
|                  DescribeRepositories                  |
+-------------------------------------------------------+
|  123456789012.dkr.ecr.us-east-1.amazonaws.com/agentic-rag/api    |
|  123456789012.dkr.ecr.us-east-1.amazonaws.com/agentic-rag/airflow|
+-------------------------------------------------------+
```

> Save the registry URL — you'll need it:
```bash
export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
echo "ECR Registry: $ECR_REGISTRY"
```

---

## 4. Create IAM Policy for Bedrock

This policy allows the API pods to call AWS Bedrock for LLM inference and guardrails.

```bash
# Create the policy JSON file
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

# Create the policy in AWS IAM
aws iam create-policy \
  --policy-name AgenticRAGBedrockPolicy \
  --policy-document file:///tmp/bedrock-policy.json \
  --description "Allows Agentic RAG API pods to call Bedrock LLM and guardrails"

# Save the policy ARN
export BEDROCK_POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGBedrockPolicy"
echo "Bedrock Policy ARN: $BEDROCK_POLICY_ARN"
```

---

## 5. Create IAM User for CI/CD

The GitHub Actions pipeline needs AWS credentials to:
- Push Docker images to ECR
- Deploy to EKS (kubectl)

```bash
# Create a dedicated IAM user for GitHub Actions
aws iam create-user --user-name github-actions-agentic-rag

# Create policy for ECR push and EKS access
cat > /tmp/cicd-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRPush",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EKSAccess",
      "Effect": "Allow",
      "Action": [
        "eks:DescribeCluster",
        "eks:ListClusters"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam create-policy \
  --policy-name AgenticRAGCICDPolicy \
  --policy-document file:///tmp/cicd-policy.json

# Attach both policies to the CI/CD user
aws iam attach-user-policy \
  --user-name github-actions-agentic-rag \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGCICDPolicy"

# Create access keys for the CI/CD user
# IMPORTANT: Save the output — you cannot retrieve the secret key again!
aws iam create-access-key --user-name github-actions-agentic-rag
```

> **Save the output!** You'll see something like:
> ```json
> {
>   "AccessKey": {
>     "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
>     "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
>   }
> }
> ```
> Copy both values — they go into GitHub Secrets in Step 10.

### Give the CI/CD User kubectl Access to EKS

After creating the EKS cluster (Step 6), run this to allow the CI/CD user to deploy:

```bash
# Run this AFTER Step 6 (cluster must exist first)
eksctl create iamidentitymapping \
  --cluster agentic-rag-cluster \
  --region $AWS_REGION \
  --arn "arn:aws:iam::${AWS_ACCOUNT_ID}:user/github-actions-agentic-rag" \
  --username github-actions \
  --group system:masters
```

---

## 6. Create the EKS Cluster

This is the most time-consuming step (~15-20 minutes).
eksctl creates everything: VPC, subnets, security groups, EC2 nodes, and the EKS control plane.

```bash
# Make sure you're in the repo root directory
cd /path/to/your/Agentic-RAG-project

# Create the cluster using the config file
eksctl create cluster -f deployment/eks/cluster.yaml
```

You'll see output like:
```
[✓]  EKS cluster "agentic-rag-cluster" in "us-east-1" region is ready
```

> **Cost note:** Creating the cluster starts billing (~$0.10/hour for the control plane alone).
> To stop billing later: see [Section 15 — Cost Management](#15-cost-management).

### Verify Cluster is Ready

```bash
# Should show 2 nodes in Ready state
kubectl get nodes

# Expected output:
# NAME                                           STATUS   ROLES    AGE   VERSION
# ip-192-168-xx-xx.us-east-1.compute.internal   Ready    <none>   2m    v1.31.x
# ip-192-168-xx-xx.us-east-1.compute.internal   Ready    <none>   2m    v1.31.x

# Check the cluster context is set correctly
kubectl config current-context
# Expected: arn:aws:eks:us-east-1:ACCOUNT_ID:cluster/agentic-rag-cluster
```

### Save kubeconfig for GitHub Actions

```bash
# Generate base64-encoded kubeconfig — this goes into GitHub Secrets in Step 10
cat ~/.kube/config | base64 | tr -d '\n' > /tmp/kubeconfig-b64.txt
echo "Kubeconfig saved to /tmp/kubeconfig-b64.txt"
echo "Length: $(wc -c < /tmp/kubeconfig-b64.txt) characters"
```

### Give CI/CD User kubectl Access (run this now)

```bash
eksctl create iamidentitymapping \
  --cluster agentic-rag-cluster \
  --region $AWS_REGION \
  --arn "arn:aws:iam::${AWS_ACCOUNT_ID}:user/github-actions-agentic-rag" \
  --username github-actions \
  --group system:masters
```

---

## 7. Create IRSA Service Account for Bedrock

IRSA (IAM Roles for Service Accounts) lets pods assume IAM roles without embedding static AWS credentials.
The API pods use this role to call Bedrock.

```bash
# Create the namespace first
kubectl apply -f deployment/eks/namespace.yaml

# Create the service account with the Bedrock IAM role attached
eksctl create iamserviceaccount \
  --cluster agentic-rag-cluster \
  --region $AWS_REGION \
  --namespace production \
  --name rag-api-sa \
  --attach-policy-arn $BEDROCK_POLICY_ARN \
  --approve \
  --override-existing-serviceaccounts

# Verify the service account was created with the IAM annotation
kubectl get serviceaccount rag-api-sa -n production -o yaml
```

You should see an annotation like:
```yaml
annotations:
  eks.amazonaws.com/role-arn: arn:aws:iam::123456789012:role/eksctl-agentic-rag-cluster-...
```

---

## 8. Set Up External Services

These services run outside Kubernetes. Get your credentials before deploying.

### 8.1 Neon PostgreSQL (Free Tier Available)

1. Go to https://neon.tech and create a free account
2. Create a new project called `agentic-rag`
3. In the project dashboard, click **Connection Details**
4. Select **Pooled connection** and copy the connection string
5. It looks like:
   ```
   postgresql+psycopg2://user:password@ep-xxx.us-east-1.aws.neon.tech/neondb?sslmode=require
   ```
6. Save this as `POSTGRES_DATABASE_URL`

### 8.2 Upstash Redis (Free Tier Available)

1. Go to https://upstash.com and create a free account
2. Create a new Redis database, select **us-east-1** region
3. In the database dashboard, click **Details**
4. Copy the **Redis URL (TLS)** — it looks like:
   ```
   rediss://default:token@optimum-ray-xxxxx.upstash.io:6379
   ```
5. Save this as `REDIS__URL`

### 8.3 Jina AI Embeddings (Free Tier Available)

1. Go to https://jina.ai and sign up
2. Go to https://jina.ai/embeddings and get your API key
3. It looks like: `jina_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`
4. Save this as `JINA_API_KEY`

### 8.4 Langfuse (Free Cloud Plan Available)

1. Go to https://langfuse.com and sign up
2. Create a new project called `agentic-rag`
3. In project settings → API Keys, create a new key pair
4. Save:
   - **Public Key** → `LANGFUSE__PUBLIC_KEY` (starts with `pk-lf-`)
   - **Secret Key** → `LANGFUSE__SECRET_KEY` (starts with `sk-lf-`)

### 8.5 Logfire (Optional — Free Tier Available)

1. Go to https://logfire.pydantic.dev and sign up
2. Create a new project
3. Go to Settings → Write tokens and create a token
4. Save as `LOGFIRE__TOKEN`
5. If you don't want to use Logfire, set `LOGFIRE__ENABLED=false` in the Secret

### 8.6 OpenAI API Key (Optional fallback)

Only needed if `PROVIDER=openai`. Get from https://platform.openai.com/api-keys

---

## 9. Create AWS Bedrock Guardrail

The guardrail filters off-topic queries, hate speech, PII, and validates answer grounding.
Run this script once — it creates the guardrail in your AWS account.

```bash
# Make sure you're in the repo root and your .env file has Bedrock credentials
cd /path/to/your/Agentic-RAG-project

# Activate your Python virtual environment
source .venv/bin/activate   # or: uv venv && source .venv/bin/activate

# Make sure .env has these set:
# BEDROCK__AWS_ACCESS_KEY_ID=your-key
# BEDROCK__AWS_SECRET_ACCESS_KEY=your-secret
# BEDROCK__AWS_REGION=us-east-1

# Run the guardrail creation script
uv run python scripts/create_bedrock_guardrail.py
```

Output will look like:
```
Creating Bedrock Guardrail in region us-east-1...

✓ Guardrail created successfully!
  guardrailId  : 4rbky7y6etl1
  guardrailArn : arn:aws:bedrock:us-east-1:123456789012:guardrail/4rbky7y6etl1
  version      : DRAFT

Add to .env:
  BEDROCK__GUARDRAIL_ID=4rbky7y6etl1
  BEDROCK__GUARDRAIL_VERSION=DRAFT
```

> Save the `guardrailId` — it goes into GitHub Secrets as `BEDROCK__GUARDRAIL_ID`.

---

## 10. Configure GitHub Actions Secrets

GitHub Secrets are encrypted variables that GitHub Actions can read during CI/CD runs.
Your Docker images and Kubernetes deployments use these secrets.

### How to Add Secrets

1. Go to your GitHub repository: `https://github.com/YOUR_USERNAME/Agentic-RAG-project`
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** for each secret below

### Required Secrets (add all of these)

| Secret Name | Value | Where to Get It |
|-------------|-------|-----------------|
| `AWS_ACCESS_KEY_ID` | Access key from Step 5 | IAM → Users → github-actions-agentic-rag → Security credentials |
| `AWS_SECRET_ACCESS_KEY` | Secret key from Step 5 | Saved from Step 5 output |
| `AWS_ACCOUNT_ID` | Your 12-digit account ID | `aws sts get-caller-identity --query Account --output text` |
| `KUBE_CONFIG` | Base64 kubeconfig from Step 6 | `cat /tmp/kubeconfig-b64.txt` |
| `POSTGRES_DATABASE_URL` | Neon connection string | Step 8.1 |
| `REDIS__URL` | Upstash Redis URL | Step 8.2 |
| `JINA_API_KEY` | Jina API key | Step 8.3 |
| `LANGFUSE__PUBLIC_KEY` | Langfuse public key | Step 8.4 |
| `LANGFUSE__SECRET_KEY` | Langfuse secret key | Step 8.4 |
| `LOGFIRE__TOKEN` | Logfire token | Step 8.5 |
| `OPENAI_API_KEY` | OpenAI key (or set empty string) | https://platform.openai.com/api-keys |
| `BEDROCK__AWS_ACCESS_KEY_ID` | AWS key with Bedrock access | Same as Step 5 or a dedicated key |
| `BEDROCK__AWS_SECRET_ACCESS_KEY` | Matching secret | Same as above |
| `BEDROCK__MODEL_ID` | Bedrock inference profile ARN | AWS Console → Bedrock → Inference profiles |
| `BEDROCK__GUARDRAIL_ID` | Guardrail ID from Step 9 | e.g. `4rbky7y6etl1` |
| `AIRFLOW__WEBSERVER__SECRET_KEY` | Random secret string | Run: `python -c "import secrets; print(secrets.token_hex(32))"` |

### Get Your Bedrock Model ARN

```bash
# List available inference profiles in your account
aws bedrock list-inference-profiles --region us-east-1 \
  --query 'inferenceProfileSummaries[*].[inferenceProfileName,inferenceProfileArn]' \
  --output table
```

Copy the ARN for `us.meta.llama3-1-70b-instruct-v1:0` (or whichever model you want).
It looks like: `arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.meta.llama3-1-70b-instruct-v1:0`

---

## 11. Create Kubernetes Secret (First Time Only)

The Kubernetes Secret holds all application credentials inside the cluster.
The CI/CD pipeline recreates this on every deployment, but you need it manually for the first deploy.

> **Note:** The cd.yml workflow creates this Secret automatically. You only need this
> step if you're deploying manually without triggering the GitHub Actions pipeline.

```bash
# Generate a random Airflow secret key if you haven't already
AIRFLOW_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
echo "Airflow secret key: $AIRFLOW_SECRET"

# Create the Secret — replace all PLACEHOLDER values with real ones
kubectl create secret generic rag-app-secrets \
  --namespace production \
  --from-literal=DEBUG="false" \
  --from-literal=ENVIRONMENT="production" \
  --from-literal=PROVIDER="bedrock" \
  --from-literal=OPENSEARCH__HOST="http://opensearch:9200" \
  --from-literal=OPENSEARCH__INDEX_NAME="arxiv-papers" \
  --from-literal=OPENSEARCH__CHUNK_INDEX_SUFFIX="chunks" \
  --from-literal=OPENSEARCH__VECTOR_DIMENSION="1024" \
  --from-literal=POSTGRES_DATABASE_URL="YOUR_NEON_URL" \
  --from-literal=REDIS__URL="YOUR_UPSTASH_URL" \
  --from-literal=REDIS__TTL_HOURS="6" \
  --from-literal=BEDROCK__AWS_ACCESS_KEY_ID="YOUR_KEY" \
  --from-literal=BEDROCK__AWS_SECRET_ACCESS_KEY="YOUR_SECRET" \
  --from-literal=BEDROCK__AWS_REGION="us-east-1" \
  --from-literal=BEDROCK__MODEL_ID="YOUR_BEDROCK_MODEL_ARN" \
  --from-literal=BEDROCK__GUARDRAIL_ID="YOUR_GUARDRAIL_ID" \
  --from-literal=BEDROCK__GUARDRAIL_VERSION="DRAFT" \
  --from-literal=LANGFUSE__PUBLIC_KEY="YOUR_LANGFUSE_PUBLIC_KEY" \
  --from-literal=LANGFUSE__SECRET_KEY="YOUR_LANGFUSE_SECRET_KEY" \
  --from-literal=LANGFUSE__HOST="https://us.cloud.langfuse.com" \
  --from-literal=LANGFUSE__ENABLED="true" \
  --from-literal=LANGFUSE__FLUSH_AT="15" \
  --from-literal=LANGFUSE__FLUSH_INTERVAL="1.0" \
  --from-literal=LOGFIRE__TOKEN="YOUR_LOGFIRE_TOKEN" \
  --from-literal=LOGFIRE__ENABLED="true" \
  --from-literal=LOGFIRE__SERVICE_NAME="arxiv-rag" \
  --from-literal=LOGFIRE__ENVIRONMENT="production" \
  --from-literal=JINA_API_KEY="YOUR_JINA_KEY" \
  --from-literal=OPENAI_API_KEY="YOUR_OPENAI_KEY" \
  --from-literal=OPENAI_MODEL="gpt-4o-mini" \
  --from-literal=OPENAI_TIMEOUT="300" \
  --from-literal=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="YOUR_NEON_URL" \
  --from-literal=AIRFLOW__CORE__EXECUTOR="LocalExecutor" \
  --from-literal=AIRFLOW__WEBSERVER__SECRET_KEY="$AIRFLOW_SECRET" \
  --from-literal=AIRFLOW__API__AUTH_BACKENDS="airflow.api.auth.backend.basic_auth" \
  --from-literal=AIRFLOW__WEBSERVER__UPDATE_FAB_PERMS="False" \
  --from-literal=PYTHONWARNINGS="ignore::FutureWarning:airflow,ignore::DeprecationWarning:airflow" \
  --dry-run=client -o yaml | kubectl apply -f -

# Verify the Secret was created
kubectl get secret rag-app-secrets -n production
# Expected: NAME               TYPE     DATA   AGE
#           rag-app-secrets    Opaque   32     5s
```

---

## 12. Trigger the First Deployment

The GitHub Actions CD pipeline automatically runs when you push to the `deployment` branch.
The branch already exists (created during project setup). Just push a commit to trigger it.

### Option A — Push an Empty Commit to Trigger CI/CD

```bash
# From the repo root, on the deployment branch
git checkout deployment

# Trigger deployment by pushing an empty commit
git commit --allow-empty -m "chore: trigger initial EKS deployment"
git push origin deployment
```

### Option B — Manual Deployment (without GitHub Actions)

If you want to deploy manually (useful for debugging):

```bash
# 1. Build and push API image manually
docker build -t $ECR_REGISTRY/agentic-rag/api:manual -f Dockerfile .
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY
docker push $ECR_REGISTRY/agentic-rag/api:manual

# 2. Build and push Airflow image
docker build -t $ECR_REGISTRY/agentic-rag/airflow:manual -f airflow/Dockerfile .
docker push $ECR_REGISTRY/agentic-rag/airflow:manual

# 3. Apply all K8s manifests in order
kubectl apply -f deployment/eks/namespace.yaml

# OpenSearch (must be first — others depend on it)
kubectl apply -f deployment/k8s/opensearch/service.yaml
kubectl apply -f deployment/k8s/opensearch/statefulset.yaml
kubectl rollout status statefulset/opensearch -n production --timeout=300s

# Dashboards
kubectl apply -f deployment/k8s/opensearch-dashboards/service.yaml
kubectl apply -f deployment/k8s/opensearch-dashboards/deployment.yaml

# Airflow DAGs ConfigMap
kubectl create configmap airflow-dags \
  --namespace production \
  --from-file=airflow/dags/ \
  --dry-run=client -o yaml | kubectl apply -f -

# Update image tags in manifests (replace placeholder)
sed -i "s|image: REPLACE_WITH_ECR_URI/agentic-rag/api:latest|image: $ECR_REGISTRY/agentic-rag/api:manual|g" \
  deployment/k8s/api/deployment.yaml
sed -i "s|image: REPLACE_WITH_ECR_URI/agentic-rag/airflow:latest|image: $ECR_REGISTRY/agentic-rag/airflow:manual|g" \
  deployment/k8s/airflow/deployment.yaml

# API
kubectl apply -f deployment/k8s/api/service.yaml
kubectl apply -f deployment/k8s/api/deployment.yaml
kubectl apply -f deployment/k8s/api/hpa.yaml

# Airflow
kubectl apply -f deployment/k8s/airflow/service.yaml
kubectl apply -f deployment/k8s/airflow/deployment.yaml

# 4. Install Metrics Server (needed for HPA)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### Watch the GitHub Actions Pipeline

After pushing to the `deployment` branch:
1. Go to your GitHub repository
2. Click **Actions** tab
3. You'll see **"CD — Build, Push, Deploy to EKS"** running
4. Click it to see live logs from each step

The pipeline takes about **10-15 minutes** for a fresh deployment:
- Build API image: ~3-5 min
- Build Airflow image: ~5-8 min (PyTorch is large)
- Deploy to EKS: ~3-5 min

---

## 13. Verify Everything Works

Run these commands after deployment completes.

### 13.1 Check All Pods Are Running

```bash
kubectl get pods -n production

# Expected output (all pods should be Running, not Pending/CrashLoopBackOff):
# NAME                                    READY   STATUS    RESTARTS   AGE
# airflow-xxxxxxxxx-xxxxx                 1/1     Running   0          5m
# opensearch-0                            1/1     Running   0          8m
# opensearch-dashboards-xxxxxxxxx-xxxxx   1/1     Running   0          6m
# rag-api-xxxxxxxxx-xxxxx                 1/1     Running   0          4m
# rag-api-xxxxxxxxx-xxxxx                 1/1     Running   0          4m
```

> **Airflow takes 3-5 minutes to start on first boot** (runs database migrations).
> It will show `0/1 Running` during this time — this is normal.

### 13.2 Get Service URLs

```bash
kubectl get services -n production

# Look for the EXTERNAL-IP column — these are the AWS ELB hostnames
# It may show <pending> for 2-3 minutes while AWS provisions the load balancers
```

Once external IPs appear, save them:

```bash
export API_URL=$(kubectl get service rag-api -n production \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
export AIRFLOW_URL=$(kubectl get service airflow -n production \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
export DASHBOARDS_URL=$(kubectl get service opensearch-dashboards -n production \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')

echo "RAG API:    http://$API_URL"
echo "Airflow:    http://$AIRFLOW_URL:8080"
echo "Dashboards: http://$DASHBOARDS_URL:5601"
```

### 13.3 Test the Health Endpoint

```bash
curl http://$API_URL/api/v1/health | python3 -m json.tool
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

### 13.4 Test the Agentic RAG Endpoint

```bash
curl -X POST http://$API_URL/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is vector policy?"}' | python3 -m json.tool
```

Expected response (once papers are ingested):
```json
{
  "query": "What is vector policy?",
  "answer": "...",
  "guardrail_filter": "Content passed all guardrail checks",
  "output_guardrail_filter": "Content passed all guardrail checks",
  "reasoning_steps": ["Validated query scope (score: 100/100)", "..."],
  "trace_id": "019e..."
}
```

### 13.5 Test Guardrail Filters

```bash
# Should be blocked — off-topic
curl -X POST http://$API_URL/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the best pasta recipe?"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('filter:', d['guardrail_filter'])"

# Expected: filter: topic_blocked: off-topic-queries

# Should be blocked — harmful content
curl -X POST http://$API_URL/api/v1/ask-agentic \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I use ML to plagiarize research papers?"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('filter:', d['guardrail_filter'])"

# Expected: filter: content_blocked: MISCONDUCT
```

### 13.6 Verify OpenSearch

```bash
# Port-forward to access OpenSearch directly
kubectl port-forward -n production pod/opensearch-0 9200:9200 &

# Check cluster health
curl http://localhost:9200/_cluster/health | python3 -m json.tool
# Expected: {"status": "green", ...}

# List all indices
curl http://localhost:9200/_cat/indices?v
# Expected: shows arxiv-papers and arxiv-papers-chunks indices

# Stop port-forwarding when done
kill %1
```

### 13.7 Verify HPA is Working

```bash
# Install Metrics Server if not already done
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

# Wait 1 minute then check HPA
kubectl get hpa -n production

# Expected:
# NAME          REFERENCE           TARGETS          MINPODS   MAXPODS   REPLICAS
# rag-api-hpa   Deployment/rag-api  15%/70%, 30%/80%  2        6        2
```

### 13.8 Open UIs in Browser

- **OpenSearch Dashboards**: `http://$DASHBOARDS_URL:5601`
  - No login required (security disabled)
  - Explore arXiv paper indices in Discover tab

- **Airflow UI**: `http://$AIRFLOW_URL:8080`
  - Login: `admin` / `admin` (or whatever your `AIRFLOW_ADMIN_PASSWORD` is set to)
  - Find the `arxiv_paper_ingestion` DAG
  - Trigger it manually to ingest papers into OpenSearch

- **API Swagger Docs**: `http://$API_URL/docs`
  - Interactive API documentation
  - Try all endpoints directly from the browser

---

## 14. How CI/CD Works Going Forward

### CI Pipeline (Runs on Pull Requests)

When you open a PR targeting `main` or `aws`:

```
PR opened → GitHub Actions triggers ci.yml
  ├── Install Python 3.12 + uv
  ├── uv sync --frozen (install exact deps from uv.lock)
  ├── ruff check  (lint — fails PR if errors found)
  ├── ruff format (formatting — fails PR if not formatted)
  ├── mypy        (type check — informational, won't block PR)
  └── pytest      (tests — fails PR if any test fails)
```

If all checks pass → PR can be merged.

### CD Pipeline (Runs on Push to `deployment` Branch)

```
Push to deployment → GitHub Actions triggers cd.yml
  ├── Job 1: Build & Push
  │   ├── docker build rag-api → push to ECR with git SHA tag
  │   └── docker build rag-airflow → push to ECR
  └── Job 2: Deploy
      ├── kubectl apply namespace
      ├── kubectl create secret (from GitHub Secrets)
      ├── kubectl apply opensearch/ → wait for ready
      ├── kubectl apply dashboards/
      ├── kubectl create configmap airflow-dags
      ├── kubectl apply api/ (with new ECR image URI)
      ├── kubectl apply airflow/ (with new ECR image URI)
      ├── kubectl rollout status rag-api (wait until healthy)
      └── kubectl rollout status airflow (wait until healthy)
```

### Typical Development Workflow

```bash
# 1. Create a feature branch from aws
git checkout aws
git checkout -b feature/my-new-feature

# 2. Make changes to the code
# ... edit files ...

# 3. Open a Pull Request → CI runs automatically
git push origin feature/my-new-feature
# Open PR on GitHub → ci.yml runs lint + tests

# 4. Merge PR to aws branch after CI passes

# 5. When ready to deploy to production:
git checkout deployment
git merge aws
git push origin deployment
# → cd.yml triggers automatically → deploys to EKS
```

---

## 15. Cost Management

### Current Estimated Monthly Cost

| Resource | Cost/Month |
|----------|-----------|
| EKS Control Plane | $73 |
| 2× m5.xlarge nodes (24/7) | ~$280 |
| EBS gp2 volumes (OpenSearch PVC + nodes) | ~$5 |
| 3× Classic Load Balancers | ~$50 |
| ECR storage (images) | ~$2 |
| **Total (running 24/7)** | **~$410** |

### Save Money During Development

```bash
# Scale nodes to 0 when not using the cluster (stops EC2 billing)
# Note: pods will be evicted but PVCs (OpenSearch data) are preserved
eksctl scale nodegroup \
  --cluster agentic-rag-cluster \
  --region us-east-1 \
  --name rag-workers \
  --nodes 0

# Scale back up when needed (takes ~3 minutes for nodes to be ready)
eksctl scale nodegroup \
  --cluster agentic-rag-cluster \
  --region us-east-1 \
  --name rag-workers \
  --nodes 2
```

### Use Spot Instances for ~70% Savings

Edit `deployment/eks/cluster.yaml` — change `instanceType: m5.xlarge` to:
```yaml
instanceType: m5.xlarge
spot: true   # Add this line
```
Then update the node group (applies on next cluster creation).

---

## 16. Troubleshooting

### Pod is stuck in `Pending`

```bash
# Find which pod is stuck
kubectl get pods -n production

# Describe the pod to see why it's not scheduled
kubectl describe pod POD_NAME -n production

# Common causes:
# "Insufficient memory" — nodes don't have enough RAM
#   → Check: kubectl top nodes
#   → Fix: scale up node group or reduce resource requests

# "no persistent volumes available" — gp2 storage not available
#   → Check: kubectl get pvc -n production
#   → Fix: verify EBS StorageClass exists: kubectl get storageclass
```

### Pod is in `CrashLoopBackOff`

```bash
# View the crash logs
kubectl logs POD_NAME -n production --previous

# Common causes:
# "connection refused" to OpenSearch → OpenSearch not ready yet, wait 2 min
# "OPENSEARCH__HOST not set" → Secret not created or wrong key name
# "Bedrock credentials" error → Check BEDROCK__ values in Secret
```

### OpenSearch won't start

```bash
kubectl logs opensearch-0 -n production | tail -50

# Common cause: vm.max_map_count not set
# Should be fixed by the init container, but verify:
kubectl logs opensearch-0 -n production -c fix-kernel-settings

# If PVC is stuck in Pending:
kubectl describe pvc opensearch-data-opensearch-0 -n production
# Fix: ensure gp2 StorageClass exists
kubectl get storageclass
# If gp2 not listed: install EBS CSI driver
kubectl apply -k "github.com/kubernetes-sigs/aws-ebs-csi-driver/deploy/kubernetes/overlays/stable/?ref=master"
```

### GitHub Actions fails on `kubectl cluster-info`

```bash
# KUBE_CONFIG is wrong or expired
# Regenerate it:
aws eks update-kubeconfig --name agentic-rag-cluster --region us-east-1
cat ~/.kube/config | base64 | tr -d '\n'
# Paste the output into GitHub Secrets → KUBE_CONFIG
```

### GitHub Actions fails on ECR push

```bash
# The CI/CD IAM user doesn't have ECR permissions
# Verify the policy is attached:
aws iam list-attached-user-policies \
  --user-name github-actions-agentic-rag

# Should show: AgenticRAGCICDPolicy
```

### API returns 500 errors after deployment

```bash
# Check API logs
kubectl logs -n production -l app=rag-api --tail=100

# Common causes:
# "POSTGRES_DATABASE_URL" — Neon URL wrong or DB not accessible
# "OpenSearch index not found" — Need to trigger Airflow DAG to ingest papers
# "Bedrock model not found" — Check BEDROCK__MODEL_ID is the full ARN
```

### View all logs at once

```bash
# API logs (all replicas)
kubectl logs -n production -l app=rag-api --tail=50 --prefix=true

# OpenSearch logs
kubectl logs -n production opensearch-0 --tail=50

# Airflow logs
kubectl logs -n production -l app=airflow --tail=100

# Events (shows scheduling decisions, errors, warnings)
kubectl get events -n production --sort-by='.lastTimestamp' | tail -20
```

---

## 17. Full Teardown

**WARNING:** These commands delete all resources and your data. Irreversible.

```bash
# 1. Delete all K8s resources (keeps the cluster running)
kubectl delete namespace production

# 2. Delete the EKS cluster (deletes nodes, VPC, security groups)
# This takes ~10 minutes
eksctl delete cluster --name agentic-rag-cluster --region us-east-1

# 3. Delete ECR repositories and all images
aws ecr delete-repository \
  --repository-name agentic-rag/api \
  --force --region us-east-1

aws ecr delete-repository \
  --repository-name agentic-rag/airflow \
  --force --region us-east-1

# 4. Delete IAM resources
aws iam delete-access-key \
  --user-name github-actions-agentic-rag \
  --access-key-id YOUR_ACCESS_KEY_ID

aws iam detach-user-policy \
  --user-name github-actions-agentic-rag \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGCICDPolicy"

aws iam delete-policy \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGCICDPolicy"

aws iam delete-policy \
  --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGBedrockPolicy"

aws iam delete-user --user-name github-actions-agentic-rag

# 5. Delete Bedrock guardrail (optional)
aws bedrock delete-guardrail \
  --guardrail-identifier YOUR_GUARDRAIL_ID \
  --region us-east-1
```

---

## Quick Reference

### Most Used Commands

```bash
# Check pod status
kubectl get pods -n production

# View API logs (live)
kubectl logs -n production -l app=rag-api -f

# Get service URLs
kubectl get services -n production

# Restart API pods (rolling restart, zero downtime)
kubectl rollout restart deployment/rag-api -n production

# Scale API manually (HPA will still override this)
kubectl scale deployment/rag-api --replicas=3 -n production

# Execute a shell inside a running pod
kubectl exec -it PODNAME -n production -- /bin/bash

# Port-forward OpenSearch to localhost
kubectl port-forward -n production pod/opensearch-0 9200:9200

# View the Kubernetes Secret (base64-encoded values)
kubectl get secret rag-app-secrets -n production -o yaml

# Decode a specific secret value
kubectl get secret rag-app-secrets -n production \
  -o jsonpath='{.data.POSTGRES_DATABASE_URL}' | base64 -d

# Scale nodes to 0 (save money)
eksctl scale nodegroup --cluster agentic-rag-cluster --name rag-workers --nodes 0

# Scale nodes back
eksctl scale nodegroup --cluster agentic-rag-cluster --name rag-workers --nodes 2
```
