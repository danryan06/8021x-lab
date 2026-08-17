"""authz policy group binding

Revision ID: 20260817_0004
Revises: 20260801_0003
Create Date: 2026-08-17

Phase 3: an authorization policy can be bound to a user group so successful
PEAP/EAP-TLS logins receive the same reply attributes MAB endpoints get. The
group name is synced into FreeRADIUS `radgroupreply`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260817_0004"
down_revision: str | None = "20260801_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("authz_policies", sa.Column("group_name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("authz_policies", "group_name")
