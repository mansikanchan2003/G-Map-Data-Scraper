"""Call recordings written out, and what the call changed (18 Nov 2026)

Revision ID: b7d9f1a3c5e8
Revises: f2a4c6e8b0d3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7d9f1a3c5e8'
down_revision: Union[str, None] = 'f2a4c6e8b0d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('call_recordings', sa.Column('transcript', sa.Text(), nullable=True))
    op.add_column('call_recordings', sa.Column('transcript_error', sa.String(length=300), nullable=True))
    op.add_column('call_recordings', sa.Column('outcome_note', sa.String(length=300), nullable=True))


def downgrade() -> None:
    for col in ('outcome_note', 'transcript_error', 'transcript'):
        op.drop_column('call_recordings', col)
