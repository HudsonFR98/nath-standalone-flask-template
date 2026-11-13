import hashlib
import logging
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship, validates
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from nath_standalone_flask_template.lib.database import Base, DBSession
from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template.lib._config import reviewer_bootstrap_configured
from nath_standalone_flask_template.lib.const import (
    ADMIN_ROLE_NAME,
    DEFAULT_PERMISSIONS,
)

log = logging.getLogger(__name__)

user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
)

role_permissions = Table(
    'role_permissions',
    Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', Integer, ForeignKey('permissions.id', ondelete='RESTRICT'), primary_key=True)
)


class Permission(Base):
    """Named permission slug attached to one or more roles."""
    __tablename__ = 'permissions'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    is_system = Column(Boolean, default=False, nullable=False)

    roles = relationship(
        'Role',
        secondary=role_permissions,
        back_populates='granted_permissions',
    )

    def __init__(self, name, description=None, is_system=False):
        self.name = name
        self.description = description
        self.is_system = is_system

    def __str__(self):
        return self.name

    @classmethod
    def ensure_defaults(cls) -> List["Permission"]:
        """Upsert the built-in permission slugs used by the template."""
        result = []
        for name, description in DEFAULT_PERMISSIONS:
            perm = cls.query.filter_by(name=name).first()
            if perm is None:
                perm = cls(name=name, description=description, is_system=True)
                DBSession.add(perm)
            else:
                perm.is_system = True
                if not perm.description:
                    perm.description = description
            result.append(perm)
        DBSession.flush()
        return result


class Role(Base):
    """Role model for permission management"""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))

    users = relationship('User', secondary=user_roles, back_populates='roles')
    granted_permissions = relationship(
        'Permission',
        secondary=role_permissions,
        back_populates='roles',
    )

    def __init__(self, name, description=None):
        self.name = name
        self.description = description

    def get_permissions(self) -> List[str]:
        """Permission slugs granted by this role."""
        return [permission.name for permission in self.granted_permissions]

    def has_permission(self, permission: str) -> bool:
        return permission in self.get_permissions()

    def add_permission(self, permission):
        """Attach a Permission instance or look it up by slug."""
        if isinstance(permission, str):
            record = Permission.query.filter_by(name=permission).first()
            if record is None:
                raise ValueError(f"Unknown permission: {permission}")
            permission = record
        if permission not in self.granted_permissions:
            self.granted_permissions.append(permission)

    def remove_permission(self, permission):
        if isinstance(permission, str):
            permission = next(
                (item for item in self.granted_permissions if item.name == permission),
                None,
            )
        if permission is not None and permission in self.granted_permissions:
            self.granted_permissions.remove(permission)

    def is_admin_role(self) -> bool:
        return self.name == ADMIN_ROLE_NAME


