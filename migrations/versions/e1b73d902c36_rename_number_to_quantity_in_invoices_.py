"""rename number to quantity in invoices tables

Revision ID: e1b73d902c36
Revises: e9107734564c
Create Date: 2025-05-09 17:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1b73d902c36'
down_revision = 'e9107734564c'
branch_labels = None
depends_on = None


def upgrade():
    # For invoices table
    op.execute('ALTER TABLE invoices RENAME COLUMN number TO quantity')

    # For invoices_lamm table
    op.execute('ALTER TABLE invoices_lamm RENAME COLUMN number TO quantity')


def downgrade():
    # For invoices table
    op.execute('ALTER TABLE invoices RENAME COLUMN quantity TO number')

    # For invoices_lamm table
    op.execute('ALTER TABLE invoices_lamm RENAME COLUMN quantity TO number')
