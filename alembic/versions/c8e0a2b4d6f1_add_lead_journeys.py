"""Keep every lead's journey in the database, to query with SQL

The journey (lead_journey.py) is read from the chats; these two tables hold
it, refreshed every 15 minutes: one row per lead with the date of each
stage, and one row per step with what the lead did and what we did next.

Revision ID: c8e0a2b4d6f1
Revises: b6d8f0a2c4e9
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c8e0a2b4d6f1'
down_revision: Union[str, None] = 'b6d8f0a2c4e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lead_journeys',
        sa.Column('phone', sa.String(20), sa.ForeignKey('whatsapp_conversations.phone', ondelete='CASCADE'),
                  primary_key=True),
        sa.Column('name', sa.String(200), nullable=True),
        sa.Column('outcome', sa.String(20), nullable=False, index=True),
        sa.Column('furthest_stage', sa.String(30), nullable=True),
        sa.Column('furthest_index', sa.Integer(), nullable=False, server_default='-1'),
        sa.Column('disposition', sa.String(40), nullable=True),
        sa.Column('disposition_label', sa.String(120), nullable=True),
        *[sa.Column(f'{stage}_at', sa.DateTime(timezone=True), nullable=True)
          for stage in ('campaign', 'interested', 'language', 'pin', 'education', 'investment', 'docs_ready',
                        'uploaded', 'handed_over')],
        sa.Column('last_step', sa.String(300), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('steps_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'lead_journey_steps',
        sa.Column('step_id', sa.String(40), primary_key=True),
        sa.Column('phone', sa.String(20), sa.ForeignKey('whatsapp_conversations.phone', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(10), nullable=False),
        sa.Column('key', sa.String(60), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('what', sa.String(500), nullable=True),
        sa.Column('action', sa.String(500), nullable=True),
        sa.Column('action_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('by', sa.String(200), nullable=True),
        sa.Column('tone', sa.String(12), nullable=True),
        sa.Column('detail', sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('lead_journey_steps')
    op.drop_table('lead_journeys')
