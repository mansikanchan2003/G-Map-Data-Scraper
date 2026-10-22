"""Keep AutoGMap's calculated views in tables, to query with SQL

The action items queue, the disposition mix, the Dashboard alerts, and per
day the dispositions, the shared number's use and the lead goal. Written by
report_store.py every 15 minutes, with the lead journeys.

Revision ID: f6b8d0e2a4c7
Revises: e4a6c8d0f2b5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f6b8d0e2a4c7'
down_revision: Union[str, None] = 'e4a6c8d0f2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'action_items',
        sa.Column('item_id', sa.String(64), primary_key=True),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('owner', sa.String(30), nullable=False, index=True),
        sa.Column('owner_label', sa.String(300), nullable=True),
        sa.Column('text', sa.String(500), nullable=True),
        sa.Column('result', sa.String(300), nullable=True),
        sa.Column('disposition_label', sa.String(120), nullable=True),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('bucket', sa.String(10), nullable=False, index=True),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'disposition_mix',
        sa.Column('row_id', sa.String(64), primary_key=True),
        sa.Column('dimension', sa.String(20), nullable=False, index=True),
        sa.Column('value', sa.String(255), nullable=False),
        sa.Column('disposition_label', sa.String(120), nullable=False),
        sa.Column('group', sa.String(20), nullable=True),
        sa.Column('leads', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('replied', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'disposition_daily',
        sa.Column('day', sa.Date(), primary_key=True),
        sa.Column('disposition', sa.String(60), primary_key=True),
        sa.Column('disposition_label', sa.String(120), nullable=True),
        sa.Column('category', sa.String(40), nullable=True),
        sa.Column('group', sa.String(20), nullable=True),
        sa.Column('chats', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'number_usage_daily',
        sa.Column('day', sa.Date(), primary_key=True),
        sa.Column('autogmap', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('others', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('others_by_category', sa.JSON(), nullable=True),
        sa.Column('others_delivered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('others_read', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('others_cost_inr', sa.Float(), nullable=False, server_default='0'),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'goal_daily',
        sa.Column('day', sa.Date(), primary_key=True),
        sa.Column('target', sa.Integer(), nullable=True),
        sa.Column('leads', sa.Integer(), nullable=True),
        sa.Column('still_needed', sa.Integer(), nullable=True),
        sa.Column('days_left', sa.Integer(), nullable=True),
        sa.Column('on_track', sa.Boolean(), nullable=True),
        sa.Column('messages_sent', sa.Integer(), nullable=True),
        sa.Column('leads_per_1000', sa.Float(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'lead_alerts',
        sa.Column('alert_id', sa.String(64), primary_key=True),
        sa.Column('check', sa.String(40), nullable=False, index=True),
        sa.Column('label', sa.String(200), nullable=True),
        sa.Column('severity', sa.String(20), nullable=True),
        sa.Column('group', sa.String(40), nullable=True, index=True),
        sa.Column('phone', sa.String(20), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('detail', sa.String(500), nullable=True),
        sa.Column('refreshed_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table in ('lead_alerts', 'goal_daily', 'number_usage_daily', 'disposition_daily', 'disposition_mix',
                  'action_items'):
        op.drop_table(table)
