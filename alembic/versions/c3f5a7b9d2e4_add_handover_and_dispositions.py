"""Record who handles a chat, each chat's disposition, and the bot's own answers

The team wanted handing a chat from the bot to a person and back to be
smooth and visible, and every chat's outcome (its disposition) recorded and
shown on the Dashboard; and a question the bot answers itself to be a
ticket solved by the bot, with the answer it gave.

Revision ID: c3f5a7b9d2e4
Revises: b8e2d4f6a1c3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f5a7b9d2e4'
down_revision: Union[str, None] = 'b8e2d4f6a1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = [
    sa.Column('handled_by', sa.String(200), nullable=True),
    sa.Column('handled_since', sa.DateTime(timezone=True), nullable=True),
    sa.Column('disposition', sa.String(40), nullable=True),
    sa.Column('disposition_note', sa.String(500), nullable=True),
    sa.Column('disposition_by', sa.String(200), nullable=True),
    sa.Column('disposition_at', sa.DateTime(timezone=True), nullable=True),
]


def upgrade() -> None:
    for col in COLUMNS:
        op.add_column('whatsapp_conversations', col)
    op.create_table(
        'chat_activity',
        sa.Column('activity_id', sa.String(32), primary_key=True),
        sa.Column('phone', sa.String(20), sa.ForeignKey('whatsapp_conversations.phone', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('value', sa.String(40), nullable=True),
        sa.Column('note', sa.String(500), nullable=True),
        sa.Column('by', sa.String(200), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.add_column('attention_tickets', sa.Column('bot_answer', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('attention_tickets', 'bot_answer')
    op.drop_table('chat_activity')
    for col in reversed(COLUMNS):
        op.drop_column('whatsapp_conversations', col.name)
