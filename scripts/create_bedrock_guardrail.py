"""One-shot script to create the Bedrock Guardrail resource in AWS.

Run once, then copy the printed guardrailId into BEDROCK__GUARDRAIL_ID in .env.

Usage:
    uv run python scripts/create_bedrock_guardrail.py

Prerequisites:
    - BEDROCK__AWS_ACCESS_KEY_ID, BEDROCK__AWS_SECRET_ACCESS_KEY, BEDROCK__AWS_REGION set in .env
    - boto3 installed (uv sync)
    - Your AWS account must have Bedrock Guardrails access enabled
"""

import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

import boto3

from config import get_settings

settings = get_settings()
bedrock_cfg = settings.bedrock

if not bedrock_cfg.aws_access_key_id:
    print("ERROR: BEDROCK__AWS_ACCESS_KEY_ID is not set. Check your .env file.")
    sys.exit(1)

client = boto3.client(
    "bedrock",
    region_name=bedrock_cfg.aws_region,
    aws_access_key_id=bedrock_cfg.aws_access_key_id,
    aws_secret_access_key=bedrock_cfg.aws_secret_access_key.get_secret_value(),
)

print(f"Creating Bedrock Guardrail in region {bedrock_cfg.aws_region}...")

response = client.create_guardrail(
    name="arxiv-rag-guardrail",
    description="Guardrails for arXiv Paper Curator RAG — topic denial, content filters, PII, grounding",

    # ── Topic denial: block non-CS/AI/ML queries ──────────────────────────────
    topicPolicyConfig={
        "topicsConfig": [
            {
                "name": "off-topic-queries",
                "definition": (
                    "Questions or requests that are not related to computer science, "
                    "artificial intelligence, machine learning, deep learning, data science, "
                    "robotics, or academic research papers in these fields."
                ),
                "examples": [
                    "What is the weather today?",
                    "How do I cook pasta?",
                    "Tell me about politics",
                    "Who won the football game?",
                    "Help me write a poem about love",
                ],
                "type": "DENY",
            }
        ]
    },

    # ── Content filters: hate, violence, misconduct ───────────────────────────
    contentPolicyConfig={
        "filtersConfig": [
            {"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
            {"type": "INSULTS", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
            {"type": "SEXUAL", "inputStrength": "HIGH", "outputStrength": "HIGH"},
            {"type": "VIOLENCE", "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
            {"type": "MISCONDUCT", "inputStrength": "HIGH", "outputStrength": "HIGH"},
            {"type": "PROMPT_ATTACK", "inputStrength": "HIGH", "outputStrength": "NONE"},
        ]
    },

    # ── PII: anonymise personal information ───────────────────────────────────
    sensitiveInformationPolicyConfig={
        "piiEntitiesConfig": [
            {"type": "EMAIL", "action": "ANONYMIZE"},
            {"type": "PHONE", "action": "ANONYMIZE"},
            {"type": "NAME", "action": "ANONYMIZE"},
            {"type": "ADDRESS", "action": "ANONYMIZE"},
            {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
            {"type": "AWS_ACCESS_KEY", "action": "BLOCK"},
            {"type": "AWS_SECRET_KEY", "action": "BLOCK"},
        ]
    },

    # ── Grounding: verify answers are grounded in retrieved sources ───────────
    contextualGroundingPolicyConfig={
        "filtersConfig": [
            {
                "type": "GROUNDING",
                "threshold": 0.7,  # Answer must be ≥70% grounded in sources
            },
            {
                "type": "RELEVANCE",
                "threshold": 0.7,  # Answer must be ≥70% relevant to the query
            },
        ]
    },

    blockedInputMessaging=(
        "I'm sorry, but I can only answer questions about computer science, AI, and "
        "machine learning research papers. Please ask a question related to these topics."
    ),
    blockedOutputsMessaging=(
        "I'm sorry, but I cannot provide this response as it doesn't meet our content "
        "guidelines or is not sufficiently grounded in the research papers."
    ),
)

guardrail_id = response["guardrailId"]
guardrail_arn = response["guardrailArn"]
guardrail_version = response.get("version", "DRAFT")

print("\n✓ Guardrail created successfully!")
print(f"  guardrailId  : {guardrail_id}")
print(f"  guardrailArn : {guardrail_arn}")
print(f"  version      : {guardrail_version}")
print(f"\nAdd to .env:")
print(f"  BEDROCK__GUARDRAIL_ID={guardrail_id}")
print(f"  BEDROCK__GUARDRAIL_VERSION={guardrail_version}")
