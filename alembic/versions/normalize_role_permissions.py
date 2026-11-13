"""Normalize role permissions into a Permission table

Revision ID: normalize_role_permissions
Revises: add_task_tables
Create Date: 2026-11-13 07:54:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'normalize_role_permissions'
down_revision = 'add_task_tables'
branch_labels = None
depends_on = None

# Duplicated from lib.const so Alembic does not import the Flask app.
DEFAULT_PERMISSIONS = (
    ("admin", "Full administration access"),
    ("read", "Read access"),
    ("write", "Write access"),
    ("delete", "Delete access"),
)


def upgrade():
    op.create_table(
        'permissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('permission_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
    )

    conn = op.get_bind()
    perm_ids = {}
    for name, description in DEFAULT_PERMISSIONS:
        permission_id = conn.execute(
            sa.text(
                "INSERT INTO permissions (name, description, is_system) "
                "VALUES (:name, :description, true) RETURNING id"
            ),
            {"name": name, "description": description},
        ).scalar()
        perm_ids[name] = permission_id

    # Unknown CSV tokens are skipped; bootstrap on next app start attaches
    # the four default slugs to the admin role.
    roles = conn.execute(sa.text("SELECT id, permissions FROM roles")).fetchall()
    for role_id, csv_value in roles:
        names = [token.strip() for token in (csv_value or "").split(",") if token.strip()]
        for name in names:
            permission_id = perm_ids.get(name)
            if permission_id is None:
                continue
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"
                ),
                {"role_id": role_id, "permission_id": permission_id},
            )

    op.drop_column('roles', 'permissions')


def downgrade():
    op.add_column(
        'roles',
        sa.Column('permissions', sa.String(length=255), server_default='', nullable=True),
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT rp.role_id, p.name FROM role_permissions rp "
            "JOIN permissions p ON p.id = rp.permission_id "
            "ORDER BY rp.role_id, p.name"
        )
    ).fetchall()
    by_role = {}
    for role_id, name in rows:
        by_role.setdefault(role_id, []).append(name)
    for role_id, names in by_role.items():
        conn.execute(
            sa.text("UPDATE roles SET permissions = :csv WHERE id = :role_id"),
            {"csv": ",".join(names), "role_id": role_id},
        )
    op.drop_table('role_permissions')
    op.drop_table('permissions')
