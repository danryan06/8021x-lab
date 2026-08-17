from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.entities import AuthMethod, AuthResult, UserStatus


class LabBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    settings: dict = Field(default_factory=dict)


class LabCreate(LabBase):
    pass


class LabUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    settings: dict | None = None


class LabRead(LabBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class RadiusUserCreate(BaseModel):
    lab_id: UUID
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    department: str | None = Field(default=None, max_length=128)
    groups: list[str] = Field(default_factory=list)
    status: UserStatus = UserStatus.active
    expires_at: datetime | None = None


class RadiusUserUpdate(BaseModel):
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    department: str | None = None
    groups: list[str] | None = None
    status: UserStatus | None = None
    expires_at: datetime | None = None


class RadiusUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_id: UUID
    username: str
    first_name: str | None = None
    last_name: str | None = None
    department: str | None = None
    groups: list
    status: UserStatus
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GenerateUsersRequest(BaseModel):
    lab_id: UUID
    count: int = Field(default=10, ge=1, le=500)
    # How usernames are formed for demo identities.
    username_style: str = Field(
        default="numbered",
        pattern="^(numbered|first_last|flast|emailish)$",
    )
    prefix: str = Field(default="user", min_length=1, max_length=32)
    # Selectable profile attributes to populate on generate.
    include_first_name: bool = True
    include_last_name: bool = True
    include_department: bool = True
    include_groups: bool = True
    department: str | None = Field(default="Engineering", max_length=128)
    groups: list[str] = Field(default_factory=lambda: ["students"])
    # Lab-friendly passwords (word+digits) by default.
    password_style: str = Field(default="easy", pattern="^(easy|random)$")
    password_length: int = Field(default=8, ge=6, le=64)


class GeneratedUserCredential(BaseModel):
    username: str
    password: str
    first_name: str | None = None
    last_name: str | None = None
    department: str | None = None
    groups: list[str] = Field(default_factory=list)


class GenerateUsersResponse(BaseModel):
    created: int
    users: list[RadiusUserRead]
    credentials: list[GeneratedUserCredential]


class RadiusClientCreate(BaseModel):
    lab_id: UUID
    name: str = Field(min_length=1, max_length=200)
    ip_address: str = Field(min_length=1, max_length=64)
    shared_secret: str = Field(min_length=1, max_length=256)
    device_type: str | None = None
    enabled: bool = True


class RadiusClientUpdate(BaseModel):
    name: str | None = None
    ip_address: str | None = None
    shared_secret: str | None = None
    device_type: str | None = None
    enabled: bool | None = None


class RadiusClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_id: UUID
    name: str
    ip_address: str
    shared_secret: str
    device_type: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AuthzPolicyBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    vlan: int | None = Field(default=None, ge=1, le=4094)
    role: str | None = Field(default=None, max_length=128)
    group_name: str | None = Field(default=None, max_length=128)
    # Raw RADIUS reply attributes (Advanced editor): {"Session-Timeout": "3600"}.
    reply_attributes: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class AuthzPolicyCreate(AuthzPolicyBase):
    lab_id: UUID


class AuthzPolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    vlan: int | None = Field(default=None, ge=1, le=4094)
    role: str | None = None
    group_name: str | None = None
    reply_attributes: dict[str, str] | None = None
    enabled: bool | None = None
    # Explicit clears, since a JSON null is indistinguishable from "unchanged".
    clear_vlan: bool = False
    clear_role: bool = False
    clear_group: bool = False


class RenderedReplyAttribute(BaseModel):
    name: str
    op: str
    value: str


class AuthzPolicyRead(AuthzPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_id: UUID
    created_at: datetime
    # What actually gets written to radreply/radgroupreply (computed on read).
    rendered_attributes: list[RenderedReplyAttribute] = Field(default_factory=list)
    endpoint_count: int = 0
    summary: str = ""


class AttributeCatalogEntry(BaseModel):
    name: str
    label: str
    example: str
    description: str


class EndpointBase(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    device_type: str | None = Field(default=None, max_length=64)
    authz_policy_id: UUID | None = None
    enabled: bool = True


class EndpointCreate(EndpointBase):
    lab_id: UUID
    # Any common spelling: aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff, aabb.ccdd.eeff, aabbccddeeff.
    mac_address: str = Field(min_length=12, max_length=32)


class EndpointUpdate(BaseModel):
    mac_address: str | None = Field(default=None, min_length=12, max_length=32)
    description: str | None = Field(default=None, max_length=255)
    device_type: str | None = Field(default=None, max_length=64)
    authz_policy_id: UUID | None = None
    enabled: bool | None = None
    clear_authz_policy: bool = False


class EndpointRead(EndpointBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_id: UUID
    mac_address: str
    created_at: datetime
    authz_policy_name: str | None = None
    # Every User-Name spelling registered in FreeRADIUS for this MAC.
    radius_usernames: list[str] = Field(default_factory=list)


class EndpointBulkCreate(EndpointBase):
    lab_id: UUID
    # Free-form paste: newline, comma, or semicolon separated MACs.
    mac_addresses: str = Field(min_length=1)


class EndpointBulkResponse(BaseModel):
    created: int
    skipped: int
    errors: list[str] = Field(default_factory=list)
    endpoints: list[EndpointRead] = Field(default_factory=list)


class GenerateEndpointsRequest(BaseModel):
    lab_id: UUID
    count: int = Field(default=5, ge=1, le=500)
    # OUI (vendor prefix) the generated MACs share, e.g. "aa:bb:cc".
    oui: str = Field(default="02:1a:2b", max_length=32)
    device_type: str | None = Field(default=None, max_length=64)
    # Mix device types from a lab-friendly list (printer, camera, voip, …).
    mixed_device_types: bool = True
    authz_policy_id: UUID | None = None
    enabled: bool = True


class GenerateEndpointsResponse(BaseModel):
    created: int
    endpoints: list[EndpointRead] = Field(default_factory=list)


class AuthEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_id: UUID | None
    timestamp: datetime
    identity: str | None
    method: AuthMethod
    result: AuthResult
    failure_reason: str | None
    returned_attributes: dict
    nas_ip: str | None
    # Friendly, derived explanation for failures (not stored; computed on read).
    failure_summary: str | None = None
    failure_hint: str | None = None


class HealthComponent(BaseModel):
    name: str
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    components: list[HealthComponent]
