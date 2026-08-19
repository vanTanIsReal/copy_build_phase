from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from src.agents.contracts import AgentProfile


class AgentWorkspaceCreate(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    agent_profile: Literal[AgentProfile.PRODUCT_DELIVERY, AgentProfile.QUALITY_ASSURANCE]

    @field_validator("key", "name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Value cannot be blank")
        return normalized


class AgentWorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_workspace_id: str
    key: str
    name: str
    agent_profile: Literal["product_delivery", "quality_assurance"]
    status: Literal["active", "suspended", "archived"]
    created_at: datetime
    updated_at: datetime


class AgentWorkspaceMemberCreate(BaseModel):
    email: EmailStr
    business_role: Literal["member", "lead", "executive_viewer"]


class AgentWorkspaceMemberOut(BaseModel):
    id: str
    agent_workspace_id: str
    user_id: str
    email: str
    display_name: str
    business_role: Literal["member", "lead", "executive_viewer"]
    status: Literal["active", "invited", "suspended", "revoked"]
    created_at: datetime
    updated_at: datetime


class AgentWorkspaceConversationCreate(BaseModel):
    conversation_id: str = Field(min_length=1)
    classification: Literal["delivery", "quality"]


class AgentWorkspaceConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_workspace_id: str
    conversation_id: str
    classification: Literal["delivery", "quality"]
    linked_by_user_id: str
    created_at: datetime


class MyAgentWorkspaceMembershipOut(BaseModel):
    """Response for GET /api/v1/agent-workspaces/{id}/my-membership - deliberately carries nothing
    beyond the caller's own business_role. No workspace name/profile/member list: a 200 here is
    only ever returned once resolve_agent_scope has already confirmed active membership, so there
    is nothing extra to gate on the client - but keeping the payload minimal means a future field
    addition can't accidentally leak workspace metadata to a non-member through this endpoint."""

    agent_workspace_id: str
    business_role: Literal["member", "lead", "executive_viewer"]
