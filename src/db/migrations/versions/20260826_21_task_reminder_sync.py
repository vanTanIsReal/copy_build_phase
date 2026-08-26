"""Add Task.reminder_id so accepting an AI-suggested task can auto-schedule a Reminder."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_21"
down_revision = "20260824_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    task_columns = {c["name"] for c in inspector.get_columns("tasks")}
    if "reminder_id" not in task_columns:
        op.add_column("tasks", sa.Column("reminder_id", sa.String(), nullable=True))
    task_fks = {fk["name"] for fk in inspector.get_foreign_keys("tasks")}
    if "fk_tasks_reminder_id_reminders" not in task_fks:
        # Column add and FK add are two separate batch operations (not one combined block) -
        # SQLite batch mode doesn't reliably register a named constraint created on a column
        # that's brand new within that same recreate, so a later downgrade's drop_constraint by
        # that name can't find it (see 20260821_16_delivery_agent_and_hitl.py's identical
        # add_column-then-separate-batch split for fk_tasks_agent_workspace_id).
        with op.batch_alter_table("tasks") as batch_op:
            batch_op.create_foreign_key(
                "fk_tasks_reminder_id_reminders", "reminders", ["reminder_id"], ["id"]
            )


def downgrade() -> None:
    task_fks = {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys("tasks")}
    if "fk_tasks_reminder_id_reminders" in task_fks:
        with op.batch_alter_table("tasks") as batch_op:
            batch_op.drop_constraint("fk_tasks_reminder_id_reminders", type_="foreignkey")
    task_columns = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "reminder_id" in task_columns:
        op.drop_column("tasks", "reminder_id")
