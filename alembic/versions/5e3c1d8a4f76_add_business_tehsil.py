"""Add tehsil to businesses and backfill it from the discovering location

Campaign audiences are selected by state / district / tehsil. District and
state were already mirrored onto the business row; tehsil lived only on
locations, which meant filtering by it required joining back through jobs.

Revision ID: 5e3c1d8a4f76
Revises: 4d2b7a9c3e51
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5e3c1d8a4f76'
down_revision: Union[str, None] = '4d2b7a9c3e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('businesses', sa.Column('tehsil', sa.String(length=100), nullable=True))
    op.create_index('ix_businesses_tehsil', 'businesses', ['tehsil'])

    # Existing rows know which job found them, and a job knows its location.
    op.execute("""
        UPDATE businesses b
        SET tehsil = l.tehsil
        FROM jobs j
        JOIN locations l ON l.location_id = j.location_id
        WHERE j.job_id = b.job_id AND b.tehsil IS NULL
    """)


def downgrade() -> None:
    op.drop_index('ix_businesses_tehsil', table_name='businesses')
    op.drop_column('businesses', 'tehsil')
