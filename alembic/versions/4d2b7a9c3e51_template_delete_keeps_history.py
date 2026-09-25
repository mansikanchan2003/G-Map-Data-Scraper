"""Let a template be deleted without destroying campaign history

A campaign referenced its template with a plain foreign key, so deleting a
template that had ever been used failed outright. Campaign history must
outlive the template, so the reference is cleared instead of blocking the
delete; the campaign detail view already handles a missing template.

Revision ID: 4d2b7a9c3e51
Revises: 3c1a8e5f7b22
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op


revision: str = '4d2b7a9c3e51'
down_revision: Union[str, None] = '3c1a8e5f7b22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint('whatsapp_campaigns_template_id_fkey', 'whatsapp_campaigns', type_='foreignkey')
    op.create_foreign_key(
        'whatsapp_campaigns_template_id_fkey',
        'whatsapp_campaigns', 'whatsapp_templates',
        ['template_id'], ['template_id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('whatsapp_campaigns_template_id_fkey', 'whatsapp_campaigns', type_='foreignkey')
    op.create_foreign_key(
        'whatsapp_campaigns_template_id_fkey',
        'whatsapp_campaigns', 'whatsapp_templates',
        ['template_id'], ['template_id'],
    )
