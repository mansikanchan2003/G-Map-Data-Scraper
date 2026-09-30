"""Add Template Studio fields to whatsapp_templates

Agent-generated templates carry where they came from, the state they were
written for, how they were made, and who approved or rejected them.

Revision ID: a1d8e6f3c2b4
Revises: 9c7a5e3b2d17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1d8e6f3c2b4'
down_revision: Union[str, None] = '9c7a5e3b2d17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('whatsapp_templates', sa.Column('origin', sa.String(length=20), nullable=False, server_default='manual'))
    op.add_column('whatsapp_templates', sa.Column('target_state', sa.String(length=100), nullable=True))
    op.add_column('whatsapp_templates', sa.Column('generation', sa.JSON(), nullable=True))
    op.add_column('whatsapp_templates', sa.Column('review_note', sa.Text(), nullable=True))
    op.add_column('whatsapp_templates', sa.Column('reviewed_by', sa.String(length=200), nullable=True))
    op.add_column('whatsapp_templates', sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_whatsapp_templates_target_state', 'whatsapp_templates', ['target_state'])


def downgrade() -> None:
    op.drop_index('ix_whatsapp_templates_target_state', table_name='whatsapp_templates')
    for col in ('reviewed_at', 'reviewed_by', 'review_note', 'generation', 'target_state', 'origin'):
        op.drop_column('whatsapp_templates', col)
