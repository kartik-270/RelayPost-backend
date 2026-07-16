"""Alter user_follows target_id to string

Revision ID: e1f2g3h4i5j6
Revises: 691aefbc8d88
Create Date: 2026-07-17 01:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e1f2g3h4i5j6'
down_revision: Union[str, None] = '691aefbc8d88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('user_follows', 'target_id',
               existing_type=postgresql.UUID(),
               type_=sa.String(),
               existing_nullable=False,
               postgresql_using='target_id::varchar')


def downgrade() -> None:
    op.alter_column('user_follows', 'target_id',
               existing_type=sa.String(),
               type_=postgresql.UUID(),
               existing_nullable=False,
               postgresql_using='target_id::uuid')
