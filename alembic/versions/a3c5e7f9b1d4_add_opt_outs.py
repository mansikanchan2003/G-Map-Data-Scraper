"""Numbers that asked not to be messaged: campaigns and the bot's reminders skip them

Revision ID: a3c5e7f9b1d4
Revises: e9b1d3f5a7c2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3c5e7f9b1d4'
down_revision: Union[str, None] = 'e9b1d3f5a7c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'opt_outs',
        sa.Column('phone', sa.String(length=20), primary_key=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=True),
        sa.Column('created_by', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('opt_outs')
