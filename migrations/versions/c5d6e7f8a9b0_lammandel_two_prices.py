"""Add price_lamm_2 to season and andel_tiers to bookings_lamm

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.add_column(sa.Column('price_lamm_2', sa.Float(), nullable=True))
    with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
        batch_op.add_column(sa.Column('andel_tiers', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('bookings_lamm', schema=None) as batch_op:
        batch_op.drop_column('andel_tiers')
    with op.batch_alter_table('season', schema=None) as batch_op:
        batch_op.drop_column('price_lamm_2')
