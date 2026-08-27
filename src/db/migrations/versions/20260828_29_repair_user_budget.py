"""Repair the per-user AI budget column on legacy production databases."""

import sqlalchemy as sa
from alembic import op

revision = "20260828_29"
down_revision = "20260827_28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "daily_token_budget" not in columns:
        op.add_column("users", sa.Column("daily_token_budget", sa.Integer(), nullable=True))


def downgrade() -> None:
    pass
