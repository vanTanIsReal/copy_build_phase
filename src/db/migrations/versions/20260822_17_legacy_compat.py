"""Compatibility marker for databases that previously applied revision 20260822_17.

The original revision created multi-agent proposal tables that were later removed from the
product. Keeping this no-op marker preserves the Alembic revision chain for existing production
databases without recreating the retired schema on fresh installations.
"""

revision = "20260822_17"
down_revision = "20260822_20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass