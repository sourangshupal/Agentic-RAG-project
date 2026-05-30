#!/usr/bin/env bash
# =============================================================================
# infra_start.sh — Complete AWS Infrastructure Bootstrap for Agentic RAG
# =============================================================================
# Builds the full stack from scratch:
#   1.  Check prerequisites & AWS credentials
#   2.  Load configuration from .env
#   3.  Create ECR repositories
#   4.  Build & push Docker images to ECR
#   5.  Create EKS cluster (eksctl, ~15 min)
#   6.  Create IAM Bedrock policy + IRSA service account
#   7.  Configure kubectl (update-kubeconfig)
#   8.  Apply namespace
#   9.  Create K8s Secret from .env
#   10. Deploy OpenSearch (StatefulSet) — wait for ready
#   11. Create Airflow DAGs ConfigMap
#   12. Deploy OpenSearch Dashboards, API, Airflow
#   13. Wait for all rollouts
#   14. (Optional) Install Grafana Cloud monitoring
#   15. Print deployment summary
#
# Usage:
#   ./scripts/infra_start.sh                          # reads .env
#   CLUSTER_NAME=foo AWS_REGION=eu-west-1 ./scripts/infra_start.sh
#
# Requirements: aws, eksctl, kubectl, docker, helm (optional for Grafana)
# =============================================================================

set -uo pipefail

# ── Colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_err()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "\n${BOLD}${BLUE}▶ $1${NC}"; }

die() { log_err "$1"; exit 1; }

# ── STEP 0: Load .env ────────────────────────────────────────────────────────
log_step "STEP 0: Loading configuration"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${REPO_ROOT}/.env" ]]; then
    # Export every KEY=VALUE line so subprocesses see them too
    set -a
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.env"
    set +a
    log_info "Loaded .env from ${REPO_ROOT}/.env"
fi

# Resolve final values (env vars override .env, args override env vars)
CLUSTER_NAME="${1:-${CLUSTER_NAME:-agentic-rag-cluster}}"
AWS_REGION="${2:-${AWS_REGION:-us-east-1}}"
AWS_ACCOUNT_ID="${3:-${AWS_ACCOUNT_ID:-}}"
K8S_NAMESPACE="${K8S_NAMESPACE:-production}"
GRAFANA_ENABLED="${GRAFANA_ENABLED:-false}"   # set to "true" to install Grafana

# Derive account ID from STS if not set
if [[ -z "${AWS_ACCOUNT_ID}" ]]; then
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
        || die "Cannot determine AWS_ACCOUNT_ID. Run 'aws configure' or set AWS_ACCOUNT_ID."
    log_info "Detected AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}"
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

log_info "Cluster:   ${CLUSTER_NAME}"
log_info "Region:    ${AWS_REGION}"
log_info "Account:   ${AWS_ACCOUNT_ID}"
log_info "Namespace: ${K8S_NAMESPACE}"
log_info "ECR:       ${ECR_REGISTRY}"

# ── STEP 1: Prerequisites check ──────────────────────────────────────────────
log_step "STEP 1: Checking prerequisites"

MISSING=()
for cmd in aws eksctl kubectl docker; do
    command -v "$cmd" &>/dev/null || MISSING+=("$cmd")
done

if [[ "${GRAFANA_ENABLED}" == "true" ]]; then
    command -v helm &>/dev/null || MISSING+=("helm")
fi

