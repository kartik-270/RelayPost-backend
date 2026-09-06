"""add_automation_state_and_diversity_score

Revision ID: b2c3d4e5f6a7
Revises: e1f2g3h4i5j6
Create Date: 2026-09-06 15:59:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'e1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create automation_state table (key-value store for round-robin queues)
    op.create_table('automation_state',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', JSONB(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('key')
    )

    # Add diversity_score column to prompt_versions
    op.add_column('prompt_versions', sa.Column('diversity_score', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('prompt_versions', 'diversity_score')
    op.drop_table('automation_state')
