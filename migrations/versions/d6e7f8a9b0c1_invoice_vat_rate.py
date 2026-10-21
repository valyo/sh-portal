"""Add vat_rate to invoices and invoices_lamm

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('invoices', 'invoices_lamm'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('vat_rate', sa.Integer(), nullable=False, server_default='12'))


def downgrade():
    for table in ('invoices_lamm', 'invoices'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('vat_rate')
