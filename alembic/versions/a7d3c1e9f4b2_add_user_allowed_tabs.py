"""Let an account see only some tabs

An account can be given a list of tabs narrower than its role's: the team
wanted a manager to see only the Inbox, Applications, Campaign History and
Campaign Insights.

Revision ID: a7d3c1e9f4b2
Revises: f5c9e2a7b3d1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a7d3c1e9f4b2'
down_revision: Union[str, None] = 'f5c9e2a7b3d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('allowed_tabs', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'allowed_tabs')
