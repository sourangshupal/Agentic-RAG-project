import logging
import re
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..models import ReasoningStep, SourceItem, ToolArtefact

logger = logging.getLogger(__name__)


def extract_sources_from_tool_messages(messages: List) -> List[SourceItem]:
    """Extract sources from tool messages in conversation.

    Parses the string representation of LangChain Documents serialized
    by LangGraph's ToolNode from the retrieve_papers tool output.

    :param messages: List of messages from graph state
    :returns: List of SourceItem objects
    """
    sources = []
    seen_arxiv_ids: set = set()

    for msg in messages:
        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == "retrieve_papers":
            content = msg.content
            if not content:
                continue

            # Parse document metadata from ToolNode's string representation of list[Document]
            # Format: [..., metadata={'arxiv_id': 'X', 'title': 'Y', 'score': Z, 'source': 'URL', ...}, ...]
            arxiv_ids = re.findall(r"'arxiv_id':\s*'([^']+)'", content)
            titles = re.findall(r"'title':\s*'([^']*)'", content)
            source_urls = re.findall(r"'source':\s*'(https?://[^']+)'", content)
            scores = re.findall(r"'score':\s*([\d.]+)", content)
            authors_matches = re.findall(r"'authors':\s*'([^']*)'", content)

            for i, arxiv_id in enumerate(arxiv_ids):
                if arxiv_id in seen_arxiv_ids:
                    continue
                seen_arxiv_ids.add(arxiv_id)

                url = source_urls[i] if i < len(source_urls) else f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                title = titles[i] if i < len(titles) else ""
                relevance_score = float(scores[i]) if i < len(scores) else 0.0
                authors_str = authors_matches[i] if i < len(authors_matches) else ""
                authors = [a.strip() for a in authors_str.split(",") if a.strip()] if authors_str else []

                sources.append(SourceItem(
                    arxiv_id=arxiv_id,
                    title=title,
                    authors=authors,
                    url=url,
                    relevance_score=relevance_score,
                ))

    logger.debug(f"Extracted {len(sources)} sources from tool messages")
    return sources


def extract_tool_artefacts(messages: List) -> List[ToolArtefact]:
    """Extract tool artifacts from messages.

    :param messages: List of messages from graph state
    :returns: List of ToolArtefact objects
    """
    artefacts = []

    for msg in messages:
        if isinstance(msg, ToolMessage):
            artefact = ToolArtefact(
                tool_name=getattr(msg, "name", "unknown"),
                tool_call_id=getattr(msg, "tool_call_id", ""),
                content=msg.content,
                metadata={},
            )
            artefacts.append(artefact)

    return artefacts


def create_reasoning_step(
    step_name: str,
    description: str,
    metadata: Optional[Dict] = None,
) -> ReasoningStep:
    """Create a reasoning step record.

    :param step_name: Name of the step/node
    :param description: Human-readable description
    :param metadata: Additional metadata
    :returns: ReasoningStep object
    """
    return ReasoningStep(
        step_name=step_name,
        description=description,
        metadata=metadata or {},
    )


def filter_messages(messages: List) -> List[AIMessage | HumanMessage]:
    """Filter messages to include only HumanMessage and AIMessage types.

    Excludes tool messages and other internal message types.

    :param messages: List of messages to filter
    :returns: Filtered list of messages
    """
    return [msg for msg in messages if isinstance(msg, (HumanMessage, AIMessage))]


def get_latest_query(messages: List) -> str:
    """Get the latest user query from messages.

    :param messages: List of messages
    :returns: Latest query text
    :raises ValueError: If no user query found
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content

    raise ValueError("No user query found in messages")


def get_latest_context(messages: List) -> str:
    """Get the latest context from tool messages.

    :param messages: List of messages
    :returns: Latest context text or empty string
    """
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            return msg.content if hasattr(msg, "content") else ""

    return ""
