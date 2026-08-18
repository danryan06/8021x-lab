"""authz policy conditions (Login-Time + NAS-IP-Address)

Revision ID: 20260818_0005
Revises: 20260817_0004
Create Date: 2026-08-18

Phase 3 leftover: an authorization policy can restrict when and from which NAS
it applies. Stored as JSONB on authz_policies; synced into radcheck /
radgroupcheck as Login-Time and NAS-IP-Address check items.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260818_0005"
down_revision: str | None = "20260817_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "authz_policies",
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("authz_policies", "conditions")
