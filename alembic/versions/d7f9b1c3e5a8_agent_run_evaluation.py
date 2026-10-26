"""What AutoGMap's own checkers found in each agent run (the evaluator)

Revision ID: d7f9b1c3e5a8
Revises: c5e7a9b1d3f6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd7f9b1c3e5a8'
down_revision: Union[str, None] = 'c5e7a9b1d3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('agent_runs', sa.Column('evaluation', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_runs', 'evaluation')
