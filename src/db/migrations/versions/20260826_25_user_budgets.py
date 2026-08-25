"""Add optional per-user daily AI token budgets."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_25"
down_revision = "20260826_24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "daily_token_budget" not in {column["name"] for column in inspector.get_columns("users")}:
        op.add_column("users", sa.Column("daily_token_budget", sa.Integer(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "daily_token_budget" in {column["name"] for column in inspector.get_columns("users")}:
        op.drop_column("users", "daily_token_budget")
