from __future__ import annotations

import logging

from fastapi import APIRouter, Request
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
    agentic_service = request.app.state.agentic_rag_service
    query = " ".join(p.text for p in params.message.parts if p.type == "text")
    logger.info("A2A task received: task_id=%s query_len=%d", params.id, len(query))

    result = await agentic_service.ask(query=query)

    return Task(
        id=params.id,
        status=TaskStatus(state="completed"),
        artifacts=[Artifact(parts=[Part(text=result["answer"])])],
    )
