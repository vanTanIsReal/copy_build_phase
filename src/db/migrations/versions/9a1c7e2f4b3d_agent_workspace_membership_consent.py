"""agent workspace membership consent status

Revision ID: 9a1c7e2f4b3d
Revises: 5fdc2d9a547c
Create Date: 2026-08-20 19:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9a1c7e2f4b3d'
down_revision: str | None = '5fdc2d9a547c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default so existing rows on a non-empty table get a valid value at ALTER time (the
    # Python-side default="active" on the model only applies to rows inserted by this app later -
    # see CLAUDE.md's note on this exact pitfall from an earlier migration in this project).
    op.add_column(
        'agent_workspace_memberships',
        sa.Column('consent_status', sa.String(), nullable=False, server_default='active'),
    )
    op.create_check_constraint(
        'ck_agent_workspace_membership_consent_status',
        'agent_workspace_memberships',
        "consent_status IN ('active', 'revoked')",
    )


def downgrade() -> None:
    op.drop_constraint('ck_agent_workspace_membership_consent_status', 'agent_workspace_memberships', type_='check')
    op.drop_column('agent_workspace_memberships', 'consent_status')
