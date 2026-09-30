"""Flag automated hits on campaign tracking links

Adds whatsapp_link_clicks.automated_reason and fills it for the rows already
recorded, judged from their user agent by the same rules the redirect now
applies. Their request method was never stored, so a past HEAD request
cannot be recognised — only agents that name themselves as tools or bots.

Revision ID: c4a7e2d9b8f1
Revises: b2e9f7a4d3c5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'c4a7e2d9b8f1'
down_revision: Union[str, None] = 'b2e9f7a4d3c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('whatsapp_link_clicks', sa.Column('automated_reason', sa.String(length=80), nullable=True))
    op.create_index('ix_whatsapp_link_clicks_automated_reason', 'whatsapp_link_clicks', ['automated_reason'])

    from src.services.click_filter import automated_reason

    conn = op.get_bind()
    clicks = sa.table('whatsapp_link_clicks', sa.column('click_id'), sa.column('user_agent'),
                      sa.column('automated_reason'))
    for click_id, user_agent in conn.execute(sa.select(clicks.c.click_id, clicks.c.user_agent)).fetchall():
        reason = automated_reason(user_agent)
        if reason:
            conn.execute(clicks.update().where(clicks.c.click_id == click_id).values(automated_reason=reason))


def downgrade() -> None:
    op.drop_index('ix_whatsapp_link_clicks_automated_reason', table_name='whatsapp_link_clicks')
    op.drop_column('whatsapp_link_clicks', 'automated_reason')
