"""Payload schema produced by the Quality Assurance agent's ``build_quality_brief`` tool.

Mirrors ``src.agents.schemas.delivery.DeliveryBriefPayload`` - its own Quality-domain vocabulary
(test progress, defects, release readiness) kept separate from the generic, cross-profile
``WorkspaceBrief``/``ExecutiveBrief`` envelopes in ``src.agents.contracts``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.agents.contracts import ReleaseReadiness


class QualityBriefPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str = Field(min_length=1)
    release_readiness: ReleaseReadiness
    test_progress: dict = Field(default_factory=dict)
    critical_defects: list[dict] = Field(default_factory=list)
    blocked_tests: list[dict] = Field(default_factory=list)
