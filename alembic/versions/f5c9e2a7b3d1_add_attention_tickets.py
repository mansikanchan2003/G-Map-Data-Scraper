"""Tickets for conversations left for a person

Each time a conversation needs attention a ticket is raised, with an id the
team can quote; pressing "Question resolved" solves it. The history of them
is kept.

Revision ID: f5c9e2a7b3d1
Revises: e4b8d1f6a2c9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f5c9e2a7b3d1'
down_revision: Union[str, None] = 'e4b8d1f6a2c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'attention_tickets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('phone', sa.String(length=20),
                  sa.ForeignKey('whatsapp_conversations.phone', ondelete='CASCADE'), nullable=False),
        sa.Column('raised_by_name', sa.String(length=200), nullable=True),
        sa.Column('question', sa.String(length=500), nullable=True),
        sa.Column('latest_question', sa.String(length=500), nullable=True),
        sa.Column('questions_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('raised_via', sa.String(length=200), nullable=False, server_default='bot'),
        sa.Column('raised_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.String(length=200), nullable=True),
    )
    op.create_index('ix_attention_tickets_phone', 'attention_tickets', ['phone'])
    op.create_index('ix_attention_tickets_raised_at', 'attention_tickets', ['raised_at'])
    op.create_index('ix_attention_tickets_resolved_at', 'attention_tickets', ['resolved_at'])


def downgrade() -> None:
    op.drop_index('ix_attention_tickets_resolved_at', table_name='attention_tickets')
    op.drop_index('ix_attention_tickets_raised_at', table_name='attention_tickets')
    op.drop_index('ix_attention_tickets_phone', table_name='attention_tickets')
    op.drop_table('attention_tickets')
