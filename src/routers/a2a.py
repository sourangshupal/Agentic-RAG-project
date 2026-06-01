from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Request
from src.config import Settings
from src.services.a2a.models import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    Artifact,
    Part,
    Task,
    TaskSendParams,
    TaskStatus,
)
from src.services.openai_llm.client import OpenAILLMClient

logger = logging.getLogger(__name__)
router = APIRouter(tags=["a2a"])


@router.get("/.well-known/agent.json", response_model=AgentCard)
async def get_agent_card(request: Request) -> AgentCard:
    base_url = str(request.base_url).rstrip("/")
    return AgentCard(
        name="ArXiv RAG Agent",
        description="Answers questions about CS/AI/ML arXiv papers using hybrid search and LLMs.",
        url=f"{base_url}/a2a/tasks/send",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        skills=[
            AgentSkill(
                id="arxiv-qa",
                name="ArXiv Paper Q&A",
                description="Answer natural language questions about recent CS/AI/ML research papers.",
            )
        ],
    )


@router.post("/a2a/tasks/send", response_model=Task)
async def send_task(params: TaskSendParams, request: Request) -> Task:
    query = " ".join(p.text for p in params.message.parts if p.type == "text")
    logger.info("A2A task received: task_id=%s query_len=%d", params.id, len(query))

    # A2A uses OpenAI directly regardless of the global PROVIDER setting
    settings = Settings()
    openai_client = OpenAILLMClient(settings)

    # Retrieve chunks via OpenSearch (reuses shared infra)
    embeddings_service = request.app.state.embeddings_service
    opensearch_client = request.app.state.opensearch_client

    query_embedding = await embeddings_service.embed_query(query)
    search_results = opensearch_client.search_unified(
        query=query,
        query_embedding=query_embedding,
        size=5,
        use_hybrid=True,
    )

    chunks: List[Dict[str, Any]] = search_results.get("hits", [])
    logger.info("A2A retrieved %d chunks for OpenAI generation", len(chunks))

    result = await openai_client.generate_rag_answer(
        query=query,
        chunks=chunks,
        model=settings.openai_model,
    )

    return Task(
        id=params.id,
        status=TaskStatus(state="completed"),
        artifacts=[Artifact(parts=[Part(text=result["answer"])])],
    )
