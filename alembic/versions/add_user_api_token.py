"""Add per-user API token hash columns

Revision ID: add_user_api_token
Revises: normalize_role_permissions
Create Date: 2026-11-13 08:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_user_api_token'
down_revision = 'normalize_role_permissions'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('api_token_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('api_token_prefix', sa.String(length=16), nullable=True))
    op.add_column('users', sa.Column('api_token_created_at', sa.DateTime(), nullable=True))
    op.create_unique_constraint('uq_users_api_token_hash', 'users', ['api_token_hash'])


def downgrade():
    op.drop_constraint('uq_users_api_token_hash', 'users', type_='unique')
    op.drop_column('users', 'api_token_created_at')
    op.drop_column('users', 'api_token_prefix')
    op.drop_column('users', 'api_token_hash')
