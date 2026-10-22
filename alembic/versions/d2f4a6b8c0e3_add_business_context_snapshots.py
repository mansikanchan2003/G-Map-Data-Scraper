"""Keep each day's business data from Tara in the database

scripts/export_business_context.py replaces data/business_context.json every
day. This table keeps every day's copy (totals only), so the history stays in
the database and the agent still has the latest copy if the file goes.

Revision ID: d2f4a6b8c0e3
Revises: c8e0a2b4d6f1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd2f4a6b8c0e3'
down_revision: Union[str, None] = 'c8e0a2b4d6f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'business_context_snapshots',
        sa.Column('snapshot_id', sa.String(32), primary_key=True),
        sa.Column('exported_at', sa.String(40), nullable=False, unique=True, index=True),
        sa.Column('tara_as_of', sa.String(10), nullable=True),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('stored_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('business_context_snapshots')
