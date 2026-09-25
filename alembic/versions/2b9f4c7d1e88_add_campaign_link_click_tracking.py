"""Add campaign link click tracking

WhatsApp does not report clicks on links written in a message body, and a URL
that is identical for every recipient cannot attribute a visit to a person.
Each recipient therefore gets an opaque token, and real clicks on the redirect
endpoint are recorded here.

Revision ID: 2b9f4c7d1e88
Revises: 1a7c3b9e2d40
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2b9f4c7d1e88'
down_revision: Union[str, None] = '1a7c3b9e2d40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'whatsapp_campaign_recipients',
        sa.Column('tracking_token', sa.String(length=32), nullable=True),
    )
    op.create_index(
        'ix_whatsapp_campaign_recipients_tracking_token',
        'whatsapp_campaign_recipients',
        ['tracking_token'],
        unique=True,
    )

    op.create_table(
        'whatsapp_link_clicks',
        sa.Column('click_id', sa.String(length=32), nullable=False),
        sa.Column('campaign_id', sa.String(length=32), nullable=False),
        sa.Column('recipient_id', sa.String(length=32), nullable=True),
        sa.Column('target_url', sa.Text(), nullable=False),
        sa.Column('ip_hash', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('clicked_at', sa.DateTime(timezone=True),
                  server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['whatsapp_campaigns.campaign_id']),
        sa.ForeignKeyConstraint(['recipient_id'], ['whatsapp_campaign_recipients.recipient_id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('click_id'),
    )
    op.create_index('ix_whatsapp_link_clicks_click_id', 'whatsapp_link_clicks', ['click_id'])
    op.create_index('ix_whatsapp_link_clicks_campaign_id', 'whatsapp_link_clicks', ['campaign_id'])
    op.create_index('ix_whatsapp_link_clicks_recipient_id', 'whatsapp_link_clicks', ['recipient_id'])
    op.create_index('ix_whatsapp_link_clicks_clicked_at', 'whatsapp_link_clicks', ['clicked_at'])


def downgrade() -> None:
    op.drop_table('whatsapp_link_clicks')
    op.drop_index('ix_whatsapp_campaign_recipients_tracking_token',
                  table_name='whatsapp_campaign_recipients')
    op.drop_column('whatsapp_campaign_recipients', 'tracking_token')
