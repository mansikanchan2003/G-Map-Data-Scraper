"""Keep real photographs of CSPs for the Template Studio's posters

The AI photos looked AI-made and showed no SBI Customer Service Point, so the
team uploads real ones, with the consent of the people in them, and posters
are set on those first.

Revision ID: a4c6e8f0b2d7
Revises: e7b3d9f1a2c5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a4c6e8f0b2d7'
down_revision: Union[str, None] = 'e7b3d9f1a2c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'studio_real_photos',
        sa.Column('photo_id', sa.String(32), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('media_id', sa.String(64), nullable=False),
        sa.Column('state', sa.String(100), nullable=True, index=True),
        sa.Column('note', sa.String(300), nullable=True),
        sa.Column('uploaded_by', sa.String(255), nullable=True),
        sa.Column('consent', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('times_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('studio_real_photos')
