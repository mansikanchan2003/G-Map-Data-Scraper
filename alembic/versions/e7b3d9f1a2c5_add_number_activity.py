"""Keep a record of messages other apps send from our WhatsApp number

The number is shared with other Eko apps (TARA, EPS nudges, the support
agent); Meta tells every app on it when a message is delivered or read. The
team wanted those counted, to see what the number is used for and spends.

Revision ID: e7b3d9f1a2c5
Revises: d6a2c8e4f1b7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7b3d9f1a2c5'
down_revision: Union[str, None] = 'd6a2c8e4f1b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'number_activity',
        sa.Column('message_id', sa.String(100), primary_key=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('category', sa.String(30), nullable=True),
        sa.Column('billable', sa.Boolean(), nullable=True),
        sa.Column('origin', sa.String(40), nullable=True),
        sa.Column('recipient_last4', sa.String(4), nullable=True),
        sa.Column('error_code', sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('number_activity')
