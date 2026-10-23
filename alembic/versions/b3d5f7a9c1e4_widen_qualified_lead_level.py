"""Room for "Not qualified for SBI branch code" in qualified_leads.level

A real PIN outside our SBI branch area no longer ends the journey; those
leads are kept with the qualified ones at this level, for another proposal.

Revision ID: b3d5f7a9c1e4
Revises: a1c3e5f7b9d2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3d5f7a9c1e4'
down_revision: Union[str, None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('qualified_leads') as batch:
        batch.alter_column('level', type_=sa.String(60), existing_type=sa.String(30), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('qualified_leads') as batch:
        batch.alter_column('level', type_=sa.String(30), existing_type=sa.String(60), existing_nullable=False)
