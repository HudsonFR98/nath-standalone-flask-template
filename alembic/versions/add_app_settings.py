"""Add app_settings table

Revision ID: add_app_settings
Revises: add_user_api_token
Create Date: 2026-11-13 10:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_app_settings'
down_revision = 'add_user_api_token'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade():
    op.drop_table('app_settings')
