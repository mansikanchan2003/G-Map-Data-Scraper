"""Add the users table

Access is two gates, not one: the email domain decides who may ask, and an
admin decides who gets in. status carries the second gate.

Revision ID: 8b6f4d2a1c95
Revises: 7a5e3c1b9d64
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8b6f4d2a1c95'
down_revision: Union[str, None] = '7a5e3c1b9d64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False),
        sa.Column('full_name', sa.String(length=200), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='PENDING'),
        sa.Column('decided_by', sa.String(length=200), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.String(length=500), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('user_id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_user_id', 'users', ['user_id'])
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_status', 'users', ['status'])


def downgrade() -> None:
    op.drop_index('ix_users_status', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_user_id', table_name='users')
    op.drop_table('users')
