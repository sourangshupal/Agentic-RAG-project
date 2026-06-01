from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class Part(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Message(BaseModel):
    role: Literal["user", "agent"]
    parts: list[Part]


class AgentSkill(BaseModel):
    id: str
    name: str
    description: str


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False


class AgentCard(BaseModel):
    name: str
    description: str
    url: str
    version: str
    capabilities: AgentCapabilities
    skills: list[AgentSkill]
    defaultInputModes: list[str] = ["text"]
    defaultOutputModes: list[str] = ["text"]


class TaskSendParams(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    message: Message


class TaskStatus(BaseModel):
    state: Literal["submitted", "working", "completed", "failed"]


class Artifact(BaseModel):
    index: int = 0
    parts: list[Part]


class Task(BaseModel):
    id: str
    status: TaskStatus
    artifacts: list[Artifact] = []
