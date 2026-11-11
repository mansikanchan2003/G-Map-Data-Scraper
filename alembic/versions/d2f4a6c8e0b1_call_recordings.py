"""Recordings of phone calls with applicants, from the team's call-recorder app

Revision ID: d2f4a6c8e0b1
Revises: c7e9a1b3d5f7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2f4a6c8e0b1'
down_revision: Union[str, None] = 'c7e9a1b3d5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'call_recordings',
        sa.Column('recording_id', sa.String(length=32), primary_key=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('external_id', sa.String(length=200), nullable=True, unique=True),
        sa.Column('direction', sa.String(length=10), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Integer(), nullable=True),
        sa.Column('stored_path', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('device', sa.String(length=100), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_call_recordings_phone', 'call_recordings', ['phone'])
    op.create_index('ix_call_recordings_started_at', 'call_recordings', ['started_at'])


def downgrade() -> None:
    op.drop_index('ix_call_recordings_started_at', table_name='call_recordings')
    op.drop_index('ix_call_recordings_phone', table_name='call_recordings')
    op.drop_table('call_recordings')
