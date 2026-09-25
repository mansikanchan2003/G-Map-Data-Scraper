"""Add meta_template_name and language_code to whatsapp_templates

Meta resolves a template send by (name, language) against the templates
APPROVED in the WhatsApp Business Account. Local templates carry their own
display name, which is not necessarily the registered Meta name, so the
Meta-side name and the approved language are stored explicitly.

Revision ID: 1a7c3b9e2d40
Revises: 0e08654b0f18
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a7c3b9e2d40'
down_revision: Union[str, None] = '0e08654b0f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'whatsapp_templates',
        sa.Column('meta_template_name', sa.String(length=200), nullable=True),
    )
    op.add_column(
        'whatsapp_templates',
        sa.Column('language_code', sa.String(length=20), nullable=False,
                  server_default='en_US'),
    )


def downgrade() -> None:
    op.drop_column('whatsapp_templates', 'language_code')
    op.drop_column('whatsapp_templates', 'meta_template_name')
