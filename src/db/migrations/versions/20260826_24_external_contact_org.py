"""Repair the final missing external contact organization column."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_24"
down_revision = "20260826_23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("ALTER TABLE external_contacts ADD COLUMN IF NOT EXISTS organization VARCHAR"))
    elif "organization" not in {column["name"] for column in sa.inspect(bind).get_columns("external_contacts")}:
        op.add_column("external_contacts", sa.Column("organization", sa.String(), nullable=True))


def downgrade() -> None:
    pass
