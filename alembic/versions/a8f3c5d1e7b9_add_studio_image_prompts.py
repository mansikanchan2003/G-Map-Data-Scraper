"""Record every image prompt the Studio uses, and how it turned out

Each row is one image asked for: the prompt and its style, how the check
judged it (a sign that read back right or came out as gibberish), and what
the reviewer did with it. Later images are made from what worked.

Revision ID: a8f3c5d1e7b9
Revises: f7d1b5c3e8a4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a8f3c5d1e7b9'
down_revision: Union[str, None] = 'f7d1b5c3e8a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'studio_image_prompts',
        sa.Column('prompt_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('template_id', sa.String(length=32), nullable=True),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('style', sa.String(length=20), nullable=False),
        sa.Column('language_code', sa.String(length=10), nullable=True),
        sa.Column('target_state', sa.String(length=100), nullable=True),
        sa.Column('scene', sa.Text(), nullable=True),
        sa.Column('phrase', sa.String(length=200), nullable=True),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=True),
        sa.Column('seed', sa.Integer(), nullable=True),
        sa.Column('media_id', sa.String(length=64), nullable=True),
        sa.Column('check', sa.JSON(), nullable=True),
        sa.Column('checked', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('passed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('gibberish', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('outcome', sa.String(length=20), nullable=False, server_default='unused'),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['template_id'], ['whatsapp_templates.template_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('prompt_id'),
    )
    op.create_index('ix_studio_image_prompts_created_at', 'studio_image_prompts', ['created_at'])
    op.create_index('ix_studio_image_prompts_template_id', 'studio_image_prompts', ['template_id'])


def downgrade() -> None:
    op.drop_index('ix_studio_image_prompts_template_id', table_name='studio_image_prompts')
    op.drop_index('ix_studio_image_prompts_created_at', table_name='studio_image_prompts')
    op.drop_table('studio_image_prompts')
