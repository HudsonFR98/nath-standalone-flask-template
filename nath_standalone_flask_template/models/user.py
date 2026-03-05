import hashlib
import logging
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship, validates
from sqlalchemy.ext.declarative import declared_attr
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from nath_standalone_flask_template.lib.database import Base, DBSession
from nath_standalone_flask_template.lib import config

log = logging.getLogger(__name__)

# Association table for user-role many-to-many relationship
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True)
)

class Role(Base):
    """Role model for permission management"""
    __tablename__ = 'roles'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    
    # Define permissions as a comma-separated string of permission names
    permissions = Column(String(255), default='')
    
    # Relationship with users
    users = relationship('User', secondary=user_roles, back_populates='roles')
    
    def __init__(self, name, description=None, permissions=None):
        self.name = name
        self.description = description
        self.permissions = ','.join(permissions) if permissions else ''
    
    def get_permissions(self) -> List[str]:
        """Get the list of permissions for this role"""
        return self.permissions.split(',') if self.permissions else []
    
    def has_permission(self, permission: str) -> bool:
        """Check if this role has a specific permission"""
        return permission in self.get_permissions()
    
    def add_permission(self, permission: str):
        """Add a permission to this role"""
        permissions = self.get_permissions()
        if permission not in permissions:
            permissions.append(permission)
            self.permissions = ','.join(permissions)
    
    def remove_permission(self, permission: str):
        """Remove a permission from this role"""
        permissions = self.get_permissions()
        if permission in permissions:
            permissions.remove(permission)
            self.permissions = ','.join(permissions)

class User(Base, UserMixin):
    """User model with role-based permissions"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    ide = Column(String(50), unique=True, nullable=False)  # Username
    pwd = Column(String(128), nullable=False)  # Hashed password
    first_name = Column(String(50))
    last_name = Column(String(50))
    email = Column(String(100))
    active = Column(Boolean, default=True)
    has_left = Column(Boolean, default=False)
    
    # Optional fields from the original model
    ptf_id = Column(Integer)
    center_id = Column(Integer)
    
    # Relationship with roles
    roles = relationship('Role', secondary=user_roles, back_populates='users')
    
    # Cache for permissions
    _permissions = None
    
    @validates('pwd')
    def _hash_password(self, key, password):
        """Hash the password using Werkzeug's secure password hashing"""
        if password and not password.startswith('pbkdf2:') and not password.startswith('sha256$'):
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
    
    # Flask-Login required methods
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
    
    def has_role(self, role_name: str) -> bool:
        """Check if the user has a specific role"""
        return any(role.name == role_name for role in self.roles)
    
    def add_role(self, role):
        """Add a role to the user"""
        if role not in self.roles:
            self.roles.append(role)
            self._permissions = None  # Reset permissions cache
    
    def remove_role(self, role):
        """Remove a role from the user"""
        if role in self.roles:
            self.roles.remove(role)
            self._permissions = None  # Reset permissions cache
    
    def check_password(self, password: str) -> bool:
        """Check if the provided password matches the stored hash"""
        # Check if password is in old SHA256 format
        if self.pwd.startswith('sha256$'):
            # Legacy format - check against SHA256 hash
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            if self.pwd == f'sha256${hashed_password}':
                # Migrate to new format on successful login
                self.pwd = generate_password_hash(password)
                DBSession.commit()
                return True
            return False
        else:
            # New format - use Werkzeug's check_password_hash
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
        """Load initial admin values from application config with safe defaults."""
        username = config.ADMIN_USER_USERNAME
        password = config.ADMIN_USER_PASSWORD
        first_name = config.ADMIN_USER_FIRST_NAME
        last_name = config.ADMIN_USER_LAST_NAME
        email = config.ADMIN_USER_EMAIL
        return {
            'username': username,
            'password': password,
            'first_name': first_name,
            'last_name': last_name,
            'email': email
        }
    
    @classmethod
    def create_admin_if_not_exists(cls):
        """Ensure admin user exists and matches configured values."""
        admin_data = cls._get_initial_admin_data()

        # Create admin role if it doesn't exist
        admin_role = Role.query.filter_by(name='admin').first()
        if not admin_role:
            admin_role = Role(
                name='admin',
                description='Administrator with all permissions',
                permissions=['admin', 'read', 'write', 'delete']
            )
            DBSession.add(admin_role)

        # Technical admin account is expected to be user id 1
        admin_user = cls.query.get(1)
        
        if not admin_user:
            # Create admin user
            admin_user = cls(
                ide=admin_data['username'],
                pwd=admin_data['password'],  # Will be hashed by the validator
                first_name=admin_data['first_name'],
                last_name=admin_data['last_name'],
                email=admin_data['email'],
                active=True,
                has_left=False
            )
            admin_user.add_role(admin_role)
            DBSession.add(admin_user)
            DBSession.commit()
            log.info("Created admin user with username '%s'", admin_data['username'])
            return admin_user
        else:
            # Update existing admin user from config
            admin_user.ide = admin_data['username']
            admin_user.first_name = admin_data['first_name']
            admin_user.last_name = admin_data['last_name']
            admin_user.email = admin_data['email']
            admin_user.active = True
            admin_user.has_left = False
            if admin_role not in admin_user.roles:
                admin_user.add_role(admin_role)
            admin_user.pwd = admin_data['password']  # Will be hashed by the validator

            DBSession.commit()
            log.info("Updated admin user '%s' from configuration", admin_data['username'])
        return admin_user

# Add query property to models
User.query = DBSession.query_property()
Role.query = DBSession.query_property()

# For backward compatibility
Service = None