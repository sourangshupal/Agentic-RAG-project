from typing import Any, AsyncIterator, Dict, List, Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Shared interface for all LLM client implementations.

    Both OpenAILLMClient and BedrockLLMClient satisfy this protocol.
    Nodes access the LLM exclusively through this interface so the
    underlying provider can be swapped via PROVIDER env var.
    """

    def get_langchain_model(self, model: str, temperature: float = 0.0) -> BaseChatModel: ...

    async def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "",
        **kwargs: Any,
    ) -> Dict[str, Any]: ...

    async def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "",
    ) -> AsyncIterator[Dict[str, Any]]: ...

    async def health_check(self) -> Dict[str, Any]: ...
