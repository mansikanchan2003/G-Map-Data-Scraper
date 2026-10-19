"""Let an account's Inbox show only some chats

The team wanted an account (Amit Singh's) whose Inbox shows only the chats
that did not come from an AutoGMap campaign.

Revision ID: d6a2c8e4f1b7
Revises: c3f5a7b9d2e4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd6a2c8e4f1b7'
down_revision: Union[str, None] = 'c3f5a7b9d2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('inbox_scope', sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'inbox_scope')
