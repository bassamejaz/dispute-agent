"""Dispute record model."""

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class DisputeRecord(BaseModel):
    """Represents a flagged dispute for review."""

    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique dispute ID")
    transaction_id: str = Field(description="ID of the disputed transaction")
    user_id: str = Field(description="User who filed the dispute")
    created_at: datetime = Field(
        default_factory=datetime.now, description="When the dispute was created"
    )
    user_complaint: str = Field(description="Original user complaint text")
    conversation_context: list[dict] = Field(
        default_factory=list, description="Conversation history for context"
    )
    status: Literal["flagged", "under_review", "resolved"] = Field(
        default="flagged", description="Current dispute status"
    )
    resolution_notes: str | None = Field(
        default=None, description="Notes from resolution"
    )

    def to_display_dict(self) -> dict:
        """Return a dictionary suitable for display."""
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "status": self.status,
            "complaint": self.user_complaint[:100] + "..." if len(self.user_complaint) > 100 else self.user_complaint,
        }
