#!/usr/bin/env bash
# =============================================================================
# tear_down.sh — Battle-Tested AWS Infrastructure Teardown
# =============================================================================
# Destroys every AWS resource created by the Agentic RAG project.
# Designed to be idempotent, fault-tolerant, and exhaustively thorough.
#
# Usage:
#   ./scripts/tear_down.sh
#
# Configuration (pick ONE method):
#   1. Export env vars before running:
#        export CLUSTER_NAME=agentic-rag-cluster
#        export AWS_REGION=us-east-1
#        export AWS_ACCOUNT_ID=123456789012
#   2. Create a .env file in the repo root (git-ignored):
#        CLUSTER_NAME=agentic-rag-cluster
#        AWS_REGION=us-east-1
#        AWS_ACCOUNT_ID=123456789012
#   3. Pass as arguments:
#        ./scripts/tear_down.sh my-cluster us-west-2 123456789012
#
# NO sensitive values are hard-coded in this script.
# =============================================================================

set -uo pipefail
# NOTE: We deliberately do NOT use `set -e` so that one failed deletion does
#       not abort the entire teardown. Every destructive command is wrapped
#       in its own error-handling block.

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

# ── Configuration ───────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load .env with export so subprocesses see vars too
if [[ -f "${REPO_ROOT}/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${REPO_ROOT}/.env"
    set +a
    log_info "Loaded configuration from ${REPO_ROOT}/.env"
fi

# Allow overrides via command-line arguments
CLUSTER_NAME="${1:-${CLUSTER_NAME:-agentic-rag-cluster}}"
AWS_REGION="${2:-${AWS_REGION:-us-east-1}}"
AWS_ACCOUNT_ID="${3:-${AWS_ACCOUNT_ID:-}}"
K8S_NAMESPACE="${K8S_NAMESPACE:-production}"

# Derive account ID from STS if not set
if [[ -z "${AWS_ACCOUNT_ID}" ]]; then
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
        || die "Cannot determine AWS_ACCOUNT_ID. Run 'aws configure' or set AWS_ACCOUNT_ID."
    log_info "Detected AWS_ACCOUNT_ID=${AWS_ACCOUNT_ID}"
fi

ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ── Prerequisites check ─────────────────────────────────────────────────────
log_step "STEP 0: Checking prerequisites"

MISSING=()
for cmd in aws eksctl kubectl helm; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING+=("$cmd")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    log_warn "Missing CLI tools: ${MISSING[*]}"
    log_warn "Some teardown steps may fail. Install missing tools and retry."
fi

if ! aws sts get-caller-identity &>/dev/null; then
    die "AWS credentials not configured or invalid. Run 'aws configure' or export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY"
fi
log_ok "AWS credentials valid"

log_info "Target:    CLUSTER_NAME=${CLUSTER_NAME}, REGION=${AWS_REGION}, ACCOUNT=${AWS_ACCOUNT_ID}"

# ── Helper: wait for a condition with timeout ─────────────────────────────
wait_for() {
    local description="$1"
    local check_cmd="$2"
    local timeout="${3:-300}"
    local interval="${4:-5}"
    local elapsed=0

    log_info "Waiting for: $description (timeout: ${timeout}s)"
    while ! eval "$check_cmd" >/dev/null 2>&1; do
        sleep "$interval"
        elapsed=$((elapsed + interval))
        if [[ $elapsed -ge $timeout ]]; then
            log_warn "Timeout waiting for: $description"
            return 1
        fi
    done
    log_ok "$description"
    return 0
}

# ── Helper: run a command, swallow errors, log what happened ────────────────
run_step() {
    local description="$1"
    local cmd="$2"
    log_info "$description"
    if eval "$cmd" >/dev/null 2>&1; then
        log_ok "$description — done"
        return 0
    else
        log_warn "$description — FAILED or resource not found"
        return 1
    fi
}

# ── Helper: confirm user wants to proceed ────────────────────────────────
confirm_destruction() {
    log_warn "╔══════════════════════════════════════════════════════════════════╗"
    log_warn "║  DESTRUCTIVE ACTION WARNING                                    ║"
    log_warn "║  This will permanently delete ALL AWS resources for:             ║"
    log_warn "║    Cluster:  ${CLUSTER_NAME}                                    ║"
    log_warn "║    Region:   ${AWS_REGION}                                      ║"
    log_warn "║    Account:  ${AWS_ACCOUNT_ID}                                  ║"
    log_warn "║                                                                  ║"
    log_warn "║  Resources to be destroyed:                                      ║"
    log_warn "║    - Helm releases (Grafana monitoring)                        ║"
    log_warn "║    - Kubernetes namespace '${K8S_NAMESPACE}' + 'monitoring'       ║"
    log_warn "║    - LoadBalancer Services (3 Classic ELBs)                    ║"
    log_warn "║    - EBS volumes from OpenSearch PVC                           ║"
    log_warn "║    - EKS cluster, node group, VPC, NAT gateway                 ║"
    log_warn "║    - IAM policy + IRSA service account                       ║"
    log_warn "║    - ECR repositories (api + airflow)                          ║"
    log_warn "║    - Leftover CloudFormation stacks                            ║"
    log_warn "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    read -r -p "Type the cluster name to confirm destruction: [${CLUSTER_NAME}] " confirm
    confirm="${confirm:-${CLUSTER_NAME}}"
    if [[ "$confirm" != "$CLUSTER_NAME" ]]; then
        die "Confirmation mismatch. Aborting."
    fi
    log_ok "Confirmation received. Beginning teardown..."
}

# ── STEP 1: Helm releases (Grafana Cloud monitoring) ──────────────────────
log_step "STEP 1/13: Uninstalling Helm releases"

run_step "Helm: uninstall alloy-logs" \
    "helm uninstall grafana-k8s-monitoring-alloy-logs -n monitoring 2>/dev/null"

run_step "Helm: uninstall alloy-metrics" \
    "helm uninstall grafana-k8s-monitoring-alloy-metrics -n monitoring 2>/dev/null"

run_step "Helm: uninstall alloy-singleton" \
    "helm uninstall grafana-k8s-monitoring-alloy-singleton -n monitoring 2>/dev/null"

run_step "Helm: uninstall grafana-k8s-monitoring" \
    "helm uninstall grafana-k8s-monitoring -n monitoring 2>/dev/null"

# ── STEP 2: Configure kubectl (if cluster still exists) ─────────────────────
log_step "STEP 2/13: Configuring kubectl context"

if eksctl get cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null; then
    aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null || true
    log_ok "kubectl context updated for ${CLUSTER_NAME}"
else
    log_warn "Cluster '${CLUSTER_NAME}' not found — kubectl steps will be skipped"
fi

# ── STEP 3: Scale down deployments to speed up deletion ─────────────────────
log_step "STEP 3/13: Scaling down all deployments"

if kubectl get namespace "$K8S_NAMESPACE" &>/dev/null; then
    log_info "Scaling deployments to 0 in namespace ${K8S_NAMESPACE}..."
    kubectl scale deployment --all --replicas=0 -n "$K8S_NAMESPACE" 2>/dev/null || true
    kubectl scale statefulset --all --replicas=0 -n "$K8S_NAMESPACE" 2>/dev/null || true
    sleep 5
    log_ok "All workloads scaled to 0"
else
    log_warn "Namespace '${K8S_NAMESPACE}' not found — skipping scale-down"
fi

# ── STEP 4: Delete LoadBalancer Services explicitly ─────────────────────────
# This ensures AWS Classic ELBs are properly de-registered and deleted
# BEFORE we delete the namespace. If we delete the namespace first,
# sometimes the ELB deletion event never reaches AWS, leaving orphaned LBs.
# ────────────────────────────────────────────────────────────────────────────
log_step "STEP 4/13: Deleting LoadBalancer Services (triggers ELB deletion)"

LB_SERVICES=("rag-api" "airflow" "opensearch-dashboards")
for svc in "${LB_SERVICES[@]}"; do
    if kubectl get service "$svc" -n "$K8S_NAMESPACE" &>/dev/null; then
        log_info "Deleting Service/${svc} — AWS will deprovision its Classic ELB..."
        kubectl delete service "$svc" -n "$K8S_NAMESPACE" --grace-period=0 --force 2>/dev/null || true
        log_ok "Service/${svc} deleted"
    else
        log_warn "Service/${svc} not found — skipping"
    fi
done

# Wait for AWS to finish deleting the ELBs (usually 30-60s)
log_info "Waiting 60s for AWS ELB deprovisioning..."
sleep 60

# ── STEP 5: Delete remaining K8s resources in production namespace ────────────
log_step "STEP 5/13: Deleting remaining Kubernetes resources"

if kubectl get namespace "$K8S_NAMESPACE" &>/dev/null; then
    # Delete HPA, ConfigMaps, Secrets explicitly so they don't block namespace
    run_step "K8s: delete HPA rag-api" \
        "kubectl delete hpa rag-api -n ${K8S_NAMESPACE} --ignore-not-found=true 2>/dev/null"

    run_step "K8s: delete ConfigMap airflow-dags" \
        "kubectl delete configmap airflow-dags -n ${K8S_NAMESPACE} --ignore-not-found=true 2>/dev/null"

    run_step "K8s: delete Secret rag-app-secrets" \
        "kubectl delete secret rag-app-secrets -n ${K8S_NAMESPACE} --ignore-not-found=true 2>/dev/null"

    # Delete Deployments
    run_step "K8s: delete Deployments" \
        "kubectl delete deployment --all -n ${K8S_NAMESPACE} --ignore-not-found=true --grace-period=0 --force 2>/dev/null"

    # Delete StatefulSet
    run_step "K8s: delete StatefulSet opensearch" \
        "kubectl delete statefulset opensearch -n ${K8S_NAMESPACE} --ignore-not-found=true --grace-period=0 --force 2>/dev/null"

    # Delete remaining Services (ClusterIP types)
    run_step "K8s: delete remaining Services" \
        "kubectl delete service --all -n ${K8S_NAMESPACE} --ignore-not-found=true --grace-period=0 --force 2>/dev/null"
else
    log_warn "Namespace '${K8S_NAMESPACE}' not found — skipping resource deletion"
fi

# ── STEP 6: Delete PVCs explicitly (releases EBS volumes) ───────────────────
log_step "STEP 6/13: Deleting Persistent Volume Claims (releases EBS volumes)"

if kubectl get namespace "$K8S_NAMESPACE" &>/dev/null; then
    PVC_LIST=$(kubectl get pvc -n "$K8S_NAMESPACE" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
    if [[ -n "$PVC_LIST" ]]; then
        log_info "PVCs found: $PVC_LIST"
        for pvc in $PVC_LIST; do
            run_step "K8s: delete PVC ${pvc}" \
                "kubectl delete pvc ${pvc} -n ${K8S_NAMESPACE} --grace-period=0 --force 2>/dev/null"
        done
        # Wait for PVCs to actually disappear
        wait_for "all PVCs deleted in ${K8S_NAMESPACE}" \
            "test -z \"\$(kubectl get pvc -n ${K8S_NAMESPACE} -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)\"" 120 5
    else
        log_ok "No PVCs found in ${K8S_NAMESPACE}"
    fi
else
    log_warn "Namespace '${K8S_NAMESPACE}' not found — skipping PVC deletion"
fi

# ── STEP 7: Delete Kubernetes namespaces ────────────────────────────────────
log_step "STEP 7/13: Deleting Kubernetes namespaces"

for ns in "$K8S_NAMESPACE" "monitoring"; do
    if kubectl get namespace "$ns" &>/dev/null; then
        log_info "Deleting namespace ${ns}..."
        kubectl delete namespace "$ns" --ignore-not-found=true --grace-period=0 --force 2>/dev/null || true
        # Wait for namespace to disappear
        wait_for "namespace ${ns} deleted" "! kubectl get namespace ${ns} &>/dev/null" 120 5 || {
            log_warn "Namespace ${ns} still terminating — may need manual cleanup"
        }
    else
        log_ok "Namespace '${ns}' not found — skipping"
    fi
done

# ── STEP 8: Delete EBS CSI driver addon ─────────────────────────────────────
log_step "STEP 8/13: Deleting EBS CSI driver addon"

if eksctl get cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null; then
    EBS_STATUS=$(aws eks describe-addon \
        --cluster-name "$CLUSTER_NAME" \
        --addon-name aws-ebs-csi-driver \
        --region "$AWS_REGION" \
        --query 'addon.status' --output text 2>/dev/null || echo "NOT_FOUND")

    if [[ "$EBS_STATUS" != "NOT_FOUND" && "$EBS_STATUS" != "None" ]]; then
        log_info "Deleting EBS CSI driver addon..."
        aws eks delete-addon \
            --cluster-name "$CLUSTER_NAME" \
            --addon-name aws-ebs-csi-driver \
            --region "$AWS_REGION" 2>/dev/null || true

        wait_for "EBS CSI addon deleted" \
            "aws eks describe-addon --cluster-name ${CLUSTER_NAME} --addon-name aws-ebs-csi-driver --region ${AWS_REGION} &>/dev/null; test \$? -ne 0" 180 10 || {
            log_warn "EBS CSI addon deletion may still be in progress"
        }
    else
        log_ok "EBS CSI driver addon not found — skipping"
    fi
else
    log_warn "Cluster not found — skipping EBS CSI addon deletion"
fi

# ── STEP 9: Delete IRSA service account ─────────────────────────────────────
log_step "STEP 9/13: Deleting IRSA service account"

if eksctl get cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null; then
    SA_NAME="rag-api-sa"
    if eksctl get iamserviceaccount --cluster "$CLUSTER_NAME" --region "$AWS_REGION" -n "$K8S_NAMESPACE" 2>/dev/null | grep -q "$SA_NAME"; then
        log_info "Deleting IRSA service account ${SA_NAME}..."
        eksctl delete iamserviceaccount \
            --cluster "$CLUSTER_NAME" \
            --region "$AWS_REGION" \
            --namespace "$K8S_NAMESPACE" \
            --name "$SA_NAME" \
            --wait 2>/dev/null || true
        log_ok "IRSA service account deletion initiated"
    else
        log_ok "IRSA service account '${SA_NAME}' not found — skipping"
    fi
else
    log_warn "Cluster not found — skipping IRSA deletion"
fi

# ── STEP 10: Delete IAM policy (after detaching from any roles) ────────────
log_step "STEP 10/13: Deleting IAM policy"

POLICY_NAME="AgenticRAGBedrockPolicy"
POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}"

if aws iam get-policy --policy-arn "$POLICY_ARN" &>/dev/null; then
    log_info "Detaching policy from all roles..."
    # Find all roles with this policy attached and detach
    aws iam list-entities-for-policy \
        --policy-arn "$POLICY_ARN" \
        --entity-filter Role \
        --query 'PolicyRoles[*].RoleName' --output text 2>/dev/null | tr '\t' '\n' | while read -r role; do
        if [[ -n "$role" && "$role" != "None" ]]; then
            log_info "  Detaching ${POLICY_NAME} from role ${role}..."
            aws iam detach-role-policy \
                --role-name "$role" \
                --policy-arn "$POLICY_ARN" 2>/dev/null || true
        fi
    done

    log_info "Deleting policy versions..."
    aws iam list-policy-versions \
        --policy-arn "$POLICY_ARN" \
        --query 'Versions[?IsDefaultVersion==`false`].VersionId' \
        --output text 2>/dev/null | tr '\t' '\n' | while read -r version; do
        if [[ -n "$version" && "$version" != "None" ]]; then
            aws iam delete-policy-version \
                --policy-arn "$POLICY_ARN" \
                --version-id "$version" 2>/dev/null || true
        fi
    done

    log_info "Deleting IAM policy ${POLICY_NAME}..."
    aws iam delete-policy --policy-arn "$POLICY_ARN" 2>/dev/null || true
    log_ok "IAM policy deleted (or was already gone)"
else
    log_ok "IAM policy '${POLICY_NAME}' not found — skipping"
fi

# ── STEP 11: Delete EKS Cluster ─────────────────────────────────────────────
log_step "STEP 11/13: Deleting EKS cluster '${CLUSTER_NAME}'"

if eksctl get cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null; then
    log_info "Cluster found. Starting deletion (this takes 15–20 min)..."
    log_info "  eksctl will delete: control plane, node group, VPC, subnets, NAT gateway,"
    log_info "                     security groups, IAM roles, CloudWatch log groups"
    if eksctl delete cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" --wait 2>&1 | tail -50; then
        log_ok "EKS cluster '${CLUSTER_NAME}' fully deleted"
    else
        log_warn "EKS cluster deletion reported issues (may still be in progress)"
        log_warn "       → Run manually: eksctl delete cluster --name ${CLUSTER_NAME} --region ${AWS_REGION} --force"
    fi
else
    log_ok "EKS cluster '${CLUSTER_NAME}' not found — skipping"
fi

# ── STEP 12: Delete ECR Repositories ────────────────────────────────────────
log_step "STEP 12/13: Deleting ECR repositories"

for repo in agentic-rag/api agentic-rag/airflow; do
    if aws ecr describe-repositories --repository-name "$repo" --region "$AWS_REGION" &>/dev/null; then
        log_info "Deleting ECR repository ${repo}..."
        aws ecr delete-repository --repository-name "$repo" --region "$AWS_REGION" --force 2>/dev/null || true
        log_ok "ECR repo '${repo}' deleted"
    else
        log_ok "ECR repo '${repo}' not found — skipping"
    fi
done

# ── STEP 13: Clean up orphaned AWS resources (safety net) ───────────────────
log_step "STEP 13/13: Cleaning up orphaned AWS resources"

# --- 13a: Classic ELBs (targeted by the known service names) ---
log_info "Checking for orphaned Classic ELBs..."
ELB_NAMES=$(aws elb describe-load-balancers --region "$AWS_REGION" \
    --query 'LoadBalancerDescriptions[*].LoadBalancerName' --output text 2>/dev/null | tr '\t' '\n')

ORPHANED_ELBS=()
for elb in $ELB_NAMES; do
    # Check if ELB tags contain our cluster name (safer than name matching)
    TAGS=$(aws elb describe-tags --region "$AWS_REGION" \
        --load-balancer-name "$elb" \
        --query 'TagDescriptions[*].Tags[*].[Key,Value]' --output text 2>/dev/null | tr '\n' ' ')
    if echo "$TAGS" | grep -qiE "(kubernetes\.io/cluster/${CLUSTER_NAME}|agentic-rag)" 2>/dev/null; then
        ORPHANED_ELBS+=("$elb")
    fi
done

if [[ ${#ORPHANED_ELBS[@]} -gt 0 ]]; then
    for elb in "${ORPHANED_ELBS[@]}"; do
        log_warn "Orphaned ELB tagged for our cluster: $elb — deleting..."
        aws elb delete-load-balancer --load-balancer-name "$elb" --region "$AWS_REGION" 2>/dev/null || true
    done
else
    log_ok "No orphaned Classic ELBs tagged for ${CLUSTER_NAME}"
fi

# --- 13b: ALB/NLB (ELBv2) ---
ALBS=$(aws elbv2 describe-load-balancers --region "$AWS_REGION" \
    --query 'LoadBalancers[*].LoadBalancerArn' --output text 2>/dev/null | tr '\t' '\n')
if [[ -n "$ALBS" ]]; then
    log_warn "ALB/NLB resources still exist (usually auto-deleted with cluster)."
    log_warn "       → Verify in AWS Console → EC2 → Load Balancers"
else
    log_ok "No ALB/NLB resources found"
fi

# --- 13c: EBS Volumes (orphaned after PVC deletion) ---
log_info "Checking for orphaned EBS volumes..."
EBS_VOLUMES=$(aws ec2 describe-volumes --region "$AWS_REGION" \
    --filters "Name=tag:kubernetes.io/cluster/${CLUSTER_NAME},Values=owned" \
    --query 'Volumes[*].VolumeId' --output text 2>/dev/null | tr '\t' '\n')

if [[ -n "$EBS_VOLUMES" ]]; then
    for vol in $EBS_VOLUMES; do
        log_warn "Orphaned EBS volume ${vol} — deleting..."
        aws ec2 delete-volume --volume-id "$vol" --region "$AWS_REGION" 2>/dev/null || true
    done
    # Also check unattached volumes tagged with our project
    UNATTACHED=$(aws ec2 describe-volumes --region "$AWS_REGION" \
        --filters "Name=status,Values=available" \
        --query 'Volumes[*].VolumeId' --output text 2>/dev/null | tr '\t' '\n')
    for vol in $UNATTACHED; do
        TAGS=$(aws ec2 describe-volumes --volume-ids "$vol" --region "$AWS_REGION" \
            --query 'Volumes[*].Tags[*].[Key,Value]' --output text 2>/dev/null | tr '\n' ' ')
        if echo "$TAGS" | grep -qi "agentic-rag\|opensearch" 2>/dev/null; then
            log_warn "Unattached EBS volume ${vol} tagged for project — deleting..."
            aws ec2 delete-volume --volume-id "$vol" --region "$AWS_REGION" 2>/dev/null || true
        fi
    done
else
    log_ok "No orphaned EBS volumes tagged for ${CLUSTER_NAME}"
fi

# --- 13d: Security Groups (orphaned after cluster deletion) ---
log_info "Checking for orphaned Security Groups..."
SGS=$(aws ec2 describe-security-groups --region "$AWS_REGION" \
    --filters "Name=tag:Name,Values=*${CLUSTER_NAME}*" \
    --query 'SecurityGroups[*].GroupId' --output text 2>/dev/null | tr '\t' '\n')

if [[ -n "$SGS" ]]; then
    for sg in $SGS; do
        log_warn "Orphaned Security Group ${sg} — attempting delete..."
        aws ec2 delete-security-group --group-id "$sg" --region "$AWS_REGION" 2>/dev/null || {
            log_warn "  Could not delete ${sg} (may still be referenced)"
        }
    done
else
    log_ok "No orphaned Security Groups found"
fi

# --- 13e: CloudFormation stacks ---
log_info "Checking for leftover CloudFormation stacks..."
STACKS=$(aws cloudformation list-stacks --region "$AWS_REGION" \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE ROLLBACK_COMPLETE \
    --query 'StackSummaries[*].StackName' --output text 2>/dev/null | tr '\t' '\n' | grep -i "${CLUSTER_NAME}" || true)

if [[ -n "$STACKS" ]]; then
    log_warn "CloudFormation stacks still exist:"
    for stack in $STACKS; do
        log_warn "  → ${stack} — deleting..."
        aws cloudformation delete-stack --stack-name "$stack" --region "$AWS_REGION" 2>/dev/null || true
    done
    log_warn "       → CloudFormation deletions initiated (can take 5–10 min)"
else
    log_ok "No leftover CloudFormation stacks for ${CLUSTER_NAME}"
fi

# ── Final Verification ──────────────────────────────────────────────────────
log_step "Final verification — checking for any remaining resources"

echo ""
echo "  ┌─────────────────────────────────────────────────────────────┐"
echo "  │                  TEARDOWN VERIFICATION                    │"
echo "  ├─────────────────────────────────────────────────────────────┤"

# Check EKS cluster
if eksctl get cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null; then
    printf  "  │  %-50s ${RED}PRESENT${NC} │\n" "EKS cluster: ${CLUSTER_NAME}"
    CLUSTER_FOUND=1
else
    printf  "  │  %-50s ${GREEN}GONE${NC}    │\n" "EKS cluster: ${CLUSTER_NAME}"
    CLUSTER_FOUND=0
fi

# Check ECR repos
ECR_FOUND=0
for repo in agentic-rag/api agentic-rag/airflow; do
    if aws ecr describe-repositories --repository-name "$repo" --region "$AWS_REGION" &>/dev/null; then
        printf  "  │  %-50s ${RED}PRESENT${NC} │\n" "ECR repo: ${repo}"
        ECR_FOUND=1
    else
        printf  "  │  %-50s ${GREEN}GONE${NC}    │\n" "ECR repo: ${repo}"
    fi
done

# Check ELBs
ELB_COUNT=$(aws elb describe-load-balancers --region "$AWS_REGION" \
    --query 'length(LoadBalancerDescriptions)' --output text 2>/dev/null || echo 0)
printf  "  │  %-50s %-6s  │\n" "Classic ELBs remaining:" "${ELB_COUNT}"

# Check EBS volumes tagged for cluster
EBS_COUNT=$(aws ec2 describe-volumes --region "$AWS_REGION" \
    --filters "Name=tag:kubernetes.io/cluster/${CLUSTER_NAME},Values=owned" \
    --query 'length(Volumes)' --output text 2>/dev/null || echo 0)
printf  "  │  %-50s %-6s  │\n" "EBS volumes tagged for cluster:" "${EBS_COUNT}"

# Check IAM policy
if aws iam get-policy --policy-arn "arn:aws:iam::${AWS_ACCOUNT_ID}:policy/AgenticRAGBedrockPolicy" &>/dev/null; then
    printf  "  │  %-50s ${RED}PRESENT${NC} │\n" "IAM policy: AgenticRAGBedrockPolicy"
    IAM_FOUND=1
else
    printf  "  │  %-50s ${GREEN}GONE${NC}    │\n" "IAM policy: AgenticRAGBedrockPolicy"
    IAM_FOUND=0
fi

echo "  └─────────────────────────────────────────────────────────────┘"
echo ""

ALL_CLEAR=0
if [[ "$CLUSTER_FOUND" -eq 0 && "$ECR_FOUND" -eq 0 && "$IAM_FOUND" -eq 0 && "$ELB_COUNT" -eq 0 && "$EBS_COUNT" -eq 0 ]]; then
    ALL_CLEAR=1
fi

if [[ "$ALL_CLEAR" -eq 1 ]]; then
    log_ok "ALL PRIMARY RESOURCES DESTROYED. You should not incur further AWS charges for this project."
else
    log_warn "Some resources may still exist. Review the messages above for manual cleanup instructions."
    log_warn "Common manual cleanup locations:"
    log_warn "  - AWS Console → EKS → Clusters"
    log_warn "  - AWS Console → EC2 → Load Balancers"
    log_warn "  - AWS Console → EC2 → Volumes"
    log_warn "  - AWS Console → CloudFormation → Stacks"
    log_warn "  - AWS Console → IAM → Policies & Roles"
fi

log_info "Teardown complete."
