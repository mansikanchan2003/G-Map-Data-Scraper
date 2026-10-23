"""Say what the messages the inbox could not show were

Messages WhatsApp does not pass on (polls, view-once photos, edited or
deleted messages) arrive as "unsupported" and were shown as "a message type
this inbox cannot show". They now say what they can be; earlier ones too.

Revision ID: a1c3e5f7b9d2
Revises: f6b8d0e2a4c7
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, None] = 'f6b8d0e2a4c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "[A message type this inbox cannot show]"
UNSUPPORTED = ("[WhatsApp did not pass this message on: it can be a poll, a view-once photo or video, an edited "
               "or deleted message, or something newer. Ask them to send it again as a normal message]")


def upgrade() -> None:
    update = sa.text("UPDATE whatsapp_messages SET body = :new WHERE kind = :kind AND body = :old")
    op.get_bind().execute(update, {"new": UNSUPPORTED, "kind": "unsupported", "old": OLD})
    op.get_bind().execute(update, {"new": "[Opened a chat with us for the first time]", "kind": "request_welcome",
                                   "old": OLD})


def downgrade() -> None:
    pass
