#!/bin/bash

set -euo pipefail

# ----------------------------
# CONFIG
# ----------------------------

REPO="sourangshupal/Agentic-RAG-project"
ENV_FILE=".env"

# ----------------------------
# Load .env
# ----------------------------

if [ ! -f "$ENV_FILE" ]; then
  echo "❌ .env file not found"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

# ----------------------------
# Generate dynamic secrets
# ----------------------------

AIRFLOW__WEBSERVER__SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

if [ -f ~/.kube/config ]; then
  KUBE_CONFIG=$(base64 < ~/.kube/config | tr -d '\n')
else
  echo "⚠️ ~/.kube/config not found"
  KUBE_CONFIG=""
fi

# ----------------------------
# Helper function
# ----------------------------

set_secret () {
    NAME=$1
    VALUE=$2

    if [ -n "${VALUE:-}" ]; then
        echo "Setting $NAME"
        gh secret set "$NAME" \
          --repo "$REPO" \
          --body "$VALUE"
    else
        echo "Skipping $NAME (empty)"
    fi
}

# ----------------------------
# Upload Secrets
# ----------------------------

# Use Bedrock AWS credentials for CI/CD ECR/EKS access
set_secret AWS_ACCESS_KEY_ID "$BEDROCK__AWS_ACCESS_KEY_ID"
set_secret AWS_SECRET_ACCESS_KEY "$BEDROCK__AWS_SECRET_ACCESS_KEY"

set_secret POSTGRES_DATABASE_URL "$POSTGRES_DATABASE_URL"
set_secret REDIS__URL "$REDIS__URL"

set_secret LANGFUSE__PUBLIC_KEY "$LANGFUSE__PUBLIC_KEY"
set_secret LANGFUSE__SECRET_KEY "$LANGFUSE__SECRET_KEY"

set_secret LOGFIRE__TOKEN "$LOGFIRE__TOKEN"

set_secret JINA_API_KEY "$JINA_API_KEY"
set_secret OPENAI_API_KEY "$OPENAI_API_KEY"

set_secret BEDROCK__AWS_ACCESS_KEY_ID "$BEDROCK__AWS_ACCESS_KEY_ID"
set_secret BEDROCK__AWS_SECRET_ACCESS_KEY "$BEDROCK__AWS_SECRET_ACCESS_KEY"

set_secret BEDROCK__MODEL_ID "$BEDROCK__MODEL_ID"
set_secret BEDROCK__GUARDRAIL_ID "$BEDROCK__GUARDRAIL_ID"

set_secret AIRFLOW__WEBSERVER__SECRET_KEY "$AIRFLOW__WEBSERVER__SECRET_KEY"

echo ""
echo "✅ All secrets uploaded"
echo ""
echo "NOTE: KUBE_CONFIG is no longer needed. The pipeline uses 'aws eks update-kubeconfig' instead."