"""Add the app_settings key/value store

Holds values the application produces at runtime rather than reads from the
environment — starting with the id of the live Google Sheet, which is created
on first export and must survive a restart.

Revision ID: 7a5e3c1b9d64
Revises: 6f4d2e9b5a83
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '7a5e3c1b9d64'
down_revision: Union[str, None] = '6f4d2e9b5a83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_index('ix_app_settings_key', 'app_settings', ['key'])


def downgrade() -> None:
    op.drop_index('ix_app_settings_key', table_name='app_settings')
    op.drop_table('app_settings')
