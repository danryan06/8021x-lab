"""initial schema

Revision ID: 20260731_0001
Revises:
Create Date: 2026-07-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260731_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create ENUM types once. Column definitions below use create_type=False so
    # create_table does not attempt a second CREATE TYPE (Postgres DuplicateObject).
    user_status = postgresql.ENUM(
        "active", "disabled", "expired", name="user_status", create_type=False
    )
    cert_type = postgresql.ENUM(
        "root_ca", "intermediate_ca", "client", "server", name="cert_type", create_type=False
    )
    cert_status = postgresql.ENUM(
        "pending", "active", "revoked", "expired", name="cert_status", create_type=False
    )
    auth_method = postgresql.ENUM(
        "peap", "eap_tls", "mab", "unknown", name="auth_method", create_type=False
    )
    auth_result = postgresql.ENUM(
        "success", "failure", "challenge", name="auth_result", create_type=False
    )

    bind = op.get_bind()
    for enum in (user_status, cert_type, cert_status, auth_method, auth_result):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "labs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "authz_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("reply_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("vlan", sa.Integer(), nullable=True),
        sa.Column("role", sa.String(length=128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "auth_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("method", auth_method, nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_identities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "radius_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("nt_hash", sa.String(length=64), nullable=True),
        sa.Column("groups", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", user_status, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_radius_users_username", "radius_users", ["username"])

    op.create_table(
        "endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("mac_address", sa.String(length=17), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("device_type", sa.String(length=64), nullable=True),
        sa.Column(
            "authz_policy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("authz_policies.id"),
            nullable=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_endpoints_mac_address", "endpoints", ["mac_address"])

    op.create_table(
        "certificate_authorities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("adapter", sa.String(length=64), nullable=False),
        sa.Column("storage_ref", sa.String(length=512), nullable=True),
        sa.Column("profiles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "certificates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column(
            "authority_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("certificate_authorities.id"),
            nullable=True,
        ),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=True),
        sa.Column("serial", sa.String(length=128), nullable=True),
        sa.Column("cert_type", cert_type, nullable=False),
        sa.Column("status", cert_status, nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("storage_ref", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "radius_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("shared_secret", sa.String(length=256), nullable=False),
        sa.Column("device_type", sa.String(length=64), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "authentication_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lab_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labs.id"), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("identity", sa.String(length=255), nullable=True),
        sa.Column("method", auth_method, nullable=False),
        sa.Column("result", auth_result, nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("returned_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("nas_ip", sa.String(length=64), nullable=True),
        sa.Column("raw_ref", sa.Text(), nullable=True),
    )
    op.create_index("ix_authentication_events_timestamp", "authentication_events", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_authentication_events_timestamp", table_name="authentication_events")
    op.drop_table("authentication_events")
    op.drop_table("radius_clients")
    op.drop_table("certificates")
    op.drop_table("certificate_authorities")
    op.drop_index("ix_endpoints_mac_address", table_name="endpoints")
    op.drop_table("endpoints")
    op.drop_index("ix_radius_users_username", table_name="radius_users")
    op.drop_table("radius_users")
    op.drop_table("auth_policies")
    op.drop_table("authz_policies")
    op.drop_table("labs")

    bind = op.get_bind()
    for name in ("auth_result", "auth_method", "cert_status", "cert_type", "user_status"):
        postgresql.ENUM(name=name, create_type=False).drop(bind, checkfirst=True)
