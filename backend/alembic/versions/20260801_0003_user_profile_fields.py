"""Add RADIUS user profile fields (name, department).

Revision ID: 20260801_0003
Revises: 20260801_0002
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0003"
down_revision: Union[str, None] = "20260801_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("radius_users", sa.Column("first_name", sa.String(length=128), nullable=True))
    op.add_column("radius_users", sa.Column("last_name", sa.String(length=128), nullable=True))
    op.add_column("radius_users", sa.Column("department", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("radius_users", "department")
    op.drop_column("radius_users", "last_name")
    op.drop_column("radius_users", "first_name")
