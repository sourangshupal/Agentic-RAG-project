import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config import Settings
from src.exceptions import BedrockGuardrailsException

logger = logging.getLogger(__name__)


@dataclass
class GuardrailResult:
    """Result from a Bedrock Guardrails ApplyGuardrail call.

    :param allowed: True if the content passed all guardrail checks.
    :param action: "NONE" if content passed, "INTERVENED" if blocked/modified.
    :param reason: Human-readable explanation of the action taken.
    :param outputs: Modified content returned by Bedrock (e.g., PII-redacted text).
    """

    allowed: bool
    action: str  # "NONE" | "INTERVENED"
    reason: str
    outputs: List[str] = field(default_factory=list)


class BedrockGuardrailsService:
    """Wraps AWS Bedrock Guardrails ApplyGuardrail API.

    Handles four guardrail capabilities:
    - Topic denial: block queries outside CS/AI/ML scope
    - Content filters: hate speech, violence, misconduct
    - PII detection: anonymise personal information
    - Grounding check: verify answers are grounded in retrieved sources

    Graceful degradation: when guardrail_id is empty, all requests pass through
    with action="NONE" (fail-open). This preserves backward compatibility when
    Bedrock Guardrails are not yet configured.
    """

    def __init__(self, settings: Settings):
        self._cfg = settings.bedrock
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            kwargs: Dict[str, Any] = {"region_name": self._cfg.aws_region}
            if self._cfg.aws_access_key_id:
                kwargs["aws_access_key_id"] = self._cfg.aws_access_key_id
                kwargs["aws_secret_access_key"] = self._cfg.aws_secret_access_key.get_secret_value()
            self._client = boto3.client("bedrock-runtime", **kwargs)
        return self._client

    def _disabled_result(self) -> GuardrailResult:
        return GuardrailResult(
            allowed=True,
            action="NONE",
            reason="guardrails_disabled: BEDROCK__GUARDRAIL_ID not configured",
        )

    async def check_input(self, query: str) -> GuardrailResult:
        """Apply guardrail to the user query (INPUT side).

        Evaluates topic denial, content filters, and PII on the incoming query.

        :param query: Raw user query text.
        :returns: GuardrailResult with allowed flag and reason.
        """
        if not self._cfg.guardrail_id:
            logger.debug("Bedrock guardrails disabled (no guardrail_id) — passing input through")
            return self._disabled_result()

        content = [{"text": {"text": query}}]
        return await self._apply_guardrail(source="INPUT", content=content, label="input")

    async def check_output(self, answer: str, source_docs: List[str]) -> GuardrailResult:
        """Apply guardrail to the generated answer (OUTPUT side).

        Evaluates content filters and grounding: verifies the answer is
        supported by the retrieved source documents.

        :param answer: Generated answer text.
        :param source_docs: Retrieved source document texts used as grounding context.
        :returns: GuardrailResult with allowed flag and reason.
        """
        if not self._cfg.guardrail_id:
            logger.debug("Bedrock guardrails disabled (no guardrail_id) — passing output through")
            return self._disabled_result()

        # Build content: grounding sources first, then the response being checked.
        content: List[Dict[str, Any]] = [
            {"text": {"text": doc, "qualifiers": ["grounding_source"]}}
            for doc in source_docs
            if doc.strip()
        ]
        content.append({"text": {"text": answer}})

        return await self._apply_guardrail(source="OUTPUT", content=content, label="output")

    async def _apply_guardrail(
        self,
        source: str,
        content: List[Dict[str, Any]],
        label: str,
    ) -> GuardrailResult:
        """Call Bedrock ApplyGuardrail API and parse the response."""

        def _call() -> Dict[str, Any]:
            client = self._get_client()
            return client.apply_guardrail(
                guardrailIdentifier=self._cfg.guardrail_id,
                guardrailVersion=self._cfg.guardrail_version,
                source=source,
                content=content,
            )

        try:
            response = await asyncio.to_thread(_call)
        except Exception as e:
            import botocore.exceptions

            logger.error(f"Bedrock guardrail {label} check failed: {e}")
            if isinstance(e, botocore.exceptions.ClientError):
                error_code = e.response["Error"]["Code"]
                raise BedrockGuardrailsException(
                    f"Bedrock Guardrails API error ({error_code}): {e}"
                )
            raise BedrockGuardrailsException(f"Bedrock Guardrails {label} check failed: {e}")

        action = response.get("action", "NONE")
        allowed = action == "NONE"

        # Extract human-readable reason from assessments
        reason = self._extract_reason(response, action)

        # Extract any modified output text (e.g., PII-redacted version)
        outputs = [
            block["text"]
            for block in response.get("outputs", [])
            if "text" in block
        ]

        logger.info(f"Guardrail {label} check: action={action}, allowed={allowed}, reason={reason}")
        return GuardrailResult(allowed=allowed, action=action, reason=reason, outputs=outputs)

    @staticmethod
    def _extract_reason(response: Dict[str, Any], action: str) -> str:
        """Parse assessments array to build a human-readable reason string."""
        if action == "NONE":
            return "Content passed all guardrail checks"

        reasons: List[str] = []
        for assessment in response.get("assessments", []):
            # Topic policy violations
            for topic in assessment.get("topicPolicy", {}).get("topics", []):
                if topic.get("action") == "BLOCKED":
                    reasons.append(f"topic_blocked: {topic.get('name', 'unknown')}")

            # Content policy violations
            for item in assessment.get("contentPolicy", {}).get("filters", []):
                if item.get("action") == "BLOCKED":
                    reasons.append(f"content_blocked: {item.get('type', 'unknown')}")

            # PII violations
            for entity in assessment.get("sensitiveInformationPolicy", {}).get("piiEntities", []):
                if entity.get("action") in ("BLOCKED", "ANONYMIZED"):
                    reasons.append(f"pii_{entity.get('action', 'detected').lower()}: {entity.get('type', 'unknown')}")

            # Grounding violations
            grounding = assessment.get("groundingPolicy", {})
            if grounding.get("filters"):
                for f in grounding["filters"]:
                    if f.get("action") == "BLOCKED":
                        score = f.get("score", 0)
                        reasons.append(f"grounding_blocked: score={score:.2f}")

        return "; ".join(reasons) if reasons else f"Guardrail intervened (action={action})"
