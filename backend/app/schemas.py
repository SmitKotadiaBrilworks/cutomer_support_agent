"""Pydantic schemas used for structured LLM outputs (not just API I/O).

These are passed to `.with_structured_output(...)` so the model is forced to
return validated, typed data instead of free-form text we'd have to parse.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class IntentClassification(BaseModel):
    """Structured classification of the customer's latest message."""

    intent: Literal[
        "order_status",
        "return_refund",
        "product_faq",
        "complaint",
        "escalation_request",
        "other",
    ] = Field(description="The primary reason for the customer's message.")
    sentiment: Literal["positive", "neutral", "negative"] = Field(
        description="Overall sentiment/tone of the customer's message."
    )
    confidence: float = Field(ge=0, le=1, description="Model confidence in this classification.")
    reasoning: str = Field(description="One short sentence explaining the classification.")


class TicketDraft(BaseModel):
    """Structured draft of a human-escalation support ticket."""

    subject: str = Field(description="Short subject line for the support ticket.")
    summary: str = Field(description="2-3 sentence summary of the issue and what's been tried so far.")
    priority: Literal["low", "medium", "high", "urgent"] = Field(
        description="Priority based on customer sentiment and issue severity."
    )


class JudgeVerdict(BaseModel):
    """Structured LLM-as-judge verdict, used by the eval harness."""

    score: int = Field(ge=1, le=5, description="1=unhelpful/wrong, 5=fully resolves the customer's need.")
    rationale: str = Field(description="One sentence explaining the score.")


class ChatRequest(BaseModel):
    session_id: str = Field(description="Stable per-conversation ID; reused across turns for memory.")
    message: str
    customer_id: Optional[str] = Field(
        default=None, description="If known (e.g. logged-in user), used to scope order lookups."
    )


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    escalated: bool
    ticket_id: Optional[str] = None
    provider_used: Optional[str] = None
    agent_path: list[str] = Field(default_factory=list, description="Ordered, deduped list of agents this turn passed through.")
    current_agent: Optional[str] = Field(default=None, description="Display name of the agent that produced the reply.")
    tools_used: list[str] = Field(default_factory=list, description="Tool names invoked during this turn.")
    intent: Optional[str] = None
    sentiment: Optional[str] = None
