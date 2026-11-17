"""CSPs near DCs: businesses found at the SBI-allocated CSP centres in the DCs' districts (17 Nov 2026)

Revision ID: a1c3e5f7b9d2
Revises: e4b6d8f0a2c5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, None] = 'e4b6d8f0a2c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('businesses', sa.Column('near_dc', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_businesses_near_dc', 'businesses', ['near_dc'])


def downgrade() -> None:
    op.drop_index('ix_businesses_near_dc', table_name='businesses')
    op.drop_column('businesses', 'near_dc')
