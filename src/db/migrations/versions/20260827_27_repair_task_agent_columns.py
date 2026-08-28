"""Repair Task agent-workspace columns missing from legacy production databases."""

import sqlalchemy as sa
from alembic import op

revision = "20260827_27"
down_revision = "20260827_26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}

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

    inspector = sa.inspect(bind)
    task_indexes = {index["name"] for index in inspector.get_indexes("tasks")}
    if "ix_tasks_agent_workspace_id" not in task_indexes:
        op.create_index("ix_tasks_agent_workspace_id", "tasks", ["agent_workspace_id"])
    if "ix_tasks_release_target" not in task_indexes:
        op.create_index("ix_tasks_release_target", "tasks", ["release_target"])

    task_fks = {fk["name"] for fk in sa.inspect(bind).get_foreign_keys("tasks")}
    if "fk_tasks_agent_workspace_id" not in task_fks:
        with op.batch_alter_table("tasks") as batch_op:
            batch_op.create_foreign_key(
                "fk_tasks_agent_workspace_id",
                "agent_workspaces",
                ["agent_workspace_id"],
                ["id"],
            )


def downgrade() -> None:
    pass
