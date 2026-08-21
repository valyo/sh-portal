"""Add delivered_at to bookings and bookings_lamm

Revision ID: a3b4c5d6e7f8
Revises: f8a9b0c1d2e3
Create Date: 2026-08-21

"""
from alembic import op
import sqlalchemy as sa


revision = 'a3b4c5d6e7f8'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookings') as batch:
        batch.add_column(sa.Column('delivered_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('bookings_lamm') as batch:
        batch.add_column(sa.Column('delivered_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('bookings_lamm') as batch:
        batch.drop_column('delivered_at')
    with op.batch_alter_table('bookings') as batch:
        batch.drop_column('delivered_at')
