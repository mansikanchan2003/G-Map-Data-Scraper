"""A work queue between the API and the scraper container (22 Nov 2026)

Revision ID: c3e5a7b9d1f2
Revises: b7d9f1a3c5e8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c3e5a7b9d1f2'
down_revision: Union[str, None] = 'b7d9f1a3c5e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'queued_tasks',
        sa.Column('task_id', sa.String(length=32), primary_key=True),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='QUEUED'),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('claimed_by', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_queued_tasks_kind', 'queued_tasks', ['kind'])
    op.create_index('ix_queued_tasks_status', 'queued_tasks', ['status'])
    op.create_index('ix_queued_tasks_created_at', 'queued_tasks', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_queued_tasks_created_at', table_name='queued_tasks')
    op.drop_index('ix_queued_tasks_status', table_name='queued_tasks')
    op.drop_index('ix_queued_tasks_kind', table_name='queued_tasks')
    op.drop_table('queued_tasks')
