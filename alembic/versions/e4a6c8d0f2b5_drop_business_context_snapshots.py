"""Drop business_context_snapshots: Tara's data stays on Sumit's server

Tara already keeps its own data; AutoGMap only reads what the Goal section
needs each day (the user, 2026-10-22). The table from d2f4a6b8c0e3 goes,
whether or not that migration ran on a server.

Revision ID: e4a6c8d0f2b5
Revises: d2f4a6b8c0e3
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'e4a6c8d0f2b5'
down_revision: Union[str, None] = 'd2f4a6b8c0e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS business_context_snapshots")


def downgrade() -> None:
    pass
