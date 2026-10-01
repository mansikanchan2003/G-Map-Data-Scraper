"""Store each campaign recipient's values from the sheet they came from

A template made from a messages sheet has a placeholder per varying column
(amount, date, ...), filled for each recipient from their own row.

Revision ID: e6c9a4b2d7f3
Revises: d5b8f3a1c6e2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e6c9a4b2d7f3'
down_revision: Union[str, None] = 'd5b8f3a1c6e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('whatsapp_campaign_recipients', sa.Column('variables', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('whatsapp_campaign_recipients', 'variables')
