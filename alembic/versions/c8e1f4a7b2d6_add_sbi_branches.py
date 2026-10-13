"""Add SBI branches, shown against their PIN codes on the Configuration page

Revision ID: c8e1f4a7b2d6
Revises: b7e4d2c9a1f5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8e1f4a7b2d6'
down_revision: Union[str, None] = 'b7e4d2c9a1f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sbi_branches',
        sa.Column('branch_code', sa.String(length=10), nullable=False),
        sa.Column('branch_name', sa.String(length=120), nullable=False),
        sa.Column('ifsc', sa.String(length=11), nullable=True),
        sa.Column('pincode', sa.String(length=10), nullable=False),
        sa.Column('town', sa.String(length=120), nullable=True),
        sa.Column('district', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=100), nullable=True),
        sa.Column('tehsil', sa.String(length=100), nullable=True),
        sa.Column('address', sa.String(length=300), nullable=True),
        sa.Column('circle', sa.String(length=60), nullable=True),
        sa.Column('network', sa.String(length=20), nullable=True),
        sa.Column('module', sa.String(length=60), nullable=True),
        sa.Column('region', sa.String(length=20), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('branch_code'),
    )
    op.create_index('ix_sbi_branches_pincode', 'sbi_branches', ['pincode'])


def downgrade() -> None:
    op.drop_index('ix_sbi_branches_pincode', table_name='sbi_branches')
    op.drop_table('sbi_branches')
