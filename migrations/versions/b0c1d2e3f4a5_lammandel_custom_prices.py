"""Add andel_custom_prices to bookings_lamm

Revision ID: b0c1d2e3f4a5
Revises: e7f8a9b0c1d2
Create Date: 2026-10-25

"""
from alembic import op
import sqlalchemy as sa


revision = 'b0c1d2e3f4a5'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
        batch_op.add_column(sa.Column('andel_custom_prices', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
        batch_op.drop_column('andel_custom_prices')
