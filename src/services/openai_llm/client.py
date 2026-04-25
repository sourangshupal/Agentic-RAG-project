import logging
from typing import Any, Dict, List, Optional

import openai
from openai import AsyncOpenAI
from src.config import Settings
from src.exceptions import OpenAIConnectionError, OpenAILLMException, OpenAITimeoutError
from src.services.ollama.prompts import RAGPromptBuilder, ResponseParser

logger = logging.getLogger(__name__)


class OpenAILLMClient:
    """Client for OpenAI API — drop-in replacement for OllamaClient."""

    def __init__(self, settings: Settings):
        self.api_key = settings.openai_api_key
        self.timeout = settings.openai_timeout
        self.prompt_builder = RAGPromptBuilder()
        self.response_parser = ResponseParser()
        self._async_client: Optional[AsyncOpenAI] = None

    def _get_async_client(self) -> AsyncOpenAI:
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                timeout=float(self.timeout),
            )
        return self._async_client

    def get_langchain_model(self, model: str, temperature: float = 0.0):
        """Return a LangChain ChatOpenAI instance for use in agent nodes."""
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=self.api_key,
            temperature=temperature,
        )

    async def health_check(self) -> Dict[str, Any]:
        """Check OpenAI API connectivity."""
        try:
            client = self._get_async_client()
            models = await client.models.list()
            return {
                "status": "healthy",
                "message": "OpenAI API is reachable",
                "model_count": len(list(models)),
            }
        except openai.AuthenticationError as e:
            raise OpenAILLMException(f"OpenAI authentication failed — check OPENAI_API_KEY: {e}")
        except openai.APIConnectionError as e:
            raise OpenAIConnectionError(f"Cannot reach OpenAI API: {e}")
        except openai.APITimeoutError as e:
            raise OpenAITimeoutError(f"OpenAI API timed out: {e}")
        except Exception as e:
            raise OpenAILLMException(f"OpenAI health check failed: {e}")

    async def generate_rag_answer(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate a RAG answer using retrieved chunks via OpenAI chat completions."""
        try:
            prompt = self.prompt_builder.create_rag_prompt(query, chunks)
            client = self._get_async_client()

            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful research assistant. Answer questions based only "
                            "on the provided context from academic papers. Be concise and accurate."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
            )

            answer = response.choices[0].message.content or ""

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

            return {
                "answer": answer,
                "sources": sources,
                "confidence": "high",
                "citations": citations[:5],
            }

        except openai.AuthenticationError as e:
            raise OpenAILLMException(f"OpenAI authentication failed: {e}")
        except openai.APIConnectionError as e:
            raise OpenAIConnectionError(f"Cannot reach OpenAI API: {e}")
        except openai.APITimeoutError as e:
            raise OpenAITimeoutError(f"OpenAI API timed out: {e}")
        except Exception as e:
            logger.error(f"Error generating RAG answer: {e}")
            raise OpenAILLMException(f"Failed to generate RAG answer: {e}")

    async def generate_rag_answer_stream(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        model: str = "gpt-4o-mini",
    ):
        """Stream a RAG answer using OpenAI streaming chat completions."""
        try:
            prompt = self.prompt_builder.create_rag_prompt(query, chunks)
            client = self._get_async_client()

            stream = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful research assistant. Answer questions based only "
                            "on the provided context from academic papers. Be concise and accurate."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                stream=True,
            )

            full_text = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_text += delta.content
                    yield {"response": delta.content, "done": False}

            yield {"response": "", "done": True, "full_response": full_text}

        except openai.AuthenticationError as e:
            raise OpenAILLMException(f"OpenAI authentication failed: {e}")
        except openai.APIConnectionError as e:
            raise OpenAIConnectionError(f"Cannot reach OpenAI API: {e}")
        except openai.APITimeoutError as e:
            raise OpenAITimeoutError(f"OpenAI API timed out: {e}")
        except Exception as e:
            logger.error(f"Error in streaming generation: {e}")
            raise OpenAILLMException(f"Streaming generation failed: {e}")
