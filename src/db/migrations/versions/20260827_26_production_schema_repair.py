"""Repair legacy production audit columns after restoring the tuan migration chain."""

import sqlalchemy as sa
from alembic import op

revision = "20260827_26"
down_revision = "20260826_25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    external_columns = {c["name"] for c in inspector.get_columns("external_contacts")}
    if "organization" not in external_columns:
        op.add_column("external_contacts", sa.Column("organization", sa.String(), nullable=True))
    audit_columns = {c["name"] for c in sa.inspect(bind).get_columns("audit_logs")}
    if "workspace_id" not in audit_columns:
        op.add_column("audit_logs", sa.Column("workspace_id", sa.String(), nullable=True))
    if "ip_address" not in audit_columns:
        op.add_column("audit_logs", sa.Column("ip_address", sa.String(), nullable=True))
    if "ix_audit_logs_workspace_id" not in {i["name"] for i in sa.inspect(bind).get_indexes("audit_logs")}:
        op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])


def downgrade() -> None:
    pass
