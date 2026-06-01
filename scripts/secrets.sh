#!/usr/bin/env bash
# ============================================================
# scripts/secrets.sh — Create K8s Secret from .env
#
# Reads values from the local .env file and creates (or updates)
# the rag-app-secrets Kubernetes Secret in the production namespace.
#
# Usage:
#   export K8S_NAMESPACE=production
#   ./scripts/secrets.sh
#
# The script extracts specific keys from .env and passes them to
# kubectl create secret via --from-literal flags.
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
NAMESPACE="${K8S_NAMESPACE:-production}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env file not found at $ENV_FILE"
    exit 1
fi

# Helper: extract a value from .env by key name
# Handles: KEY=value, KEY="value", KEY='value'
_env_value() {
    local key="$1"
    local val
    val=$(grep "^${key}=" "$ENV_FILE" | head -n1 | cut -d'=' -f2-)
    # Strip surrounding quotes if present
    val="${val#\"}"
    val="${val%\"}"
    val="${val#\'}"
    val="${val%\'}"
    echo "$val"
}

echo "Creating K8s Secret rag-app-secrets in namespace: $NAMESPACE"
echo "Reading values from: $ENV_FILE"
echo ""

kubectl create secret generic rag-app-secrets \
    --namespace "$NAMESPACE" \
    --from-literal=DEBUG="false" \
    --from-literal=ENVIRONMENT="production" \
    --from-literal=PROVIDER="bedrock" \
    --from-literal=OPENSEARCH__HOST="http://opensearch:9200" \
    --from-literal=OPENSEARCH__INDEX_NAME="arxiv-papers" \
    --from-literal=OPENSEARCH__CHUNK_INDEX_SUFFIX="chunks" \
    --from-literal=OPENSEARCH__VECTOR_DIMENSION="1024" \
    --from-literal=POSTGRES_DATABASE_URL="$(_env_value POSTGRES_DATABASE_URL)" \
    --from-literal=REDIS__URL="$(_env_value REDIS__URL)" \
    --from-literal=REDIS__TTL_HOURS="$(_env_value REDIS__TTL_HOURS)" \
    --from-literal=BEDROCK__AWS_ACCESS_KEY_ID="$(_env_value BEDROCK__AWS_ACCESS_KEY_ID)" \
    --from-literal=BEDROCK__AWS_SECRET_ACCESS_KEY="$(_env_value BEDROCK__AWS_SECRET_ACCESS_KEY)" \
    --from-literal=BEDROCK__AWS_REGION="us-east-1" \
    --from-literal=BEDROCK__MODEL_ID="$(_env_value BEDROCK__MODEL_ID)" \
    --from-literal=BEDROCK__GUARDRAIL_ID="$(_env_value BEDROCK__GUARDRAIL_ID)" \
    --from-literal=BEDROCK__GUARDRAIL_VERSION="DRAFT" \
    --from-literal=LANGFUSE__PUBLIC_KEY="$(_env_value LANGFUSE__PUBLIC_KEY)" \
    --from-literal=LANGFUSE__SECRET_KEY="$(_env_value LANGFUSE__SECRET_KEY)" \
    --from-literal=LANGFUSE__HOST="https://us.cloud.langfuse.com" \
    --from-literal=LANGFUSE__ENABLED="true" \
    --from-literal=LANGFUSE__FLUSH_AT="15" \
    --from-literal=LANGFUSE__FLUSH_INTERVAL="1.0" \
    --from-literal=LOGFIRE__TOKEN="$(_env_value LOGFIRE__TOKEN)" \
    --from-literal=LOGFIRE__ENABLED="true" \
    --from-literal=LOGFIRE__SERVICE_NAME="arxiv-rag" \
    --from-literal=LOGFIRE__ENVIRONMENT="production" \
    --from-literal=JINA_API_KEY="$(_env_value JINA_API_KEY)" \
    --from-literal=OPENAI_API_KEY="$(_env_value OPENAI_API_KEY)" \
    --from-literal=OPENAI_MODEL="gpt-4o-mini" \
    --from-literal=OPENAI_TIMEOUT="300" \
    --from-literal=AIRFLOW__DATABASE__SQL_ALCHEMY_CONN="$(_env_value POSTGRES_DATABASE_URL)" \
    --from-literal=AIRFLOW__CORE__EXECUTOR="LocalExecutor" \
    --from-literal=AIRFLOW__WEBSERVER__SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
    --from-literal=AIRFLOW__API__AUTH_BACKENDS="airflow.api.auth.backend.basic_auth" \
    --from-literal=AIRFLOW__WEBSERVER__UPDATE_FAB_PERMS="False" \
    --from-literal=PYTHONWARNINGS="ignore::FutureWarning:airflow,ignore::DeprecationWarning:airflow" \
    --from-literal=AIRFLOW__CORE__DAG_IGNORE_FILE_SYNTAX="regexp" \
    --from-literal=ARXIV__MAX_RESULTS="$(_env_value ARXIV__MAX_RESULTS)" \
    --from-literal=ARXIV__TIMEOUT_SECONDS="$(_env_value ARXIV__TIMEOUT_SECONDS)" \
    --from-literal=ARXIV__RATE_LIMIT_DELAY="$(_env_value ARXIV__RATE_LIMIT_DELAY)" \
    --from-literal=ARXIV__BASE_URL="$(_env_value ARXIV__BASE_URL)" \
    --from-literal=PDF_PARSER__MAX_PAGES="$(_env_value PDF_PARSER__MAX_PAGES)" \
    --from-literal=PDF_PARSER__DO_OCR="$(_env_value PDF_PARSER__DO_OCR)" \
    --from-literal=CHUNKING__CHUNK_SIZE="$(_env_value CHUNKING__CHUNK_SIZE)" \
    --from-literal=CHUNKING__OVERLAP_SIZE="$(_env_value CHUNKING__OVERLAP_SIZE)" \
    --from-literal=TELEGRAM__ENABLED="$(_env_value TELEGRAM__ENABLED)" \
    --from-literal=TELEGRAM__BOT_TOKEN="$(_env_value TELEGRAM__BOT_TOKEN)" \
    --dry-run=client -o yaml | kubectl apply -f -

echo ""
echo "Secret rag-app-secrets created/updated in namespace: $NAMESPACE"
