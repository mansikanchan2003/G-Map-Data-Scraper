"""Keep qualified and strongly qualified applicants for good

The team wanted every applicant who reached Qualified or Strongly qualified
kept, with why, when, where and the nearest SBI branch, even if they later
answer otherwise or are taken off the Applications tab.

Revision ID: b8e2d4f6a1c3
Revises: a7d3c1e9f4b2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b8e2d4f6a1c3'
down_revision: Union[str, None] = 'a7d3c1e9f4b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'qualified_leads',
        sa.Column('phone', sa.String(20), primary_key=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('level', sa.String(30), nullable=False),
        sa.Column('why', sa.JSON(), nullable=True),
        sa.Column('qualified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('strongly_qualified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pincode', sa.String(10), nullable=True),
        sa.Column('state', sa.String(100), nullable=True),
        sa.Column('district', sa.String(100), nullable=True),
        sa.Column('tehsil', sa.String(100), nullable=True),
        sa.Column('branch_code', sa.String(10), nullable=True),
        sa.Column('branch_name', sa.String(120), nullable=True),
        sa.Column('branch_ao', sa.String(60), nullable=True),
        sa.Column('branch_region', sa.String(20), nullable=True),
        sa.Column('branch_circle', sa.String(60), nullable=True),
        sa.Column('branch_distance_km', sa.Float(), nullable=True),
        sa.Column('branch_checked_pin', sa.String(10), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('qualified_leads')
