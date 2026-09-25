"""Add Meta billing category to whatsapp_templates

Meta assigns the category (UTILITY / MARKETING / MARKETING_LITE) at review
time, and it can differ from what was requested at submission, so it is stored
as reported by Meta rather than as requested.

Revision ID: 3c1a8e5f7b22
Revises: 2b9f4c7d1e88
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3c1a8e5f7b22'
down_revision: Union[str, None] = '2b9f4c7d1e88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('whatsapp_templates', sa.Column('category', sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column('whatsapp_templates', 'category')
