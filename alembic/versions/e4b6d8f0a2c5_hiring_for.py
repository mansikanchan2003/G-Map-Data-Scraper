"""Who a search hires for: CSP, District Coordinator or State Head (13 Nov 2026)

jobs.hiring_for, and businesses.for_csp / for_dc / for_state_head. Every job and
business before this is CSP.

Revision ID: e4b6d8f0a2c5
Revises: d2f4a6c8e0b1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e4b6d8f0a2c5'
down_revision: Union[str, None] = 'd2f4a6c8e0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('jobs', sa.Column('hiring_for', sa.String(length=20), nullable=False, server_default='CSP'))
    op.create_index('ix_jobs_hiring_for', 'jobs', ['hiring_for'])
    for col, default in (('for_csp', sa.true()), ('for_dc', sa.false()), ('for_state_head', sa.false())):
        op.add_column('businesses', sa.Column(col, sa.Boolean(), nullable=False, server_default=default))
        op.create_index(f'ix_businesses_{col}', 'businesses', [col])


def downgrade() -> None:
    for col in ('for_state_head', 'for_dc', 'for_csp'):
        op.drop_index(f'ix_businesses_{col}', table_name='businesses')
        op.drop_column('businesses', col)
    op.drop_index('ix_jobs_hiring_for', table_name='jobs')
    op.drop_column('jobs', 'hiring_for')
