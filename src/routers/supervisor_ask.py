from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from src.schemas.api.ask import AskRequest
from src.services.agents.supervisor_agent import SupervisorAgent, SupervisorResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["supervisor"])


@router.post("/ask-supervisor")
async def ask_supervisor(body: AskRequest, request: Request) -> dict:
    supervisor: SupervisorAgent = request.app.state.supervisor_agent
    logger.info("Supervisor ask: query_len=%d", len(body.query))

    result: SupervisorResult = await supervisor.ask(query=body.query)

    return {
        "query": body.query,
        "answer": result.answer,
        "intent": result.intent,
        "routed_to": result.routed_to,
        "sources": result.sources,
    }
