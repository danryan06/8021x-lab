"""Authorization policies: what FreeRADIUS returns alongside an Access-Accept."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.freeradius.policy_conditions import (
    parse_policy_conditions,
    render_check_items,
    summarize_conditions,
)
from app.integrations.freeradius.reply_attributes import (
    render_policy_attributes,
    summarize_attributes,
)
from app.integrations.freeradius.sql_sync import (
    delete_group_reply,
    sync_authz_policy_groups,
    sync_endpoint_to_radius,
)
from app.models.entities import AuthzPolicy, Endpoint
from app.schemas.entities import (
    AuthzPolicyCreate,
    AuthzPolicyRead,
    AuthzPolicyUpdate,
    RenderedReplyAttribute,
)


def list_policies(db: Session, lab_id: UUID | None = None) -> list[AuthzPolicy]:
    stmt = select(AuthzPolicy).order_by(AuthzPolicy.name)
    if lab_id:
        stmt = stmt.where(AuthzPolicy.lab_id == lab_id)
    return list(db.scalars(stmt).all())


def get_policy(db: Session, policy_id: UUID) -> AuthzPolicy | None:
    return db.get(AuthzPolicy, policy_id)


def to_read(db: Session, policy: AuthzPolicy) -> AuthzPolicyRead:
    """Serialize a policy with the reply attributes it renders to."""
    attributes = render_policy_attributes(
        vlan=policy.vlan,
        role=policy.role,
        extra=policy.reply_attributes or {},
    )
    endpoint_count = (
        db.scalar(
            select(func.count())
            .select_from(Endpoint)
            .where(Endpoint.authz_policy_id == policy.id)
        )
        or 0
    )
    read = AuthzPolicyRead.model_validate(policy)
    read.rendered_attributes = [
        RenderedReplyAttribute(name=a.name, op=a.op, value=a.value) for a in attributes
    ]
    read.rendered_check_items = [
        RenderedReplyAttribute(name=item.name, op=item.op, value=item.value)
        for item in render_check_items(policy.conditions)
    ]
    read.endpoint_count = int(endpoint_count)
    reply_summary = summarize_attributes({a.name: a.value for a in attributes})
    check_summary = summarize_conditions(policy.conditions)
    read.summary = " · ".join(part for part in (reply_summary, check_summary) if part)
    return read


def _normalized_conditions(raw: dict | None) -> dict:
    parsed = parse_policy_conditions(raw)
    return parsed.model_dump(exclude_none=True)


def _validate_group_is_free(
    db: Session,
    lab_id: UUID,
    group_name: str | None,
    exclude_id: UUID | None = None,
) -> None:
    """One policy per user group: FreeRADIUS would otherwise merge two policies."""
    group = (group_name or "").strip()
    if not group:
        return
    stmt = select(AuthzPolicy).where(
        AuthzPolicy.lab_id == lab_id,
        AuthzPolicy.group_name == group,
    )
    if exclude_id:
        stmt = stmt.where(AuthzPolicy.id != exclude_id)
    existing = db.scalar(stmt)
    if existing:
        raise ValueError(
            f"group '{group}' is already authorized by policy '{existing.name}' — "
            "edit that policy or pick another group"
        )


def _resync(db: Session, policy: AuthzPolicy) -> None:
    """Re-push the policy: endpoints using it, plus its group reply rows."""
    endpoints = list(
        db.scalars(select(Endpoint).where(Endpoint.authz_policy_id == policy.id)).all()
    )
    for endpoint in endpoints:
        sync_endpoint_to_radius(db, endpoint)
    sync_authz_policy_groups(db, policy.lab_id)


def create_policy(db: Session, payload: AuthzPolicyCreate) -> AuthzPolicy:
    # Render eagerly so an invalid attribute name/value fails before it is stored.
    render_policy_attributes(
        vlan=payload.vlan, role=payload.role, extra=payload.reply_attributes
    )
    conditions = _normalized_conditions(payload.conditions)
    _validate_group_is_free(db, payload.lab_id, payload.group_name)
    policy = AuthzPolicy(
        lab_id=payload.lab_id,
        name=payload.name,
        vlan=payload.vlan,
        role=(payload.role or None),
        group_name=((payload.group_name or "").strip() or None),
        reply_attributes=payload.reply_attributes,
        conditions=conditions,
        enabled=payload.enabled,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    _resync(db, policy)
    return policy


def update_policy(db: Session, policy: AuthzPolicy, payload: AuthzPolicyUpdate) -> AuthzPolicy:
    previous_group = policy.group_name
    fields = payload.model_dump(exclude_unset=True)
    fields.pop("clear_vlan", None)
    fields.pop("clear_role", None)
    fields.pop("clear_group", None)
    fields.pop("clear_conditions", None)

    if payload.group_name is not None:
        _validate_group_is_free(db, policy.lab_id, payload.group_name, exclude_id=policy.id)

    if "conditions" in fields:
        fields["conditions"] = _normalized_conditions(fields.get("conditions"))

    for field, value in fields.items():
        if value is None:
            continue
        setattr(policy, field, value.strip() or None if isinstance(value, str) else value)

    if payload.clear_vlan:
        policy.vlan = None
    if payload.clear_role:
        policy.role = None
    if payload.clear_group:
        policy.group_name = None
    if payload.clear_conditions:
        policy.conditions = {}

    render_policy_attributes(
        vlan=policy.vlan, role=policy.role, extra=policy.reply_attributes or {}
    )
    db.commit()
    db.refresh(policy)

    if previous_group and previous_group != policy.group_name:
        delete_group_reply(db, previous_group)
    _resync(db, policy)
    return policy


def delete_policy(db: Session, policy: AuthzPolicy) -> None:
    group = policy.group_name
    lab_id = policy.lab_id
    endpoints = list(
        db.scalars(select(Endpoint).where(Endpoint.authz_policy_id == policy.id)).all()
    )
    for endpoint in endpoints:
        endpoint.authz_policy_id = None
    db.delete(policy)
    db.commit()
    if group:
        delete_group_reply(db, group)
    for endpoint in endpoints:
        db.refresh(endpoint)
        sync_endpoint_to_radius(db, endpoint)
    sync_authz_policy_groups(db, lab_id)