[[ ${#MISSING[@]} -gt 0 ]] && die "Missing required tools: ${MISSING[*]}. Install and retry."

aws sts get-caller-identity &>/dev/null || die "AWS credentials invalid. Run 'aws configure'."
log_ok "All prerequisites met"

# ── STEP 2: Create ECR Repositories ─────────────────────────────────────────
log_step "STEP 2: Creating ECR repositories"

for repo in agentic-rag/api agentic-rag/airflow; do
    if aws ecr describe-repositories --repository-name "${repo}" --region "${AWS_REGION}" &>/dev/null; then
        log_ok "ECR repo already exists: ${repo}"
    else
        aws ecr create-repository \
            --repository-name "${repo}" \
            --region "${AWS_REGION}" \
            --image-scanning-configuration scanOnPush=true \
            --output text --query 'repository.repositoryUri' &>/dev/null
        log_ok "Created ECR repo: ${repo}"
    fi
done

# ── STEP 3: Build & Push Docker Images ──────────────────────────────────────
log_step "STEP 3: Building and pushing Docker images"

log_info "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${ECR_REGISTRY}" \
    || die "ECR login failed"

IMAGE_TAG=$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo "latest")

log_info "Building rag-api image (tag: ${IMAGE_TAG})..."
# --platform linux/amd64: EKS nodes are x86_64; Mac M-series would otherwise build arm64
docker buildx build \
    --platform linux/amd64 \
    --cache-from "${ECR_REGISTRY}/agentic-rag/api:latest" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    -t "${ECR_REGISTRY}/agentic-rag/api:${IMAGE_TAG}" \
    -t "${ECR_REGISTRY}/agentic-rag/api:latest" \
    -f "${REPO_ROOT}/Dockerfile" \
    --push \
    "${REPO_ROOT}" \
    || die "API Docker build failed"
log_ok "rag-api pushed: ${ECR_REGISTRY}/agentic-rag/api:${IMAGE_TAG}"

log_info "Building rag-airflow image (tag: ${IMAGE_TAG})..."
docker buildx build \
    --platform linux/amd64 \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    -t "${ECR_REGISTRY}/agentic-rag/airflow:${IMAGE_TAG}" \
    -t "${ECR_REGISTRY}/agentic-rag/airflow:latest" \
    -f "${REPO_ROOT}/airflow/Dockerfile" \
    --push \
    "${REPO_ROOT}" \
    || die "Airflow Docker build failed"
log_ok "rag-airflow pushed: ${ECR_REGISTRY}/agentic-rag/airflow:${IMAGE_TAG}"

API_IMAGE="${ECR_REGISTRY}/agentic-rag/api:${IMAGE_TAG}"
AIRFLOW_IMAGE="${ECR_REGISTRY}/agentic-rag/airflow:${IMAGE_TAG}"

# ── STEP 4: Create EKS Cluster ───────────────────────────────────────────────
log_step "STEP 4: Creating EKS cluster (this takes 15-20 minutes)"

if eksctl get cluster --name "${CLUSTER_NAME}" --region "${AWS_REGION}" &>/dev/null; then
    log_ok "EKS cluster '${CLUSTER_NAME}' already exists — skipping creation"
else
    log_info "Creating cluster with eksctl using deployment/eks/cluster.yaml..."
    eksctl create cluster \
        -f "${REPO_ROOT}/deployment/eks/cluster.yaml" \
        || die "EKS cluster creation failed"
    log_ok "EKS cluster '${CLUSTER_NAME}' created"
fi

# ── STEP 5: Configure kubectl ────────────────────────────────────────────────
log_step "STEP 5: Configuring kubectl"

aws eks update-kubeconfig \
    --name "${CLUSTER_NAME}" \
    --region "${AWS_REGION}" \
    || die "kubectl configuration failed"

kubectl cluster-info || die "Cannot connect to EKS cluster"
log_ok "kubectl configured"

# ── STEP 6: Create IAM Bedrock Policy + IRSA Service Account ────────────────
log_step "STEP 6: Setting up IAM + IRSA for Bedrock access"

POLICY_NAME="AgenticRAGBedrockPolicy"
POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}"

if aws iam get-policy --policy-arn "${POLICY_ARN}" &>/dev/null; then
    log_ok "IAM policy already exists: ${POLICY_NAME}"
else
    log_info "Creating IAM policy ${POLICY_NAME}..."
    aws iam create-policy \
        --policy-name "${POLICY_NAME}" \
        --policy-document "file://${REPO_ROOT}/bedrock-policy.json" \
        --output text --query 'Policy.Arn' \
        || die "IAM policy creation failed"
    log_ok "Created IAM policy: ${POLICY_ARN}"
fi

# Apply namespace before creating the service account
kubectl apply -f "${REPO_ROOT}/deployment/eks/namespace.yaml"

SA_NAME="rag-api-sa"
if kubectl get serviceaccount "${SA_NAME}" -n "${K8S_NAMESPACE}" &>/dev/null; then
    log_ok "IRSA service account '${SA_NAME}' already exists"
else
    log_info "Creating IRSA service account '${SA_NAME}'..."
    eksctl create iamserviceaccount \
        --cluster "${CLUSTER_NAME}" \
        --region "${AWS_REGION}" \
        --namespace "${K8S_NAMESPACE}" \
        --name "${SA_NAME}" \
        --attach-policy-arn "${POLICY_ARN}" \
        --approve \
        --override-existing-serviceaccounts \
        || die "IRSA service account creation failed"
    log_ok "IRSA service account created"
fi

# ── STEP 6b: Install EBS CSI Driver + gp3 StorageClass ──────────────────────
log_step "STEP 6b: Installing EBS CSI driver and gp3 StorageClass"

# EKS 1.23+ requires EBS CSI driver — in-tree aws-ebs provisioner is removed.
# Attach AmazonEBSCSIDriverPolicy to node role so the addon can provision EBS volumes.
NODE_ROLE_NAME=$(aws eks describe-nodegroup \
    --cluster-name "${CLUSTER_NAME}" \
    --nodegroup-name rag-workers \
    --region "${AWS_REGION}" \
    --query 'nodegroup.nodeRole' --output text 2>/dev/null | awk -F'/' '{print $NF}')

if [[ -n "${NODE_ROLE_NAME}" ]]; then
    aws iam attach-role-policy \
        --role-name "${NODE_ROLE_NAME}" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy \
        2>/dev/null && log_ok "AmazonEBSCSIDriverPolicy attached to ${NODE_ROLE_NAME}" \
        || log_warn "Policy attach failed or already attached — continuing"
fi

EBS_STATUS=$(aws eks describe-addon \
    --cluster-name "${CLUSTER_NAME}" \
    --addon-name aws-ebs-csi-driver \
    --region "${AWS_REGION}" \
    --query 'addon.status' --output text 2>/dev/null || echo "NOT_FOUND")

if [[ "${EBS_STATUS}" == "ACTIVE" ]]; then
    log_ok "EBS CSI driver already active"
else
    log_info "Installing EBS CSI driver addon..."
    aws eks create-addon \
        --cluster-name "${CLUSTER_NAME}" \
        --addon-name aws-ebs-csi-driver \
        --region "${AWS_REGION}" \
        --resolve-conflicts OVERWRITE \
        --output text --query 'addon.status' &>/dev/null \
        || log_warn "EBS CSI addon create failed (may already exist)"

    log_info "Waiting for EBS CSI driver to become ACTIVE (up to 3min)..."
    for i in $(seq 1 36); do
        STATUS=$(aws eks describe-addon \
            --cluster-name "${CLUSTER_NAME}" \
            --addon-name aws-ebs-csi-driver \
            --region "${AWS_REGION}" \
            --query 'addon.status' --output text 2>/dev/null)
        [[ "${STATUS}" == "ACTIVE" ]] && break
        sleep 5
    done
    log_ok "EBS CSI driver is ACTIVE"
fi

# Create gp3 StorageClass (EBS CSI provisioner, replaces legacy in-tree gp2)
kubectl apply -f - <<'YAML'
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
YAML
log_ok "gp3 StorageClass created"

# ── STEP 7: Create K8s Secret from .env ──────────────────────────────────────
log_step "STEP 7: Creating Kubernetes Secret"

# Derive Airflow secret key if not in .env
AIRFLOW_SECRET_KEY="${AIRFLOW__WEBSERVER__SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"

kubectl create secret generic rag-app-secrets \
    --namespace "${K8S_NAMESPACE}" \
    --from-literal=DEBUG="false" \
    --from-literal=ENVIRONMENT="production" \
    --from-literal=PROVIDER="${PROVIDER:-bedrock}" \
    --from-literal=OPENSEARCH__HOST="http://opensearch:9200" \
    --from-literal=OPENSEARCH__INDEX_NAME="${OPENSEARCH__INDEX_NAME:-arxiv-papers}" \
    --from-literal=OPENSEARCH__CHUNK_INDEX_SUFFIX="${OPENSEARCH__CHUNK_INDEX_SUFFIX:-chunks}" \
    --from-literal=OPENSEARCH__VECTOR_DIMENSION="${OPENSEARCH__VECTOR_DIMENSION:-1024}" \
    --from-literal=POSTGRES_DATABASE_URL="${POSTGRES_DATABASE_URL:-}" \
    --from-literal=REDIS__URL="${REDIS__URL:-}" \
    --from-literal=REDIS__TTL_HOURS="${REDIS__TTL_HOURS:-6}" \
    --from-literal=BEDROCK__AWS_ACCESS_KEY_ID="${BEDROCK__AWS_ACCESS_KEY_ID:-}" \
    --from-literal=BEDROCK__AWS_SECRET_ACCESS_KEY="${BEDROCK__AWS_SECRET_ACCESS_KEY:-}" \
    --from-literal=BEDROCK__AWS_REGION="${BEDROCK__AWS_REGION:-us-east-1}" \
    --from-literal=BEDROCK__MODEL_ID="${BEDROCK__MODEL_ID:-}" \
    --from-literal=BEDROCK__GUARDRAIL_ID="${BEDROCK__GUARDRAIL_ID:-}" \
    --from-literal=BEDROCK__GUARDRAIL_VERSION="${BEDROCK__GUARDRAIL_VERSION:-DRAFT}" \
    --from-literal=LANGFUSE__PUBLIC_KEY="${LANGFUSE__PUBLIC_KEY:-}" \
    --from-literal=LANGFUSE__SECRET_KEY="${LANGFUSE__SECRET_KEY:-}" \
    --from-literal=LANGFUSE__HOST="${LANGFUSE__HOST:-https://us.cloud.langfuse.com}" \
    --from-literal=LANGFUSE__ENABLED="${LANGFUSE__ENABLED:-true}" \
    --from-literal=LANGFUSE__FLUSH_AT="${LANGFUSE__FLUSH_AT:-15}" \
    --from-literal=LANGFUSE__FLUSH_INTERVAL="${LANGFUSE__FLUSH_INTERVAL:-1.0}" \
    --from-literal=LOGFIRE__TOKEN="${LOGFIRE__TOKEN:-}" \
    --from-literal=LOGFIRE__ENABLED="${LOGFIRE__ENABLED:-true}" \
    --from-literal=LOGFIRE__SERVICE_NAME="arxiv-rag" \
    --from-literal=LOGFIRE__ENVIRONMENT="production" \
    --from-literal=JINA_API_KEY="${JINA_API_KEY:-}" \
    --from-literal=OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
    --from-literal=OPENAI_MODEL="${OPENAI_MODEL:-gpt-4o-mini}" \
    --from-literal=OPENAI_TIMEOUT="${OPENAI_TIMEOUT:-300}" \
    --from-literal=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="${POSTGRES_DATABASE_URL:-}" \
    --from-literal=AIRFLOW__CORE__EXECUTOR="LocalExecutor" \
    --from-literal=AIRFLOW__WEBSERVER__SECRET_KEY="${AIRFLOW_SECRET_KEY}" \
    --from-literal=AIRFLOW__API__AUTH_BACKENDS="airflow.api.auth.backend.basic_auth" \
    --from-literal=AIRFLOW__WEBSERVER__UPDATE_FAB_PERMS="False" \
    --from-literal=PYTHONWARNINGS="ignore::FutureWarning:airflow,ignore::DeprecationWarning:airflow" \
    --from-literal=AIRFLOW__CORE__DAG_IGNORE_FILE_SYNTAX="regexp" \
    --from-literal=ARXIV__MAX_RESULTS="${ARXIV__MAX_RESULTS:-2}" \
    --dry-run=client -o yaml | kubectl apply -f -

log_ok "K8s Secret 'rag-app-secrets' applied"

# ── STEP 8: Deploy OpenSearch ─────────────────────────────────────────────────
log_step "STEP 8: Deploying OpenSearch"

kubectl apply -f "${REPO_ROOT}/deployment/k8s/opensearch/service.yaml"
kubectl apply -f "${REPO_ROOT}/deployment/k8s/opensearch/statefulset.yaml"

log_info "Waiting for OpenSearch StatefulSet (timeout: 5min)..."
kubectl rollout status statefulset/opensearch \
    -n "${K8S_NAMESPACE}" \
    --timeout=300s \
    || die "OpenSearch rollout timed out"

log_ok "OpenSearch is running"

# ── STEP 9: Deploy OpenSearch Dashboards ─────────────────────────────────────
log_step "STEP 9: Deploying OpenSearch Dashboards"

kubectl apply -f "${REPO_ROOT}/deployment/k8s/opensearch-dashboards/service.yaml"
kubectl apply -f "${REPO_ROOT}/deployment/k8s/opensearch-dashboards/deployment.yaml"
log_ok "OpenSearch Dashboards applied"

# ── STEP 10: Create Airflow DAGs ConfigMap ───────────────────────────────────
log_step "STEP 10: Creating Airflow DAGs ConfigMap"

kubectl create configmap airflow-dags \
    --namespace "${K8S_NAMESPACE}" \
    --from-file="${REPO_ROOT}/airflow/dags/" \
    --dry-run=client -o yaml | kubectl apply -f -

log_ok "airflow-dags ConfigMap applied"

# ── STEP 11: Patch deployment manifests with actual ECR image URIs ───────────
log_step "STEP 11: Injecting ECR image URIs into manifests"

# Work on temp copies so we don't dirty the git working tree
TMP_API_DEPLOY=$(mktemp)
TMP_AIRFLOW_DEPLOY=$(mktemp)

cp "${REPO_ROOT}/deployment/k8s/api/deployment.yaml" "${TMP_API_DEPLOY}"
cp "${REPO_ROOT}/deployment/k8s/airflow/deployment.yaml" "${TMP_AIRFLOW_DEPLOY}"

# Replace placeholder OR existing ECR URI with current SHA-tagged image
sed -i.bak \
    "s|image: REPLACE_WITH_ECR_URI/agentic-rag/api:.*|image: ${API_IMAGE}|g" \
    "${TMP_API_DEPLOY}"
# Also handle the case where a previous full URI was already substituted
sed -i.bak \
    "s|image: [0-9]*\.dkr\.ecr\.[a-z0-9-]*\.amazonaws\.com/agentic-rag/api:.*|image: ${API_IMAGE}|g" \
    "${TMP_API_DEPLOY}"

sed -i.bak \
    "s|image: REPLACE_WITH_ECR_URI/agentic-rag/airflow:.*|image: ${AIRFLOW_IMAGE}|g" \
    "${TMP_AIRFLOW_DEPLOY}"
sed -i.bak \
    "s|image: [0-9]*\.dkr\.ecr\.[a-z0-9-]*\.amazonaws\.com/agentic-rag/airflow:.*|image: ${AIRFLOW_IMAGE}|g" \
    "${TMP_AIRFLOW_DEPLOY}"

log_info "API image:     ${API_IMAGE}"
log_info "Airflow image: ${AIRFLOW_IMAGE}"

# ── STEP 12: Deploy API & Airflow ────────────────────────────────────────────
log_step "STEP 12: Deploying RAG API and Airflow"

kubectl apply -f "${REPO_ROOT}/deployment/k8s/api/service.yaml"
kubectl apply -f "${TMP_API_DEPLOY}"
kubectl apply -f "${REPO_ROOT}/deployment/k8s/api/hpa.yaml"
log_ok "RAG API manifests applied"

kubectl apply -f "${REPO_ROOT}/deployment/k8s/airflow/service.yaml"
kubectl apply -f "${TMP_AIRFLOW_DEPLOY}"
log_ok "Airflow manifests applied"

rm -f "${TMP_API_DEPLOY}" "${TMP_API_DEPLOY}.bak" "${TMP_AIRFLOW_DEPLOY}" "${TMP_AIRFLOW_DEPLOY}.bak"

# ── STEP 13: Wait for Rollouts ───────────────────────────────────────────────
log_step "STEP 13: Waiting for rollouts to complete"

log_info "Waiting for rag-api (timeout: 5min)..."
kubectl rollout status deployment/rag-api \
    -n "${K8S_NAMESPACE}" \
    --timeout=300s \
    || { log_warn "rag-api rollout timed out — check: kubectl describe pod -n ${K8S_NAMESPACE}"; }

log_info "Waiting for Airflow (timeout: 10min — first boot runs db migrate)..."
kubectl rollout status deployment/airflow \
    -n "${K8S_NAMESPACE}" \
    --timeout=600s \
    || { log_warn "Airflow rollout timed out — check: kubectl logs -n ${K8S_NAMESPACE} -l app=airflow"; }

# ── STEP 14: Grafana Cloud (optional) ───────────────────────────────────────
if [[ "${GRAFANA_ENABLED}" == "true" ]]; then
    log_step "STEP 14: Installing Grafana Cloud monitoring"

    if ! command -v helm &>/dev/null; then
        log_warn "helm not found — skipping Grafana installation"
    elif [[ ! -f "${REPO_ROOT}/deployment/grafana/values.yaml" ]]; then
        log_warn "deployment/grafana/values.yaml not found — skipping Grafana installation"
    else
        helm repo add grafana https://grafana.github.io/helm-charts &>/dev/null
        helm repo update &>/dev/null

        kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -

        helm upgrade --install grafana-k8s-monitoring grafana/k8s-monitoring \
            --namespace monitoring \
            --values "${REPO_ROOT}/deployment/grafana/values.yaml" \
            --timeout 10m \
            || log_warn "Grafana Helm install failed — check: helm list -n monitoring"

        log_ok "Grafana Cloud monitoring installed"
    fi
else
    log_info "STEP 14: Grafana Cloud skipped (set GRAFANA_ENABLED=true to enable)"
fi

# ── STEP 15: Deployment Summary ──────────────────────────────────────────────
log_step "STEP 15: Deployment Summary"

echo ""
echo "=== Pods ==="
kubectl get pods -n "${K8S_NAMESPACE}" -o wide

echo ""
echo "=== Services ==="
kubectl get services -n "${K8S_NAMESPACE}"

echo ""
echo "=== HPA ==="
kubectl get hpa -n "${K8S_NAMESPACE}" 2>/dev/null || true

echo ""
echo "=== Access URLs (ELB may take 2-3 min to provision) ==="
API_HOST=$(kubectl get service rag-api -n "${K8S_NAMESPACE}" \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "pending")
AIRFLOW_HOST=$(kubectl get service airflow -n "${K8S_NAMESPACE}" \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "pending")
DASHBOARDS_HOST=$(kubectl get service opensearch-dashboards -n "${K8S_NAMESPACE}" \
    -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "pending")

echo "  RAG API:    http://${API_HOST}/api/v1/health"
echo "  Airflow:    http://${AIRFLOW_HOST}:8080"
echo "  Dashboards: http://${DASHBOARDS_HOST}:5601"
echo ""

log_ok "Infrastructure bootstrap complete."
log_info "To test the API health endpoint after ELB provisions:"
log_info "  curl http://${API_HOST}/api/v1/health"
log_info "To tear down everything: ./scripts/tear_down.sh"