class User(Base, UserMixin):
    """User model with role-based permissions"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    ide = Column(String(50), unique=True, nullable=False)  # Username
    pwd = Column(String(255), nullable=False)  # Werkzeug hash (scrypt or pbkdf2)
    first_name = Column(String(50))
    last_name = Column(String(50))
    email = Column(String(100))
    active = Column(Boolean, default=True)
    has_left = Column(Boolean, default=False)

    ptf_id = Column(Integer)
    center_id = Column(Integer)

    api_token_hash = Column(String(64), unique=True, nullable=True)
    api_token_prefix = Column(String(16), nullable=True)
    api_token_created_at = Column(DateTime, nullable=True)

    roles = relationship('Role', secondary=user_roles, back_populates='users')

    _permissions = None

    @validates('pwd')
    def _hash_password(self, key, password):
        """Hash the password using Werkzeug's secure password hashing"""
        if password and not password.startswith(('pbkdf2:', 'scrypt:', 'sha256$')):
            return generate_password_hash(password)
        return password

    def __init__(self, ide, pwd, first_name=None, last_name=None, email=None,
                 active=True, has_left=False, ptf_id=None, center_id=None):
        self.ide = ide
        self.pwd = pwd  # Will be hashed by the validator
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.active = active
        self.has_left = has_left
        self.ptf_id = ptf_id
        self.center_id = center_id

    def __str__(self):
        """String representation of the user"""
        return f"{self.first_name} {self.last_name}"

    def get_id(self):
        """Return the user ID as a string (required by Flask-Login)"""
        return str(self.id)

    def is_authenticated(self):
        """Return True if the user is authenticated"""
        return self.active and not self.has_left

    def is_active(self):
        """Return True if the user is active"""
        return self.active and not self.has_left

    def reload_permissions(self):
        """Reload the user's permissions from their roles"""
        self._permissions = set()
        for role in self.roles:
            self._permissions.update(role.get_permissions())

    def has_permission(self, permission: str) -> bool:
        """Check if the user has a specific permission"""
        if self._permissions is None:
            self.reload_permissions()
        return permission in (self._permissions or set())

    def has_role(self, *role_names: str) -> bool:
        names = set(role_names)
        return any(role.name in names for role in self.roles)

    def has_api_token(self) -> bool:
        return bool(self.api_token_hash)

    def can_use_api_token(self) -> bool:
        return self.active and not self.has_left and self.has_api_token()

    def add_role(self, role):
        """Add a role to the user"""
        if role not in self.roles:
            self.roles.append(role)
            self._permissions = None

    def remove_role(self, role):
        """Remove a role from the user"""
        if role in self.roles:
            self.roles.remove(role)
            self._permissions = None

    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the stored hash"""
        if self.pwd.startswith('sha256$'):
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            if self.pwd == f'sha256${hashed_password}':
                self.pwd = generate_password_hash(password)
                DBSession.commit()
                return True
            return False
        return check_password_hash(self.pwd, password)

    @classmethod
    def authenticate(cls, username: str, password: str) -> Optional['User']:
        """Authenticate a user with username and password"""
        user = cls.query.filter_by(ide=username, active=True).first()
        if user and user.check_password(password):
            return user
        raise Exception("Invalid username or password")

    @classmethod
    def _get_initial_admin_data(cls) -> dict:
        return {
            'username': config.ADMIN_USER_USERNAME,
            'password': config.ADMIN_USER_PASSWORD,
            'first_name': config.ADMIN_USER_FIRST_NAME,
            'last_name': config.ADMIN_USER_LAST_NAME,
            'email': config.ADMIN_USER_EMAIL,
        }

    @classmethod
    def _get_initial_reviewer_data(cls) -> dict | None:
        if not reviewer_bootstrap_configured():
            return None
        username = config.REVIEWER_USER_USERNAME
        return {
            'username': username,
            'password': config.REVIEWER_USER_PASSWORD,
            'first_name': config.REVIEWER_USER_FIRST_NAME or username,
            'last_name': config.REVIEWER_USER_LAST_NAME or '',
            'email': config.REVIEWER_USER_EMAIL or f'{username}@local',
        }

    @classmethod
    def _upsert_bootstrap_user(cls, data: dict, role: Role, existing=None):
        user = existing
        created = False
        if user is None:
            user = cls(
                ide=data['username'],
                pwd=data['password'],
                first_name=data['first_name'],
                last_name=data['last_name'],
                email=data['email'],
                active=True,
                has_left=False,
            )
            DBSession.add(user)
            created = True
        else:
            user.ide = data['username']
            user.first_name = data['first_name']
            user.last_name = data['last_name']
            user.email = data['email']
            user.active = True
            user.has_left = False
            user.pwd = data['password']
        if role not in user.roles:
            user.add_role(role)
        log.info(
            "%s user '%s' from configuration",
            "Created" if created else "Updated",
            data['username'],
        )
        return user

    @classmethod
    def create_admin_if_not_exists(cls):
        """Ensure default permissions, admin/reviewer roles, and bootstrap users exist."""
        default_permissions = Permission.ensure_defaults()

        admin_role = Role.query.filter_by(name=ADMIN_ROLE_NAME).first()
        if not admin_role:
            admin_role = Role(
                name=ADMIN_ROLE_NAME,
                description='Administrator with all permissions',
            )
            DBSession.add(admin_role)
            DBSession.flush()

        for permission in default_permissions:
            admin_role.add_permission(permission)

        reviewer_role = Role.query.filter_by(name='reviewer').first()
        if not reviewer_role:
            reviewer_role = Role(
                name='reviewer',
                description='Reviewer with read, write and delete',
            )
            DBSession.add(reviewer_role)
            DBSession.flush()
        for permission in default_permissions:
            if permission.name != 'admin':
                reviewer_role.add_permission(permission)

        admin_data = cls._get_initial_admin_data()
        cls._upsert_bootstrap_user(admin_data, admin_role, existing=cls.query.get(1))
        reviewer_data = cls._get_initial_reviewer_data()
        if reviewer_data is not None:
            cls._upsert_bootstrap_user(
                reviewer_data,
                reviewer_role,
                existing=cls.query.filter_by(ide=reviewer_data['username']).first(),
            )
        DBSession.commit()


User.query = DBSession.query_property()
Role.query = DBSession.query_property()
Permission.query = DBSession.query_property()

Service = None
