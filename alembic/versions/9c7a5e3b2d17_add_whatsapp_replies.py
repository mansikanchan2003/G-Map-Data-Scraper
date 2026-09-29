"""Add the whatsapp_replies table

Free-form answers sent back inside Meta's 24-hour window. Kept so the panel
can show what was already said, and so a refused send leaves its reason
behind rather than disappearing.

Revision ID: 9c7a5e3b2d17
Revises: 8b6f4d2a1c95
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '9c7a5e3b2d17'
down_revision: Union[str, None] = '8b6f4d2a1c95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'whatsapp_replies',
        sa.Column('reply_id', sa.String(length=32), nullable=False),
        sa.Column('click_id', sa.String(length=32), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='SENT'),
        sa.Column('provider_message_id', sa.String(length=100), nullable=True),
        sa.Column('error_reason', sa.String(length=500), nullable=True),
        sa.Column('sent_by', sa.String(length=200), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('reply_id'),
        sa.ForeignKeyConstraint(['click_id'], ['whatsapp_button_clicks.click_id'], ondelete='CASCADE'),
    )
    op.create_index('ix_whatsapp_replies_reply_id', 'whatsapp_replies', ['reply_id'])
    op.create_index('ix_whatsapp_replies_click_id', 'whatsapp_replies', ['click_id'])
    op.create_index('ix_whatsapp_replies_phone', 'whatsapp_replies', ['phone'])
    op.create_index('ix_whatsapp_replies_sent_at', 'whatsapp_replies', ['sent_at'])


def downgrade() -> None:
    op.drop_index('ix_whatsapp_replies_sent_at', table_name='whatsapp_replies')
    op.drop_index('ix_whatsapp_replies_phone', table_name='whatsapp_replies')
    op.drop_index('ix_whatsapp_replies_click_id', table_name='whatsapp_replies')
    op.drop_index('ix_whatsapp_replies_reply_id', table_name='whatsapp_replies')
    op.drop_table('whatsapp_replies')
