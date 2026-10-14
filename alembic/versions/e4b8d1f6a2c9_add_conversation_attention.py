"""Mark conversations whose question needs a person

A question the bot could not answer flags its conversation until someone
answers it and presses "Question resolved".

Revision ID: e4b8d1f6a2c9
Revises: d9f2a6c3e1b7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e4b8d1f6a2c9'
down_revision: Union[str, None] = 'd9f2a6c3e1b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('whatsapp_conversations',
                  sa.Column('needs_attention', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('whatsapp_conversations', sa.Column('attention_reason', sa.String(length=500), nullable=True))
    op.add_column('whatsapp_conversations', sa.Column('attention_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('whatsapp_conversations', sa.Column('attention_resolved_by', sa.String(length=200), nullable=True))
    op.add_column('whatsapp_conversations',
                  sa.Column('attention_resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_whatsapp_conversations_needs_attention', 'whatsapp_conversations', ['needs_attention'])


def downgrade() -> None:
    op.drop_index('ix_whatsapp_conversations_needs_attention', table_name='whatsapp_conversations')
    for col in ('attention_resolved_at', 'attention_resolved_by', 'attention_at', 'attention_reason',
                'needs_attention'):
        op.drop_column('whatsapp_conversations', col)
