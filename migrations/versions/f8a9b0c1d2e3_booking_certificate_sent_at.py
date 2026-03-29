"""Add certificate_sent_at to bookings and bookings_lamm

Revision ID: f8a9b0c1d2e3
Revises: e2f3a4b5c6d7
Create Date: 2026-03-28

"""
from alembic import op
import sqlalchemy as sa


revision = 'f8a9b0c1d2e3'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookings') as batch:
        batch.add_column(sa.Column('certificate_sent_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('bookings_lamm') as batch:
        batch.add_column(sa.Column('certificate_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('bookings_lamm') as batch:
        batch.drop_column('certificate_sent_at')
    with op.batch_alter_table('bookings') as batch:
        batch.drop_column('certificate_sent_at')
