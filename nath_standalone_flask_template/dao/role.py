from typing import Iterable, List, Optional

from flask_babel import gettext as _

from nath_standalone_flask_template.lib.const import ADMIN_ROLE_NAME
from nath_standalone_flask_template.lib.database import DBSession
from nath_standalone_flask_template.lib.exc import DomainError
from nath_standalone_flask_template.models.user import Permission, Role


def list_roles() -> List[Role]:
    return Role.query.order_by(Role.name).all()


def get_role(pk: int) -> Optional[Role]:
    return Role.query.get(pk)


def get_role_by_name(name: str) -> Optional[Role]:
    return Role.query.filter_by(name=name).first()


def _load_permissions(permission_ids: Iterable) -> List[Permission]:
    records = []
    for raw_id in permission_ids:
        try:
            permission_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        permission = Permission.query.get(permission_id)
        if permission is None:
            raise DomainError(_("One of the selected permissions does not exist."))
        records.append(permission)
    return records


def _replace_permissions(role: Role, permission_ids: Iterable) -> None:
    role.granted_permissions.clear()
    for permission in _load_permissions(permission_ids):
        role.granted_permissions.append(permission)


def set_permissions(role_id: int, permission_ids: Iterable) -> Role:
    role = get_role(role_id)
    if role is None:
        raise DomainError(_("Role not found."))
    _replace_permissions(role, permission_ids)
    DBSession.commit()
    return role


def create_role(name: str, description: str = None, permission_ids: Iterable = ()) -> Role:
    slug = (name or "").strip()
    if not slug:
        raise DomainError(_("Role name is required."))
    if get_role_by_name(slug):
        raise DomainError(_("A role with this name already exists."))
    role = Role(name=slug, description=(description or "").strip() or None)
    DBSession.add(role)
    DBSession.flush()
    for permission in _load_permissions(permission_ids):
        role.granted_permissions.append(permission)
    DBSession.commit()
    return role


def update_role(
    pk: int,
    name: str,
    description: str = None,
    permission_ids: Iterable = (),
) -> Role:
    role = get_role(pk)
    if role is None:
        raise DomainError(_("Role not found."))
    slug = (name or "").strip()
    if not slug:
        raise DomainError(_("Role name is required."))
    if role.is_admin_role() and slug != ADMIN_ROLE_NAME:
        raise DomainError(_("The admin role cannot be renamed."))
    existing = get_role_by_name(slug)
    if existing is not None and existing.id != role.id:
        raise DomainError(_("A role with this name already exists."))
    if not role.is_admin_role():
        role.name = slug
    role.description = (description or "").strip() or None
    _replace_permissions(role, permission_ids)
    DBSession.commit()
    return role


def delete_role(pk: int) -> None:
    role = get_role(pk)
    if role is None:
        raise DomainError(_("Role not found."))
    if role.is_admin_role():
        raise DomainError(_("The admin role cannot be deleted."))
    if role.users:
        raise DomainError(_("This role is still assigned to one or more users."))
    DBSession.delete(role)
    DBSession.commit()
