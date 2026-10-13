"""Add application comments and removals, for the Applications tab

Revision ID: d9f2a6c3e1b7
Revises: c8e1f4a7b2d6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd9f2a6c3e1b7'
down_revision: Union[str, None] = 'c8e1f4a7b2d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'application_comments',
        sa.Column('comment_id', sa.String(length=32), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('author', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['phone'], ['whatsapp_conversations.phone'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('comment_id'),
    )
    op.create_index('ix_application_comments_phone', 'application_comments', ['phone'])
    op.create_table(
        'application_removals',
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('removed_by', sa.String(length=200), nullable=False),
        sa.Column('removed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['phone'], ['whatsapp_conversations.phone'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('phone'),
    )


def downgrade() -> None:
    op.drop_table('application_removals')
    op.drop_index('ix_application_comments_phone', table_name='application_comments')
    op.drop_table('application_comments')
