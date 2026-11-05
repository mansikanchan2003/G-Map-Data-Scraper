"""Calls made by the AI calling agent (Voxomos): the chat of each call and its outcome

Revision ID: c7e9a1b3d5f7
Revises: b5d7f9a1c3e6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c7e9a1b3d5f7'
down_revision: Union[str, None] = 'b5d7f9a1c3e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ai_calls',
        sa.Column('call_id', sa.String(length=32), primary_key=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('external_id', sa.String(length=120), nullable=True, unique=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('turns', sa.JSON(), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('recording_url', sa.String(length=500), nullable=True),
        sa.Column('provider_outcome', sa.String(length=200), nullable=True),
        sa.Column('outcome', sa.String(length=40), nullable=True),
        sa.Column('outcome_reason', sa.String(length=300), nullable=True),
        sa.Column('outcome_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_ai_calls_phone', 'ai_calls', ['phone'])
    op.create_index('ix_ai_calls_started_at', 'ai_calls', ['started_at'])


def downgrade() -> None:
    op.drop_index('ix_ai_calls_started_at', table_name='ai_calls')
    op.drop_index('ix_ai_calls_phone', table_name='ai_calls')
    op.drop_table('ai_calls')
