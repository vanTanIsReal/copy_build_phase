"""Restore audit log columns missing from older production schemas."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_21"
down_revision = "20260824_19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    if "workspace_id" not in columns:
        op.add_column("audit_logs", sa.Column("workspace_id", sa.String(), nullable=True))
    if "ip_address" not in columns:
        op.add_column("audit_logs", sa.Column("ip_address", sa.String(), nullable=True))
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("audit_logs")}
    if "ix_audit_logs_workspace_id" not in indexes:
        op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes("audit_logs")}
    if "ix_audit_logs_workspace_id" in indexes:
        op.drop_index("ix_audit_logs_workspace_id", table_name="audit_logs")
    columns = {column["name"] for column in inspector.get_columns("audit_logs")}
    if "ip_address" in columns:
        op.drop_column("audit_logs", "ip_address")
    if "workspace_id" in columns:
        op.drop_column("audit_logs", "workspace_id")
