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
    groups: list[str] = Field(default_factory=list)
    status: UserStatus = UserStatus.active
    expires_at: datetime | None = None


class RadiusUserUpdate(BaseModel):
    password: str | None = None
    groups: list[str] | None = None
    status: UserStatus | None = None
    expires_at: datetime | None = None


class RadiusUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    lab_id: UUID
    username: str
    groups: list
    status: UserStatus
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class GenerateUsersRequest(BaseModel):
    lab_id: UUID
    count: int = Field(default=10, ge=1, le=500)
    prefix: str = Field(default="user", min_length=1, max_length=32)
    groups: list[str] = Field(default_factory=lambda: ["students"])
    password_length: int = Field(default=12, ge=8, le=64)


class GeneratedUserCredential(BaseModel):
    username: str
    password: str


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


class HealthComponent(BaseModel):
    name: str
    status: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    components: list[HealthComponent]
