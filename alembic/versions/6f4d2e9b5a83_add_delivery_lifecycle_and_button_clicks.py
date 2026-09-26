"""Record the delivery lifecycle and quick-reply button taps

A recipient's delivery stages accumulate — a message that was read was also
delivered — so they are stored as timestamps. Held in the single `status`
column, READ overwrites DELIVERED and the delivered count can never be
recovered.

Existing rows are backfilled only where the fact is already known: a row that
reached SENT was sent at its last update, and a FAILED row failed then. Nothing
invents a delivered or read time, because Meta does not replay webhooks for
messages already sent.

Revision ID: 6f4d2e9b5a83
Revises: 5e3c1d8a4f76
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '6f4d2e9b5a83'
down_revision: Union[str, None] = '5e3c1d8a4f76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('whatsapp_campaign_recipients', sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('whatsapp_campaign_recipients', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('whatsapp_campaign_recipients', sa.Column('read_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('whatsapp_campaign_recipients', sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('whatsapp_campaign_recipients', sa.Column('failure_code', sa.String(length=50), nullable=True))

    # The webhook looks recipients up by this id on every status event.
    op.create_index(
        'ix_whatsapp_campaign_recipients_provider_message_id',
        'whatsapp_campaign_recipients', ['provider_message_id'],
    )

    op.execute("""
        UPDATE whatsapp_campaign_recipients
           SET sent_at = updated_at
         WHERE sent_at IS NULL
           AND status IN ('SENT', 'DELIVERED', 'READ')
    """)
    op.execute("""
        UPDATE whatsapp_campaign_recipients
           SET failed_at = updated_at
         WHERE failed_at IS NULL
           AND status = 'FAILED'
    """)

    op.create_table(
        'whatsapp_button_clicks',
        sa.Column('click_id', sa.String(length=32), nullable=False),
        sa.Column('campaign_id', sa.String(length=32), nullable=False),
        sa.Column('recipient_id', sa.String(length=32), nullable=True),
        sa.Column('button_text', sa.String(length=200), nullable=True),
        sa.Column('button_payload', sa.String(length=500), nullable=True),
        sa.Column('provider_message_id', sa.String(length=100), nullable=True),
        sa.Column('clicked_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['campaign_id'], ['whatsapp_campaigns.campaign_id']),
        sa.ForeignKeyConstraint(['recipient_id'], ['whatsapp_campaign_recipients.recipient_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('click_id'),
    )
    op.create_index('ix_whatsapp_button_clicks_click_id', 'whatsapp_button_clicks', ['click_id'])
    op.create_index('ix_whatsapp_button_clicks_campaign_id', 'whatsapp_button_clicks', ['campaign_id'])
    op.create_index('ix_whatsapp_button_clicks_recipient_id', 'whatsapp_button_clicks', ['recipient_id'])
    op.create_index('ix_whatsapp_button_clicks_clicked_at', 'whatsapp_button_clicks', ['clicked_at'])
    # Meta redelivers a webhook until it is acknowledged, so the inbound id is
    # unique: the same tap must not be counted twice.
    op.create_index(
        'ix_whatsapp_button_clicks_provider_message_id',
        'whatsapp_button_clicks', ['provider_message_id'], unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_whatsapp_button_clicks_provider_message_id', table_name='whatsapp_button_clicks')
    op.drop_index('ix_whatsapp_button_clicks_clicked_at', table_name='whatsapp_button_clicks')
    op.drop_index('ix_whatsapp_button_clicks_recipient_id', table_name='whatsapp_button_clicks')
    op.drop_index('ix_whatsapp_button_clicks_campaign_id', table_name='whatsapp_button_clicks')
    op.drop_index('ix_whatsapp_button_clicks_click_id', table_name='whatsapp_button_clicks')
    op.drop_table('whatsapp_button_clicks')

    op.drop_index('ix_whatsapp_campaign_recipients_provider_message_id',
                  table_name='whatsapp_campaign_recipients')
    op.drop_column('whatsapp_campaign_recipients', 'failure_code')
    op.drop_column('whatsapp_campaign_recipients', 'failed_at')
    op.drop_column('whatsapp_campaign_recipients', 'read_at')
    op.drop_column('whatsapp_campaign_recipients', 'delivered_at')
    op.drop_column('whatsapp_campaign_recipients', 'sent_at')
