"""Posters the team likes, as style references for the Template Studio's agents

Revision ID: e9b1d3f5a7c2
Revises: d7f9b1c3e5a8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e9b1d3f5a7c2'
down_revision: Union[str, None] = 'd7f9b1c3e5a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'studio_reference_posters',
        sa.Column('poster_id', sa.String(length=32), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('media_id', sa.String(length=64), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('uploaded_by', sa.String(length=255), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('style', sa.JSON(), nullable=True),
        sa.Column('palette', sa.JSON(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('read_error', sa.String(length=300), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('studio_reference_posters')
