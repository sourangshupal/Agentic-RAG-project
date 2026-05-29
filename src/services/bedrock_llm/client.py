import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from src.config import Settings
from src.exceptions import BedrockConnectionError, BedrockLLMException, BedrockTimeoutError
from src.services.ollama.prompts import RAGPromptBuilder, ResponseParser

logger = logging.getLogger(__name__)


class BedrockLLMClient:
    """LLM client backed by AWS Bedrock — drop-in replacement for OpenAILLMClient.

    Satisfies LLMClientProtocol so all agent nodes work without modification.
    Uses boto3 bedrock-runtime for direct API calls and langchain-aws ChatBedrock
    for LangGraph node integration.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._bedrock_cfg = settings.bedrock
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()
        self._client: Optional[Any] = None  # boto3 bedrock-runtime client

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            kwargs: Dict[str, Any] = {"region_name": self._bedrock_cfg.aws_region}
            if self._bedrock_cfg.aws_access_key_id:
                kwargs["aws_access_key_id"] = self._bedrock_cfg.aws_access_key_id
                kwargs["aws_secret_access_key"] = self._bedrock_cfg.aws_secret_access_key.get_secret_value()
            self._client = boto3.client("bedrock-runtime", **kwargs)
        return self._client

    @staticmethod
    def _infer_provider(model_id: str) -> Optional[str]:
        """Infer Bedrock provider from model ID or ARN. Required by ChatBedrock when model_id is an ARN."""
        lower = model_id.lower()
        if "meta" in lower or "llama" in lower:
            return "meta"
        if "anthropic" in lower or "claude" in lower:
            return "anthropic"
        if "amazon" in lower or "titan" in lower or "nova" in lower:
            return "amazon"
        if "mistral" in lower:
            return "mistral"
        if "cohere" in lower:
            return "cohere"
        return None

    def get_langchain_model(self, model: str = "", temperature: float = 0.0) -> Any:
        """Return a LangChain ChatBedrock instance for use in agent nodes."""
        from langchain_aws import ChatBedrock

        model_id = model or self._bedrock_cfg.model_id
        kwargs: Dict[str, Any] = {
            "model_id": model_id,
            "region_name": self._bedrock_cfg.aws_region,
            "model_kwargs": {"temperature": temperature},
        }
        provider = self._infer_provider(model_id)
        if provider:
            kwargs["provider"] = provider
        if self._bedrock_cfg.aws_access_key_id:
            kwargs["aws_access_key_id"] = self._bedrock_cfg.aws_access_key_id
            kwargs["aws_secret_access_key"] = self._bedrock_cfg.aws_secret_access_key.get_secret_value()
        return ChatBedrock(**kwargs)

    async def health_check(self) -> Dict[str, Any]:
        """Check Bedrock API connectivity by listing foundation models."""
        try:
            import boto3

            kwargs: Dict[str, Any] = {"region_name": self._bedrock_cfg.aws_region}
            if self._bedrock_cfg.aws_access_key_id:
                kwargs["aws_access_key_id"] = self._bedrock_cfg.aws_access_key_id
                kwargs["aws_secret_access_key"] = self._bedrock_cfg.aws_secret_access_key.get_secret_value()
            bedrock = boto3.client("bedrock", **kwargs)
            resp = await asyncio.to_thread(bedrock.list_foundation_models)
            model_count = len(resp.get("modelSummaries", []))
            return {
                "status": "healthy",
                "message": "AWS Bedrock is reachable",
                "provider": "bedrock",
                "region": self._bedrock_cfg.aws_region,
                "model_count": model_count,
            }
        except Exception as e:
            import botocore.exceptions

            if isinstance(e, botocore.exceptions.NoCredentialsError):
                raise BedrockConnectionError(f"AWS credentials not found: {e}")
            if isinstance(e, botocore.exceptions.EndpointConnectionError):
                raise BedrockConnectionError(f"Cannot reach AWS Bedrock endpoint: {e}")
            raise BedrockLLMException(f"Bedrock health check failed: {e}")

    async def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate a RAG answer using Bedrock converse API."""
        model_id = model or self._bedrock_cfg.model_id
        prompt = self.prompt_builder.create_rag_prompt(query, chunks)

        system_text = (
            "You are a helpful research assistant. Answer questions based only "
            "on the provided context from academic papers. Be concise and accurate."
        )
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        system = [{"text": system_text}]

        def _call_converse() -> Dict[str, Any]:
            client = self._get_client()
            return client.converse(
                modelId=model_id,
                messages=messages,
                system=system,
                inferenceConfig={"temperature": 0.0},
            )

        try:
            response = await asyncio.to_thread(_call_converse)

            answer = ""
            output_message = response.get("output", {}).get("message", {})
            for content_block in output_message.get("content", []):
                if "text" in content_block:
                    answer += content_block["text"]

            sources = []
            seen_urls: set = set()
            for chunk in chunks:
                arxiv_id = chunk.get("arxiv_id")
                if arxiv_id:
                    arxiv_id_clean = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id_clean}.pdf"
                    if pdf_url not in seen_urls:
                        sources.append(pdf_url)
                        seen_urls.add(pdf_url)

            citations = list(set(chunk.get("arxiv_id") for chunk in chunks if chunk.get("arxiv_id")))
            usage = response.get("usage", {})

            return {
                "answer": answer,
                "sources": sources,
                "confidence": "high",
                "citations": citations[:5],
                "usage": {
                    "prompt_tokens": usage.get("inputTokens", 0),
                    "completion_tokens": usage.get("outputTokens", 0),
                    "total_tokens": usage.get("totalTokens", 0),
                },
            }

        except Exception as e:
            import botocore.exceptions

            if isinstance(e, botocore.exceptions.EndpointConnectionError):
                raise BedrockConnectionError(f"Cannot reach AWS Bedrock: {e}")
            logger.error(f"Bedrock generate_rag_answer failed: {e}")
            raise BedrockLLMException(f"Failed to generate RAG answer via Bedrock: {e}")

    async def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "",
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream a RAG answer using Bedrock converse_stream API."""
        model_id = model or self._bedrock_cfg.model_id
        prompt = self.prompt_builder.create_rag_prompt(query, chunks)

        system_text = (
            "You are a helpful research assistant. Answer questions based only "
            "on the provided context from academic papers. Be concise and accurate."
        )
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        system = [{"text": system_text}]

        def _collect_stream() -> List[str]:
            """Collect streaming tokens from Bedrock converse_stream (sync)."""
            client = self._get_client()
            response = client.converse_stream(
                modelId=model_id,
                messages=messages,
                system=system,
                inferenceConfig={"temperature": 0.0},
            )
            tokens: List[str] = []
            for event in response.get("stream", []):
                if "contentBlockDelta" in event:
                    delta = event["contentBlockDelta"].get("delta", {})
                    if "text" in delta:
                        tokens.append(delta["text"])
            return tokens

        try:
            tokens = await asyncio.to_thread(_collect_stream)
        except Exception as e:
            import botocore.exceptions

            if isinstance(e, botocore.exceptions.EndpointConnectionError):
                raise BedrockConnectionError(f"Cannot reach AWS Bedrock: {e}")
            logger.error(f"Bedrock streaming failed: {e}")
            raise BedrockLLMException(f"Bedrock streaming generation failed: {e}")

        full_text = ""
        for token in tokens:
            full_text += token
            yield {"response": token, "done": False}
        yield {"response": "", "done": True, "full_response": full_text}
