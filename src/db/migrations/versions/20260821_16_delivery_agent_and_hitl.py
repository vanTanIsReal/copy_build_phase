"""Add Product Delivery Agent work-item fields, membership consent, workspace briefs, agent
run/HITL audit tables (ported from feature/delivery-agent-tools onto the develop schema)."""

import sqlalchemy as sa
from alembic import op

revision = "20260821_16"
down_revision = "20260819_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    # Every add_column/constraint change below is guarded by an inspector check, same convention
    # as the "if <table> not in get_table_names()" guards further down for the 3 new tables. This
    # isn't optional belt-and-suspenders here: src/db/migrations/env.py imports `src.db.models`
    # (for target_metadata) before any migration runs, and on SQLite that live-updated ORM
    # metadata gets consulted by earlier migrations' own `op.create_table` calls in this same
    # script run (observed: 20260817_13's create_table for agent_workspace_memberships already
    # includes today's `AgentWorkspaceMembership.consent_status`, though that revision's own
    # source only lists its original columns) - so by the time this revision runs, these columns
    # may already exist. A real Postgres deploy never hits this (each revision only ever runs
    # once, against a database that never skipped ahead) but the guard is cheap and correct
    # either way.
    membership_columns = {c["name"] for c in inspector.get_columns("agent_workspace_memberships")}
    if "consent_status" not in membership_columns:
        op.add_column(
            "agent_workspace_memberships",
            sa.Column("consent_status", sa.String(), nullable=False, server_default="active"),
        )
    membership_checks = {c["name"] for c in inspector.get_check_constraints("agent_workspace_memberships")}
    if "ck_agent_workspace_membership_consent_status" not in membership_checks:
        # SQLite can't ALTER a constraint in place - needs the batch/table-recreate strategy
        # (env.py sets render_as_batch=True for that dialect; a direct ALTER on every other
        # dialect, Postgres included).
        with op.batch_alter_table("agent_workspace_memberships") as batch_op:
            batch_op.create_check_constraint(
                "ck_agent_workspace_membership_consent_status",
                "consent_status IN ('active', 'revoked')",
            )

    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    for column_name, column in (
        ("agent_workspace_id", sa.Column("agent_workspace_id", sa.String(), nullable=True)),
        ("confidence", sa.Column("confidence", sa.Float(), nullable=True)),
        (
            "needs_clarification",
            sa.Column("needs_clarification", sa.Boolean(), nullable=False, server_default=sa.false()),
        ),
        ("work_item_type", sa.Column("work_item_type", sa.String(), nullable=True)),
        ("severity", sa.Column("severity", sa.String(), nullable=True)),
        ("quality_status", sa.Column("quality_status", sa.String(), nullable=True)),
        ("release_target", sa.Column("release_target", sa.String(), nullable=True)),
    ):
        if column_name not in task_columns:
            op.add_column("tasks", column)

    task_fks = {fk["name"] for fk in inspector.get_foreign_keys("tasks")}
    needs_fk = "fk_tasks_agent_workspace_id" not in task_fks
    task_checks = {c["name"] for c in inspector.get_check_constraints("tasks")}
    has_old_check = "ck_task_status" in task_checks
    if needs_fk or has_old_check:
        # Same reasoning as above - a new FK and a constraint replacement both need the
        # batch/table-recreate strategy on SQLite.
        with op.batch_alter_table("tasks") as batch_op:
            if needs_fk:
                batch_op.create_foreign_key(
                    "fk_tasks_agent_workspace_id", "agent_workspaces", ["agent_workspace_id"], ["id"]
                )
            if has_old_check:
                batch_op.drop_constraint("ck_task_status", type_="check")
                batch_op.create_check_constraint(
                    "ck_task_status",
                    "status IN ('suggested', 'pending', 'in_progress', 'blocked', 'completed', 'dismissed', 'invalidated')",
                )
    task_indexes = {ix["name"] for ix in inspector.get_indexes("tasks")}
    if "ix_tasks_agent_workspace_id" not in task_indexes:
        op.create_index("ix_tasks_agent_workspace_id", "tasks", ["agent_workspace_id"])
    if "ix_tasks_release_target" not in task_indexes:
        op.create_index("ix_tasks_release_target", "tasks", ["release_target"])

    if "workspace_briefs" not in inspector.get_table_names():
        op.create_table(
            "workspace_briefs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("organization_workspace_id", sa.String(), nullable=False),
            sa.Column("agent_workspace_id", sa.String(), nullable=False),
            sa.Column("brief_type", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=False),
            sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
            sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("headline", sa.String(), nullable=False),
            sa.Column("brief_json", sa.JSON(), nullable=False),
            sa.CheckConstraint("brief_type IN ('delivery', 'quality')", name="ck_workspace_brief_type"),
            sa.ForeignKeyConstraint(["organization_workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["agent_workspace_id"], ["agent_workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_workspace_briefs_organization_workspace_id", "workspace_briefs", ["organization_workspace_id"])
        op.create_index("ix_workspace_briefs_agent_workspace_id", "workspace_briefs", ["agent_workspace_id"])
        op.create_index("ix_workspace_briefs_trace_id", "workspace_briefs", ["trace_id"])
        op.create_index("ix_workspace_briefs_generated_at", "workspace_briefs", ["generated_at"])
        op.create_index(
            "ix_workspace_briefs_workspace_type_generated",
            "workspace_briefs",
            ["agent_workspace_id", "brief_type", "generated_at"],
        )

    if "agent_runs" not in inspector.get_table_names():
        op.create_table(
            "agent_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=False),
            sa.Column("actor_user_id", sa.String(), nullable=False),
            sa.Column("organization_workspace_id", sa.String(), nullable=True),
            sa.Column("agent_workspace_id", sa.String(), nullable=True),
            sa.Column("agent_profile", sa.String(), nullable=False),
            sa.Column("intent", sa.String(), nullable=False),
            sa.Column("requested_scope", sa.String(), nullable=False),
            sa.Column("policy_decision", sa.String(), nullable=False),
            sa.Column("policy_reason", sa.String(), nullable=False),
            sa.Column("prompt_version", sa.String(), nullable=False),
            sa.Column("model", sa.String(), nullable=False, server_default=""),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("token_usage", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "policy_decision IN ('ALLOW', 'DENY', 'MASK', 'REQUIRE_APPROVAL')",
                name="ck_agent_run_policy_decision",
            ),
            sa.CheckConstraint("status IN ('success', 'partial', 'error', 'denied')", name="ck_agent_run_status"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["organization_workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["agent_workspace_id"], ["agent_workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_runs_trace_id", "agent_runs", ["trace_id"])
        op.create_index("ix_agent_runs_actor_user_id", "agent_runs", ["actor_user_id"])
        op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])
        op.create_index("ix_agent_runs_actor_created", "agent_runs", ["actor_user_id", "created_at"])

    if "agent_action_executions" not in inspector.get_table_names():
        op.create_table(
            "agent_action_executions",
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("proposal_id", sa.String(), nullable=False),
            sa.Column("trace_id", sa.String(), nullable=False),
            sa.Column("actor_user_id", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=False),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("idempotency_key"),
        )
        op.create_index("ix_agent_action_executions_proposal_id", "agent_action_executions", ["proposal_id"])
        op.create_index("ix_agent_action_executions_trace_id", "agent_action_executions", ["trace_id"])


def downgrade() -> None:
    op.drop_table("agent_action_executions")
    op.drop_table("agent_runs")
    op.drop_table("workspace_briefs")

    op.drop_index("ix_tasks_release_target", table_name="tasks")
    op.drop_index("ix_tasks_agent_workspace_id", table_name="tasks")
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_constraint("ck_task_status", type_="check")
        batch_op.create_check_constraint(
            "ck_task_status",
            "status IN ('suggested', 'pending', 'in_progress', 'completed', 'dismissed', 'invalidated')",
        )
        batch_op.drop_constraint("fk_tasks_agent_workspace_id", type_="foreignkey")
    op.drop_column("tasks", "release_target")
    op.drop_column("tasks", "quality_status")
    op.drop_column("tasks", "severity")
    op.drop_column("tasks", "work_item_type")
    op.drop_column("tasks", "needs_clarification")
    op.drop_column("tasks", "confidence")
    op.drop_column("tasks", "agent_workspace_id")

    with op.batch_alter_table("agent_workspace_memberships") as batch_op:
        batch_op.drop_constraint("ck_agent_workspace_membership_consent_status", type_="check")
    op.drop_column("agent_workspace_memberships", "consent_status")
