from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UserStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"
    expired = "expired"


class CertStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    revoked = "revoked"
    expired = "expired"


class CertType(str, enum.Enum):
    root_ca = "root_ca"
    intermediate_ca = "intermediate_ca"
    client = "client"
    server = "server"


class AuthMethod(str, enum.Enum):
    peap = "peap"
    eap_tls = "eap_tls"
    mab = "mab"
    unknown = "unknown"


class AuthResult(str, enum.Enum):
    success = "success"
    failure = "failure"
    challenge = "challenge"


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    users: Mapped[list[RadiusUser]] = relationship(back_populates="lab")
    clients: Mapped[list[RadiusClient]] = relationship(back_populates="lab")
    endpoints: Mapped[list[Endpoint]] = relationship(back_populates="lab")
    certificate_authorities: Mapped[list[CertificateAuthority]] = relationship(back_populates="lab")
    certificates: Mapped[list[Certificate]] = relationship(back_populates="lab")
    auth_policies: Mapped[list[AuthPolicy]] = relationship(back_populates="lab")
    authz_policies: Mapped[list[AuthzPolicy]] = relationship(back_populates="lab")
    events: Mapped[list[AuthenticationEvent]] = relationship(back_populates="lab")


class RadiusUser(Base):
    """RADIUS / lab identity (distinct from the web admin account)."""

    __tablename__ = "radius_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # FreeRADIUS NT-Password value (0x + hex). Never log this value.
    nt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    groups: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), nullable=False, default=UserStatus.active
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lab: Mapped[Lab] = relationship(back_populates="users")


class Endpoint(Base):
    __tablename__ = "endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    mac_address: Mapped[str] = mapped_column(String(17), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    authz_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("authz_policies.id"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lab: Mapped[Lab] = relationship(back_populates="endpoints")


class CertificateAuthority(Base):
    __tablename__ = "certificate_authorities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    adapter: Mapped[str] = mapped_column(String(64), nullable=False, default="openssl")
    storage_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    profiles: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lab: Mapped[Lab] = relationship(back_populates="certificate_authorities")
    certificates: Mapped[list[Certificate]] = relationship(back_populates="authority")


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("certificate_authorities.id"), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(512), nullable=True)
    serial: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cert_type: Mapped[CertType] = mapped_column(Enum(CertType, name="cert_type"), nullable=False)
    status: Mapped[CertStatus] = mapped_column(
        Enum(CertStatus, name="cert_status"), nullable=False, default=CertStatus.pending
    )
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    storage_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lab: Mapped[Lab] = relationship(back_populates="certificates")
    authority: Mapped[CertificateAuthority | None] = relationship(back_populates="certificates")


class AuthPolicy(Base):
    __tablename__ = "auth_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    method: Mapped[AuthMethod] = mapped_column(Enum(AuthMethod, name="auth_method"), nullable=False)
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    allowed_identities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lab: Mapped[Lab] = relationship(back_populates="auth_policies")


class AuthzPolicy(Base):
    __tablename__ = "authz_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    reply_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    vlan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Optional user group this policy authorizes (mirrors radius_users.groups →
    # radusergroup), so PEAP/EAP-TLS logins can receive the same attributes as MAB.
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lab: Mapped[Lab] = relationship(back_populates="authz_policies")


class RadiusClient(Base):
    __tablename__ = "radius_clients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("labs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    shared_secret: Mapped[str] = mapped_column(String(256), nullable=False)
    device_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lab: Mapped[Lab] = relationship(back_populates="clients")


class AuthenticationEvent(Base):
    __tablename__ = "authentication_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lab_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("labs.id"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[AuthMethod] = mapped_column(
        Enum(AuthMethod, name="auth_method"),
        nullable=False,
        default=AuthMethod.unknown,
    )
    result: Mapped[AuthResult] = mapped_column(
        Enum(AuthResult, name="auth_result"), nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    returned_attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    nas_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    lab: Mapped[Lab | None] = relationship(back_populates="events")
