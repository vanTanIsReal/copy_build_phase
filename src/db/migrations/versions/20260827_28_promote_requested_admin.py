"""Promote the explicitly requested production administrator account."""

import sqlalchemy as sa
from alembic import op

revision = "20260827_28"
down_revision = "20260827_27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE users SET role = 'admin', platform_role = 'platform_admin' "
            "WHERE lower(email) = 'admin1@gmail.com'"
        )
    )


def downgrade() -> None:
    pass
