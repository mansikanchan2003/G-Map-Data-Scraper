"""Record when a user's password was last changed, and a reset code

Sessions issued before the change stop working, so changing a password
signs out anyone who was signed in with the old one. The reset code is the
one emailed for a forgotten password: its hash, when it was sent, and how
many wrong guesses it has had.

Revision ID: f7d1b5c3e8a4
Revises: e6c9a4b2d7f3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f7d1b5c3e8a4'
down_revision: Union[str, None] = 'e6c9a4b2d7f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('reset_code_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('reset_code_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('reset_code_attempts', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('users', 'reset_code_attempts')
    op.drop_column('users', 'reset_code_sent_at')
    op.drop_column('users', 'reset_code_hash')
    op.drop_column('users', 'password_changed_at')
