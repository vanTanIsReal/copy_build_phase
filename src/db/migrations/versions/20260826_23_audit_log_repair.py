"""Repair targeted schema drift in legacy production databases."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_23"
down_revision = "20260826_22"
branch_labels = None
depends_on = None


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def _indexes(connection, table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(connection).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "workspace_memberships" not in tables:
        op.create_table(
            "workspace_memberships",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("invited_by_user_id", sa.String(), nullable=True),
            sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"]),
            sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_membership_user"),
            sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'guest')", name="ck_workspace_membership_role"),
            sa.CheckConstraint(
                "status IN ('active', 'invited', 'suspended', 'revoked')",
                name="ck_workspace_membership_status",
            ),
        )
    if "ix_workspace_memberships_workspace_id" not in _indexes(bind, "workspace_memberships"):
        op.create_index("ix_workspace_memberships_workspace_id", "workspace_memberships", ["workspace_id"])
    if "ix_workspace_memberships_user_id" not in _indexes(bind, "workspace_memberships"):
        op.create_index("ix_workspace_memberships_user_id", "workspace_memberships", ["user_id"])

    tables = _tables(bind)
    if "people_preferences" not in tables:
        op.create_table(
            "people_preferences",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("workspace_id", sa.String(), nullable=False),
            sa.Column("owner_user_id", sa.String(), nullable=False),
            sa.Column("subject_user_id", sa.String(), nullable=False),
            sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("private_note", sa.Text(), nullable=True),
            sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"]),
            sa.UniqueConstraint(
                "workspace_id", "owner_user_id", "subject_user_id",
                name="uq_people_preference_workspace_owner_subject",
            ),
            sa.CheckConstraint("owner_user_id <> subject_user_id", name="ck_people_preference_not_self"),
        )
    for name, columns in {
        "ix_people_preferences_workspace_id": ["workspace_id"],
        "ix_people_preferences_owner_user_id": ["owner_user_id"],
        "ix_people_preferences_subject_user_id": ["subject_user_id"],
        "ix_people_preferences_workspace_owner_pinned": ["workspace_id", "owner_user_id", "is_pinned"],
        "ix_people_preferences_workspace_owner_follow_up": ["workspace_id", "owner_user_id", "follow_up_at"],
    }.items():
        if name not in _indexes(bind, "people_preferences"):
            op.create_index(name, "people_preferences", columns)

    columns = {column["name"] for column in sa.inspect(bind).get_columns("external_contacts")}
    if "organization" not in columns:
        op.add_column("external_contacts", sa.Column("organization", sa.String(), nullable=True))
    audit_columns = {column["name"] for column in sa.inspect(bind).get_columns("audit_logs")}
    if "workspace_id" not in audit_columns:
        op.add_column("audit_logs", sa.Column("workspace_id", sa.String(), nullable=True))
    if "ip_address" not in audit_columns:
        op.add_column("audit_logs", sa.Column("ip_address", sa.String(), nullable=True))
    if "ix_audit_logs_workspace_id" not in _indexes(bind, "audit_logs"):
        op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])


def downgrade() -> None:
    # Compatibility repair is intentionally irreversible; the next deploy must retain it.
    pass
