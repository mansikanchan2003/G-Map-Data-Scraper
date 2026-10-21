"""Keep the contacts and tasks each disposition calls for

The team's "Call Dispositions" sheet: every disposition has an action (call
back at a time, try again the next day, a visit by the District
Coordinator...). Until calls are added these are WhatsApp nudges; each row
records what was wanted, what was used, and how it went.

Revision ID: b6d8f0a2c4e9
Revises: a4c6e8f0b2d7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b6d8f0a2c4e9'
down_revision: Union[str, None] = 'a4c6e8f0b2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'follow_ups',
        sa.Column('followup_id', sa.String(32), primary_key=True),
        sa.Column('phone', sa.String(20), sa.ForeignKey('whatsapp_conversations.phone', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('disposition', sa.String(40), nullable=False),
        sa.Column('purpose', sa.String(40), nullable=False),
        sa.Column('owner', sa.String(10), nullable=False),
        sa.Column('wants', sa.String(20), nullable=False),
        sa.Column('channel', sa.String(20), nullable=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='scheduled', index=True),
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('expects_reply', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('cancel_on_reply', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('task', sa.String(300), nullable=True),
        sa.Column('language', sa.String(12), nullable=True),
        sa.Column('message_id', sa.String(64), nullable=True),
        sa.Column('note', sa.String(500), nullable=True),
        sa.Column('created_by', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('done_by', sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('follow_ups')
