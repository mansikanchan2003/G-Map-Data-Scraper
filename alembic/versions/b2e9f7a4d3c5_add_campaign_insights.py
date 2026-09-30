"""Add campaign insights and playbook snapshots

Per-campaign success reports, and a dated record of what the playbook
concluded after each campaign.

Revision ID: b2e9f7a4d3c5
Revises: a1d8e6f3c2b4
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2e9f7a4d3c5'
down_revision: Union[str, None] = 'a1d8e6f3c2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'campaign_insights',
        sa.Column('campaign_id', sa.String(length=32), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('breakdowns', sa.JSON(), nullable=True),
        sa.Column('suggestions', sa.JSON(), nullable=True),
        sa.Column('vs_all_campaigns', sa.Float(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['whatsapp_campaigns.campaign_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('campaign_id'),
    )
    op.create_table(
        'insight_snapshots',
        sa.Column('snapshot_id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('trigger', sa.String(length=40), nullable=False),
        sa.Column('campaign_id', sa.String(length=32), nullable=True),
        sa.Column('campaigns', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('recipients', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('responses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('playbook', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['whatsapp_campaigns.campaign_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('snapshot_id'),
    )
    op.create_index('ix_insight_snapshots_created_at', 'insight_snapshots', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_insight_snapshots_created_at', table_name='insight_snapshots')
    op.drop_table('insight_snapshots')
    op.drop_table('campaign_insights')
