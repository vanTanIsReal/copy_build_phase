"""Payload schema produced by the Product Delivery agent's ``build_delivery_brief`` tool.

This is the structured, Delivery-domain-specific shape a specialist tool assembles *before*
it gets folded into the generic, cross-profile ``WorkspaceBrief`` envelope from
``src.agents.contracts`` (see ``build_delivery_brief`` in ``delivery_tool.py``). Keeping it as
its own schema lets the Delivery agent reason in its own vocabulary (milestones, blocked items)
while the envelope stays profile-agnostic for the Executive agent to consume later.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DeliveryBriefPayload(BaseModel):
    """Structured Delivery brief content, keyed by the facets an Executive brief needs."""

    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1)
    milestones: list[dict] = Field(default_factory=list)
    blocked_items: list[dict] = Field(default_factory=list)
    dependencies: list[dict] = Field(default_factory=list)
    decisions_needed: list[dict] = Field(default_factory=list)
