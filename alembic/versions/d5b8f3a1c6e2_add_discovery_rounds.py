"""Add discovery_rounds for the scraping autopilot

Revision ID: d5b8f3a1c6e2
Revises: c4a7e2d9b8f1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd5b8f3a1c6e2'
down_revision: Union[str, None] = 'c4a7e2d9b8f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'discovery_rounds',
        sa.Column('round_id', sa.String(length=32), nullable=False),
        sa.Column('state', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='ACTIVE'),
        sa.Column('plan', sa.JSON(), nullable=False),
        sa.Column('batches_done', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('round_id'),
    )
    op.create_index('ix_discovery_rounds_state', 'discovery_rounds', ['state'])
    op.create_index('ix_discovery_rounds_status', 'discovery_rounds', ['status'])
    op.create_index('ix_discovery_rounds_created_at', 'discovery_rounds', ['created_at'])


def downgrade() -> None:
    for ix in ('ix_discovery_rounds_created_at', 'ix_discovery_rounds_status', 'ix_discovery_rounds_state'):
        op.drop_index(ix, table_name='discovery_rounds')
    op.drop_table('discovery_rounds')
