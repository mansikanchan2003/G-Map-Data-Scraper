"""Add the WhatsApp inbox: conversations, messages and onboarding documents

Every message to and from the business number, the onboarding bot's place in
each conversation, and the documents people upload through the link it sends.
Button taps and replies recorded before this are copied in at startup.

Revision ID: b7e4d2c9a1f5
Revises: a8f3c5d1e7b9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e4d2c9a1f5'
down_revision: Union[str, None] = 'a8f3c5d1e7b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'whatsapp_conversations',
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('profile_name', sa.String(length=200), nullable=True),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_inbound_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bot_step', sa.String(length=40), nullable=True),
        sa.Column('bot_data', sa.JSON(), nullable=True),
        sa.Column('bot_paused', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('bot_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('upload_token', sa.String(length=64), nullable=True),
        sa.Column('upload_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('documents_submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('drive_folder_url', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('phone'),
    )
    op.create_index('ix_whatsapp_conversations_phone', 'whatsapp_conversations', ['phone'])
    op.create_index('ix_whatsapp_conversations_last_message_at', 'whatsapp_conversations', ['last_message_at'])
    op.create_index('ix_whatsapp_conversations_bot_step', 'whatsapp_conversations', ['bot_step'])
    op.create_index('ix_whatsapp_conversations_upload_token', 'whatsapp_conversations', ['upload_token'], unique=True)

    op.create_table(
        'whatsapp_messages',
        sa.Column('message_id', sa.String(length=32), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('direction', sa.String(length=3), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('provider_message_id', sa.String(length=100), nullable=True),
        sa.Column('context_id', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('error_reason', sa.String(length=500), nullable=True),
        sa.Column('sent_by', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('message_id'),
        sa.ForeignKeyConstraint(['phone'], ['whatsapp_conversations.phone'], ondelete='CASCADE'),
    )
    op.create_index('ix_whatsapp_messages_message_id', 'whatsapp_messages', ['message_id'])
    op.create_index('ix_whatsapp_messages_phone', 'whatsapp_messages', ['phone'])
    op.create_index('ix_whatsapp_messages_created_at', 'whatsapp_messages', ['created_at'])
    op.create_index('ix_whatsapp_messages_provider_message_id', 'whatsapp_messages',
                    ['provider_message_id'], unique=True)

    op.create_table(
        'onboarding_documents',
        sa.Column('document_id', sa.String(length=32), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('doc_type', sa.String(length=40), nullable=False),
        sa.Column('original_name', sa.String(length=255), nullable=True),
        sa.Column('stored_path', sa.String(length=500), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('drive_file_id', sa.String(length=100), nullable=True),
        sa.Column('drive_url', sa.String(length=500), nullable=True),
        sa.Column('drive_error', sa.String(length=500), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('document_id'),
        sa.ForeignKeyConstraint(['phone'], ['whatsapp_conversations.phone'], ondelete='CASCADE'),
    )
    op.create_index('ix_onboarding_documents_document_id', 'onboarding_documents', ['document_id'])
    op.create_index('ix_onboarding_documents_phone', 'onboarding_documents', ['phone'])


def downgrade() -> None:
    op.drop_index('ix_onboarding_documents_phone', table_name='onboarding_documents')
    op.drop_index('ix_onboarding_documents_document_id', table_name='onboarding_documents')
    op.drop_table('onboarding_documents')
    op.drop_index('ix_whatsapp_messages_provider_message_id', table_name='whatsapp_messages')
    op.drop_index('ix_whatsapp_messages_created_at', table_name='whatsapp_messages')
    op.drop_index('ix_whatsapp_messages_phone', table_name='whatsapp_messages')
    op.drop_index('ix_whatsapp_messages_message_id', table_name='whatsapp_messages')
    op.drop_table('whatsapp_messages')
    op.drop_index('ix_whatsapp_conversations_upload_token', table_name='whatsapp_conversations')
    op.drop_index('ix_whatsapp_conversations_bot_step', table_name='whatsapp_conversations')
    op.drop_index('ix_whatsapp_conversations_last_message_at', table_name='whatsapp_conversations')
    op.drop_index('ix_whatsapp_conversations_phone', table_name='whatsapp_conversations')
    op.drop_table('whatsapp_conversations')
