"""Add agent_action_proposals - durable store for a specialist ActionProposal awaiting HITL
confirm/reject, replacing the in-memory _pending_specialist_proposals dict in src/api/routes.py."""

import sqlalchemy as sa
from alembic import op

revision = "20260822_17"
down_revision = "20260822_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    if "agent_action_proposals" not in inspector.get_table_names():
        op.create_table(
            "agent_action_proposals",
            sa.Column("thread_id", sa.String(), nullable=False),
            sa.Column("proposal_id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=False),
            sa.Column("actor_user_id", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("organization_workspace_id", sa.String(), nullable=False),
            sa.Column("agent_profile", sa.String(), nullable=False),
            sa.Column("requested_scope", sa.String(), nullable=False),
            sa.Column("target_agent_workspace_id", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "status IN ('pending', 'approved', 'rejected')", name="ck_agent_action_proposal_status"
            ),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["organization_workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["target_agent_workspace_id"], ["agent_workspaces.id"]),
            sa.PrimaryKeyConstraint("thread_id"),
        )
        op.create_index("ix_agent_action_proposals_proposal_id", "agent_action_proposals", ["proposal_id"])
        op.create_index("ix_agent_action_proposals_trace_id", "agent_action_proposals", ["trace_id"])
        op.create_index("ix_agent_action_proposals_actor_user_id", "agent_action_proposals", ["actor_user_id"])
        op.create_index(
            "ix_agent_action_proposals_actor_created", "agent_action_proposals", ["actor_user_id", "created_at"]
        )


def downgrade() -> None:
    op.drop_table("agent_action_proposals")
