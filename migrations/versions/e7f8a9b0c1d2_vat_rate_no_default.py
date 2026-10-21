"""Drop the default on vat_rate so every invoice must state its VAT rate

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-10-21

The default of 12 was only needed to backfill invoices that existed before the
column was added. Existing rows keep their value.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('invoices', 'invoices_lamm'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('vat_rate', existing_type=sa.Integer(), existing_nullable=False, server_default=None)


def downgrade():
    for table in ('invoices_lamm', 'invoices'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column('vat_rate', existing_type=sa.Integer(), existing_nullable=False, server_default='12')
