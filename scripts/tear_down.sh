#!/usr/bin/env bash
# =============================================================================
# tear_down.sh — Complete AWS Infrastructure Teardown
# =============================================================================
# Destroys every AWS resource created by the Agentic RAG project.
# Designed to be idempotent and fault-tolerant: if a resource is already gone
# the script continues to the next step and tells you what (if anything) still
# needs manual cleanup.
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

# ── Configuration ───────────────────────────────────────────────────────────
# 1. Load from .env if present (git-ignored — safe for secrets)
if [[ -f .env ]]; then
    # shellcheck source=/dev/null
    source .env
    log_info "Loaded configuration from .env"
fi

# 2. Allow overrides via command-line arguments
CLUSTER_NAME="${1:-${CLUSTER_NAME:-agentic-rag-cluster}}"
AWS_REGION="${2:-${AWS_REGION:-us-east-1}}"
AWS_ACCOUNT_ID="${3:-${AWS_ACCOUNT_ID:-}}"

# 3. Derived values
ECR_REGISTRY="${AWS_ACCOUNT_ID:-REPLACEME}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# ── Prerequisites check ─────────────────────────────────────────────────────
log_step "Checking prerequisites"
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

# Verify AWS credentials work
if ! aws sts get-caller-identity &>/dev/null; then
    log_err "AWS credentials not configured or invalid."
    log_err "Run: aws configure   OR   export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY"
    exit 1
fi

log_ok "AWS credentials valid"

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
        log_warn "       → You may need to delete this manually in the AWS Console"
        return 1
    fi
}

# ── STEP 1: Helm releases (Grafana Cloud monitoring) ─────────────────────────
log_step "STEP 1/6: Uninstalling Helm releases"

# Sub-chart releases first, then the parent umbrella release
run_step "Helm: uninstall alloy-logs" \
    "helm uninstall grafana-k8s-monitoring-alloy-logs -n monitoring 2>/dev/null"

run_step "Helm: uninstall alloy-metrics" \
    "helm uninstall grafana-k8s-monitoring-alloy-metrics -n monitoring 2>/dev/null"

run_step "Helm: uninstall alloy-singleton" \
    "helm uninstall grafana-k8s-monitoring-alloy-singleton -n monitoring 2>/dev/null"

run_step "Helm: uninstall grafana-k8s-monitoring" \
    "helm uninstall grafana-k8s-monitoring -n monitoring 2>/dev/null"

# ── STEP 2: Kubernetes namespaces ────────────────────────────────────────────
log_step "STEP 2/6: Deleting Kubernetes namespaces"

run_step "K8s: delete production namespace" \
    "kubectl delete namespace production --ignore-not-found=true --grace-period=0 --force 2>/dev/null"

run_step "K8s: delete monitoring namespace" \
    "kubectl delete namespace monitoring --ignore-not-found=true --grace-period=0 --force 2>/dev/null"

# ── STEP 3: EKS Cluster ─────────────────────────────────────────────────────
log_step "STEP 3/6: Deleting EKS cluster '$CLUSTER_NAME'"

if eksctl get cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" &>/dev/null; then
    log_info "Cluster found. Starting deletion (this takes 10–15 min)..."
    if eksctl delete cluster --name "$CLUSTER_NAME" --region "$AWS_REGION" --wait 2>&1 | tail -30; then
        log_ok "EKS cluster '$CLUSTER_NAME' deleted"
    else
        log_warn "EKS cluster deletion failed or timed out"
        log_warn "       → Manually delete in AWS Console → EKS, or run:"
        log_warn "         eksctl delete cluster --name $CLUSTER_NAME --region $AWS_REGION --force"
    fi
else
    log_ok "EKS cluster '$CLUSTER_NAME' not found — skipping"
fi

# ── STEP 4: ECR Repositories ──────────────────────────────────────────────
log_step "STEP 4/6: Deleting ECR repositories"

run_step "ECR: delete agentic-rag/api" \
    "aws ecr delete-repository --repository-name agentic-rag/api --region $AWS_REGION --force 2>/dev/null"

run_step "ECR: delete agentic-rag/airflow" \
    "aws ecr delete-repository --repository-name agentic-rag/airflow --region $AWS_REGION --force 2>/dev/null"

# ── STEP 5: Load Balancers (safety net) ─────────────────────────────────────
log_step "STEP 5/6: Cleaning up orphaned Load Balancers"

# Classic ELBs created by Kubernetes Services of type LoadBalancer
ELBS=$(aws elb describe-load-balancers --region "$AWS_REGION" \
    --query 'LoadBalancerDescriptions[?contains(LoadBalancerName, `a`)].[LoadBalancerName]' \
    --output text 2>/dev/null | head -20)

if [[ -n "$ELBS" ]]; then
    log_warn "Classic ELBs still exist:"
    echo "$ELBS" | while read -r elb; do
        log_warn "  → $elb — deleting..."
        aws elb delete-load-balancer --load-balancer-name "$elb" --region "$AWS_REGION" 2>/dev/null || true
    done
else
    log_ok "No orphaned Classic ELBs found"
fi

# ALB/NLB (ELBv2) — usually deleted automatically when the cluster goes away,
# but we check just in case.
ALBS=$(aws elbv2 describe-load-balancers --region "$AWS_REGION" \
    --query 'LoadBalancers[*].LoadBalancerArn' --output text 2>/dev/null)
if [[ -n "$ALBS" ]]; then
    log_warn "ALB/NLB resources still exist (usually auto-deleted with cluster)."
    log_warn "       → Verify in AWS Console → EC2 → Load Balancers"
fi

# ── STEP 6: CloudFormation stacks (safety net) ─────────────────────────────
log_step "STEP 6/6: Checking for leftover CloudFormation stacks"

STACKS=$(aws cloudformation list-stacks --region "$AWS_REGION" \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --query 'StackSummaries[?contains(StackName, `'$CLUSTER_NAME'`)].[StackName]' \
    --output text 2>/dev/null)

if [[ -n "$STACKS" ]]; then
    log_warn "CloudFormation stacks still exist:"
    echo "$STACKS" | while read -r stack; do
        log_warn "  → $stack"
    done
    log_warn "       → Delete manually in AWS Console → CloudFormation, or run:"
    log_warn "         aws cloudformation delete-stack --stack-name <STACK_NAME> --region $AWS_REGION"
else
    log_ok "No leftover CloudFormation stacks"
fi

# ── Final Verification ──────────────────────────────────────────────────────
log_step "Final verification"

CLUSTERS=$(eksctl get cluster --region "$AWS_REGION" 2>/dev/null | grep -c "$CLUSTER_NAME" || echo 0)
REPOS=$(aws ecr describe-repositories --region "$AWS_REGION" 2>/dev/null | grep -c "agentic-rag" || echo 0)

echo ""
echo "  ┌────────────────────────────────────────┐"
echo "  │           TEARDOWN SUMMARY             │"
echo "  ├────────────────────────────────────────┤"
printf  "  │  EKS clusters remaining:    %-10s │\n" "$CLUSTERS"
printf  "  │  ECR repos remaining:       %-10s │\n" "$REPOS"
printf  "  │  Target cluster:             %-10s │\n" "$CLUSTER_NAME"
printf  "  │  AWS region:                %-10s │\n" "$AWS_REGION"
echo "  └────────────────────────────────────────┘"
echo ""

if [[ "$CLUSTERS" -eq 0 && "$REPOS" -eq 0 ]]; then
    log_ok "All primary resources destroyed. You should not incur further AWS charges for this project."
else
    log_warn "Some resources may still exist. Review the messages above for manual cleanup instructions."
fi

log_info "Done."
