"""An append-only audit log, and who launched and approved each campaign

Revision ID: b5d7f9a1c3e6
Revises: a3c5e7f9b1d4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b5d7f9a1c3e6'
down_revision: Union[str, None] = 'a3c5e7f9b1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('actor', sa.String(length=200), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=True),
        sa.Column('action', sa.String(length=120), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('path', sa.String(length=300), nullable=False),
        sa.Column('status', sa.Integer(), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=True),
    )
    op.create_index('ix_audit_log_at', 'audit_log', ['at'])
    op.create_index('ix_audit_log_actor', 'audit_log', ['actor'])
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])

    if op.get_bind().dialect.name == 'postgresql':
        # Append-only: no update or delete, whoever asks.
        op.execute("""
            CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_log is append-only';
            END;
            $$ LANGUAGE plpgsql;
        """)
        op.execute("""
            CREATE TRIGGER audit_log_no_change BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
        """)

    op.add_column('whatsapp_campaigns', sa.Column('created_by', sa.String(length=200), nullable=True))
    op.add_column('whatsapp_campaigns', sa.Column('approved_by', sa.String(length=200), nullable=True))
    op.add_column('whatsapp_campaigns', sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('whatsapp_campaigns', sa.Column('review_note', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('whatsapp_campaigns', 'review_note')
    op.drop_column('whatsapp_campaigns', 'approved_at')
    op.drop_column('whatsapp_campaigns', 'approved_by')
    op.drop_column('whatsapp_campaigns', 'created_by')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_change ON audit_log")
        op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
    op.drop_table('audit_log')
