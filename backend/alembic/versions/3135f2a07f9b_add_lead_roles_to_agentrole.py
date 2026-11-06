"""add_lead_roles_to_agentrole

Revision ID: 3135f2a07f9b
Revises: 5362c432beca
Create Date: 2026-11-06 23:22:23.564453

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3135f2a07f9b'
down_revision: Union[str, Sequence[str], None] = '5362c432beca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE agentrole ADD VALUE IF NOT EXISTS 'INVESTIGATION_LEAD'")
    op.execute("ALTER TYPE agentrole ADD VALUE IF NOT EXISTS 'RESOLUTION_LEAD'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
