"""Add full_analysis and is_verified

Revision ID: ee5c250d008d
Revises: 0c973abfceb6
Create Date: 2026-05-11 17:01:33.342209

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ee5c250d008d'
down_revision = '0c973abfceb6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('articles', sa.Column('is_verified', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('articles', sa.Column('full_analysis', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('articles', 'full_analysis')
    op.drop_column('articles', 'is_verified')
