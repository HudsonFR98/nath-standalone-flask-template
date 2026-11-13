import re
from typing import List, Optional

from flask_babel import gettext as _

from nath_standalone_flask_template.lib.const import PERMISSION_NAME_PATTERN
from nath_standalone_flask_template.lib.database import DBSession
from nath_standalone_flask_template.lib.exc import DomainError
from nath_standalone_flask_template.models.user import Permission


def list_permissions() -> List[Permission]:
    return Permission.query.order_by(Permission.name).all()


def get_permission(pk: int) -> Optional[Permission]:
    return Permission.query.get(pk)


def get_permission_by_name(name: str) -> Optional[Permission]:
    return Permission.query.filter_by(name=name).first()


def create_permission(name: str, description: str = None) -> Permission:
    slug = (name or "").strip()
    if not re.match(PERMISSION_NAME_PATTERN, slug):
        raise DomainError(
            _("Permission name must start with a letter and contain only "
              "lowercase letters, digits, or underscores.")
        )
    if get_permission_by_name(slug):
        raise DomainError(_("A permission with this name already exists."))
    permission = Permission(
        name=slug,
        description=(description or "").strip() or None,
        is_system=False,
    )
    DBSession.add(permission)
    DBSession.commit()
    return permission


def update_permission(pk: int, description: str = None) -> Permission:
    permission = get_permission(pk)
    if permission is None:
        raise DomainError(_("Permission not found."))
    permission.description = (description or "").strip() or None
    DBSession.commit()
    return permission


def delete_permission(pk: int) -> None:
    permission = get_permission(pk)
    if permission is None:
        raise DomainError(_("Permission not found."))
    if permission.is_system:
        raise DomainError(_("System permissions cannot be deleted."))
    if permission.roles:
        raise DomainError(_("This permission is still assigned to one or more roles."))
    DBSession.delete(permission)
    DBSession.commit()
