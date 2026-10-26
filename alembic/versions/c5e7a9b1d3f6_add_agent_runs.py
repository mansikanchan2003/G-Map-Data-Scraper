"""Keep every agent run's full execution chain, for the Agent quality page

The prompt, the context injected, the output and the final human version of
each run of the template writers, the bot's FAQ answers and reply
dispositions, and the Inbox's ready replies.

Revision ID: c5e7a9b1d3f6
Revises: b3d5f7a9c1e4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e7a9b1d3f6'
down_revision: Union[str, None] = 'b3d5f7a9c1e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_runs',
        sa.Column('run_id', sa.String(32), primary_key=True),
        sa.Column('agent', sa.String(40), nullable=False, index=True),
        sa.Column('subject_type', sa.String(20), nullable=False),
        sa.Column('subject_id', sa.String(64), nullable=False, index=True),
        sa.Column('model', sa.String(120), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('output', sa.Text(), nullable=True),
        sa.Column('final_output', sa.Text(), nullable=True),
        sa.Column('outcome', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('edit_distance', sa.Integer(), nullable=True),
        sa.Column('edit_ratio', sa.Float(), nullable=True),
        sa.Column('prompt_tokens', sa.Integer(), nullable=True),
        sa.Column('context_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(500), nullable=True),
        sa.Column('finalized_by', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('finalized_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('agent_runs')
